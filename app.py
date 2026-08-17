# Reemplaza la parte inicial de cargar_datos_bigquery por esto:
if "gcp_service_account" in st.secrets:
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict:
        # Limpia caracteres escapados por error al pegar
        pk = creds_dict["private_key"]
        pk = pk.replace("\\n", "\n").replace("\\_", "_")
        creds_dict["private_key"] = pk
        
    client = bigquery.Client.from_service_account_info(creds_dict)
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from google.cloud import bigquery

# -------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA
# -------------------------------------------------------------------------
st.set_page_config(
    page_title="Simulador Operativo | PedidosYa VE",
    page_icon="🛵",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    .stMetric {
        background-color: #FFFFFF;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    div[data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E2E8F0;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------------
# 2. CARGA DE DATOS DESDE BIGQUERY
# -------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def cargar_datos_bigquery():
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            client = bigquery.Client.from_service_account_info(creds_dict)
        else:
            client = bigquery.Client(project='peya-venezuela')

        sql_query = """
        WITH 
        daily_staffing AS (
            SELECT 
                DATE(SAFE_CAST(staffing.created_date_local AS TIMESTAMP)) AS ds_date,
                staffing.city_name AS city_name,
                SUM(staffing.adjusted_orders) AS orders_forecast_rooster,
                SUM(staffing.orders_actuals) AS orders_real,
                SUM(staffing.evaluations_working_time) / 3600.0 AS worked_hours
            FROM `peya-data-origins-pro.cl_hurrier.staffing_kpi` AS staffing
            WHERE SAFE_CAST(staffing.created_date_local AS TIMESTAMP) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY)
              AND staffing.country_code = 've'
            GROUP BY 1, 2
        ),
        daily_payments AS (
            SELECT 
                DATE(SAFE_CAST(payments.created_date AS TIMESTAMP)) AS ds_date,
                SUM(payments.total_date_payment) AS rider_payments
            FROM `peya-data-origins-pro.cl_hurrier.rider_payments` AS payments
            WHERE SAFE_CAST(payments.created_date AS TIMESTAMP) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY)
              AND payments.country_code = 've'
            GROUP BY 1
        )
        SELECT 
            s.ds_date,
            s.city_name,
            s.orders_forecast_rooster,
            s.orders_real,
            ROUND(s.worked_hours, 2) AS worked_hours,
            p.rider_payments,
            ROUND(SAFE_DIVIDE(s.orders_real, s.worked_hours), 2) AS utr_diario,
            ROUND(SAFE_DIVIDE(p.rider_payments, s.orders_real), 2) AS cpo_diario,
            ROUND(SAFE_DIVIDE(p.rider_payments, s.worked_hours), 2) AS cph_diario
        FROM daily_staffing s
        LEFT JOIN daily_payments p ON s.ds_date = p.ds_date
        ORDER BY s.ds_date ASC, s.city_name ASC;
        """
        
        df = client.query(sql_query).to_dataframe()
        
        columnas_num = ['orders_forecast_rooster', 'orders_real', 'worked_hours', 'rider_payments', 'utr_diario', 'cpo_diario', 'cph_diario']
        for col in columnas_num:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                
        df['ds_date'] = pd.to_datetime(df['ds_date'])
        return df
    except Exception as e:
        st.error(f"Error al conectar con BigQuery: {e}")
        st.stop()

# LLAMADA OBLIGATORIA A LA FUNCIÓN (Fuera de la definición)
with st.spinner("Conectando con BigQuery..."):
    df_real = cargar_datos_bigquery()
# -------------------------------------------------------------------------
# 4. LÓGICA DE PROYECCIÓN
# -------------------------------------------------------------------------
if sel_ciudad == 'TODAS (TOTAL VENEZUELA)':
    df_hist = df_real.groupby('ds_date').agg({
        'orders_forecast_rooster': 'sum',
        'orders_real': 'sum',
        'worked_hours': 'sum',
        'rider_payments': 'first'
    }).reset_index()
    df_hist['cph_diario'] = np.where(df_hist['worked_hours'] > 0, df_hist['rider_payments'] / df_hist['worked_hours'], 0.0)
    plaza_label = "Venezuela (Total Consolidado)"
else:
    df_hist = df_real[df_real['city_name'] == sel_ciudad].groupby('ds_date').agg({
        'orders_forecast_rooster': 'sum',
        'orders_real': 'sum',
        'worked_hours': 'sum',
        'cph_diario': 'mean'
    }).reset_index()
    plaza_label = sel_ciudad

df_hist = df_hist.sort_values('ds_date').copy()
max_fecha = df_hist['ds_date'].max()
df_60d = df_hist[df_hist['ds_date'] >= (max_fecha - pd.Timedelta(days=60))].copy()
inicio_mes_actual = max_fecha.replace(day=1)
df_mtd = df_60d[df_60d['ds_date'] >= inicio_mes_actual]

if sel_horizonte == 'Resto del Mes (MTD)':
    ultimo_dia_mes = pd.date_range(start=inicio_mes_actual, periods=1, freq='ME')[0]
    dias_a_proyectar = (ultimo_dia_mes - max_fecha).days
    if dias_a_proyectar <= 0:
        dias_a_proyectar = 14
elif sel_horizonte == 'Próximos 15 días':
    dias_a_proyectar = 15
else:
    dias_a_proyectar = 30

base_orders_dia = float(df_mtd['orders_forecast_rooster'].mean()) if len(df_mtd) > 0 else float(df_60d['orders_forecast_rooster'].mean())
base_cph = float(df_mtd['cph_diario'].mean()) if len(df_mtd) > 0 else float(df_60d['cph_diario'].mean())

mult_vol = 1.0 + (float(pct_impacto) if aplica_quincena else 0.0)
orders_dia_proyectadas = base_orders_dia * mult_vol
orders_totales_proyectadas = int(orders_dia_proyectadas * dias_a_proyectar)

horas_totales_requeridas = int(orders_totales_proyectadas / target_utr) if target_utr > 0 else 0
costo_total_pago = horas_totales_requeridas * base_cph
cpo_proyectado = costo_total_pago / orders_totales_proyectadas if orders_totales_proyectadas > 0 else 0.0

delta_cpo = cpo_proyectado - target_cpo
accuracy_60d = 100.0 - ((np.abs(df_60d['orders_real'] - df_60d['orders_forecast_rooster']).sum() / df_60d['orders_real'].sum()) * 100 if df_60d['orders_real'].sum() > 0 else 0)

# -------------------------------------------------------------------------
# 5. DASHBOARD PRINCIPAL
# -------------------------------------------------------------------------
st.title(f"🚀 Dashboard de Proyección Operativa | {plaza_label}")
st.caption(f"Datos desde BigQuery (`peya-venezuela`). Horizonte: **{dias_a_proyectar} días**. Precisión del modelo (Últ. 60D): **{accuracy_60d:.1f}%**.")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)

kpi1.metric("📦 Órdenes Proyectadas", f"{orders_totales_proyectadas:,}", f"{int(orders_dia_proyectadas):,}/día")
kpi2.metric("⏱️ Horas Requeridas", f"{horas_totales_requeridas:,}", f"{int(horas_totales_requeridas/dias_a_proyectar):,}/día")
kpi3.metric("💵 Gasto Total Riders", f"${costo_total_pago:,.2f}", f"CPH: ${base_cph:.2f}/h")
kpi4.metric(
    "📉 CPO Proyectado", 
    f"${cpo_proyectado:.2f}", 
    f"{delta_cpo:+.2f} vs Target (${target_cpo:.2f})", 
    delta_color="inverse"
)

st.markdown("---")

st.subheader("📈 Evolución Diaria: Histórico (Últimos 2 Meses) vs. Proyección Futura")

fechas_futuras = [max_fecha + pd.Timedelta(days=i+1) for i in range(dias_a_proyectar)]
x_proj = [max_fecha] + fechas_futuras
y_proj = [df_60d[df_60d['ds_date'] == max_fecha]['orders_real'].values[0]] + [orders_dia_proyectadas] * dias_a_proyectar

fig = go.Figure()

fig.add_trace(go.Scatter(
    x=df_60d['ds_date'], y=df_60d['orders_real'],
    mode='lines+markers', name='Órdenes Reales (Histórico + MTD)',
    line=dict(color='#2563EB', width=2.5),
    marker=dict(size=4)
))

fig.add_trace(go.Scatter(
    x=df_60d['ds_date'], y=df_60d['orders_forecast_rooster'],
    mode='lines', name='Forecast Rooster (Base)',
    line=dict(color='#F59E0B', width=2, dash='dash')
))

fig.add_trace(go.Scatter(
    x=x_proj, y=y_proj,
    mode='lines+markers', name=f'Proyección Futura ({dias_a_proyectar} días)',
    line=dict(color='#E31837', width=3, dash='dot'),
    marker=dict(size=6, symbol='diamond')
))

fig.update_layout(
    height=480,
    template='plotly_white',
    hovermode='x unified',
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=20, r=20, t=30, b=20)
)

st.plotly_chart(fig, use_container_width=True)

with st.expander("📋 Ver detalle de datos en tabla"):
    df_display = df_60d[['ds_date', 'orders_real', 'orders_forecast_rooster', 'worked_hours', 'cph_diario']].copy()
    df_display.columns = ['Fecha', 'Órdenes Reales', 'Forecast Rooster', 'Horas Trabajadas', 'CPH ($)']
    st.dataframe(df_display.sort_values('Fecha', ascending=False), use_container_width=True)
