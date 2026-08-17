import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

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
# 2. CARGA DE DATOS DESDE ARCHIVO LOCAL CSV
# -------------------------------------------------------------------------
@st.cache_data
def cargar_datos_csv():
    df = pd.read_csv("datos.csv")
    columnas_num = ['orders_forecast_rooster', 'orders_real', 'worked_hours', 'rider_payments', 'utr_diario', 'cpo_diario', 'cph_diario']
    for col in columnas_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
    df['ds_date'] = pd.to_datetime(df['ds_date'])
    return df

df_real = cargar_datos_csv()

# -------------------------------------------------------------------------
# 3. CONTROLES SIDEBAR
# -------------------------------------------------------------------------
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/d/d6/PedidosYa_Logo.png", width=180)
st.sidebar.title("⚙️ Parámetros de Simulación")

ciudades_lista = sorted([str(c) for c in df_real['city_name'].dropna().unique() if str(c) not in ['None', 'nan']])
opciones_vista = ['TODAS (TOTAL VENEZUELA)'] + ciudades_lista

sel_ciudad = st.sidebar.selectbox("🏙️ Vista / Ciudad:", opciones_vista)
sel_horizonte = st.sidebar.selectbox("📅 Horizonte de Proyección:", ['Resto del Mes (MTD)', 'Próximos 15 días', 'Próximos 30 días'])

st.sidebar.markdown("---")
st.sidebar.subheader("📈 Modificadores de Demanda")
aplica_quincena = st.sidebar.checkbox("💰 ¿Aplica Efecto Quincena?", value=True)
pct_impacto = st.sidebar.slider("Uplift Quincena (%):", min_value=0.0, max_value=0.50, value=0.15, step=0.01,
                                 help="Aumento aplicado a la base real en días de quincena (14-16 y 29-2).")

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Metas Operativas y Financieras")
# Metas reales ajustadas para Venezuela
target_utr = st.sidebar.slider("Target UTR (Órdenes/Hora):", min_value=1.20, max_value=2.50, value=1.65, step=0.05)
target_cpo = st.sidebar.slider("Target CPO ($):", min_value=0.80, max_value=2.50, value=1.33, step=0.01)

# -------------------------------------------------------------------------
# 4. LÓGICA DE PROYECCIÓN BASADA 100% EN ÓRDENES REALES RECIENTES
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

# Cálculo de horizonte
if sel_horizonte == 'Resto del Mes (MTD)':
    ultimo_dia_mes = pd.date_range(start=inicio_mes_actual, periods=1, freq='ME')[0]
    dias_a_proyectar = (ultimo_dia_mes - max_fecha).days
    if dias_a_proyectar <= 0:
        dias_a_proyectar = 14
elif sel_horizonte == 'Próximos 15 días':
    dias_a_proyectar = 15
else:
    dias_a_proyectar = 30

# MODELO: PROMEDIO POR DÍA DE LA SEMANA TOMANDO LAS ÚLTIMAS 3 SEMANAS DE ÓRDENES REALES
df_21d = df_hist[df_hist['ds_date'] >= (max_fecha - pd.Timedelta(days=21))].copy()
df_21d['day_of_week'] = df_21d['ds_date'].dt.dayofweek

# Patrón real por día de la semana (0=Lunes, 6=Domingo)
real_dow_pattern = df_21d.groupby('day_of_week')['orders_real'].mean().to_dict()
mean_real_21d = df_21d['orders_real'].mean() if len(df_21d) > 0 else 1.0

# Generar la secuencia futura conectando con la realidad
fechas_futuras = [max_fecha + pd.Timedelta(days=i+1) for i in range(dias_a_proyectar)]
y_proj_future = []

# Días con impacto de quincena (14-16 y 29-2)
dias_quincena = {1, 2, 14, 15, 16, 29, 30, 31}

for f in fechas_futuras:
    dow = f.dayofweek
    base_real_day = real_dow_pattern.get(dow, mean_real_21d)
    
    # Aplica multiplicador de quincena únicamente en las fechas de cobro
    mult_q = (1.0 + float(pct_impacto)) if (aplica_quincena and f.day in dias_quincena) else 1.0
    val_proyectado = base_real_day * mult_q
    y_proj_future.append(val_proyectado)

# Totales y Métricas Operativas
orders_totales_proyectadas = int(sum(y_proj_future))
orders_dia_promedio = orders_totales_proyectadas / dias_a_proyectar if dias_a_proyectar > 0 else 0

base_cph = float(df_mtd['cph_diario'].mean()) if len(df_mtd) > 0 and df_mtd['cph_diario'].mean() > 0 else float(df_60d['cph_diario'].mean())
horas_totales_requeridas = int(orders_totales_proyectadas / target_utr) if target_utr > 0 else 0
costo_total_pago = horas_totales_requeridas * base_cph
cpo_proyectado = costo_total_pago / orders_totales_proyectadas if orders_totales_proyectadas > 0 else 0.0

delta_cpo = cpo_proyectado - target_cpo
accuracy_60d = 100.0 - ((np.abs(df_60d['orders_real'] - df_60d['orders_forecast_rooster']).sum() / df_60d['orders_real'].sum()) * 100 if df_60d['orders_real'].sum() > 0 else 0)

# -------------------------------------------------------------------------
# 5. DASHBOARD PRINCIPAL
# -------------------------------------------------------------------------
st.title(f"🚀 Dashboard de Proyección Operativa | {plaza_label}")
st.caption(f"Modelo: Estacionalidad sobre **Órdenes Reales Recientes** (Últimas 3 semanas). Horizonte: **{dias_a_proyectar} días**.")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)

kpi1.metric("📦 Órdenes Proyectadas", f"{orders_totales_proyectadas:,}", f"{int(orders_dia_promedio):,}/día promedio")
kpi2.metric("⏱️ Horas Requeridas", f"{horas_totales_requeridas:,}", f"Target UTR: {target_utr:.2f}")
kpi3.metric("💵 Gasto Total Riders", f"${costo_total_pago:,.2f}", f"CPH Base: ${base_cph:.2f}/h")
kpi4.metric(
    "📉 CPO Proyectado", 
    f"${cpo_proyectado:.2f}", 
    f"{delta_cpo:+.2f} vs Target (${target_cpo:.2f})", 
    delta_color="inverse"
)

st.markdown("---")

st.subheader("📈 Evolución Diaria: Histórico Reales (Últimos 2 Meses) vs. Proyección Reales Futuras")

x_proj = [max_fecha] + fechas_futuras
y_proj = [df_60d[df_60d['ds_date'] == max_fecha]['orders_real'].values[0]] + y_proj_future

fig = go.Figure()

# Línea Histórica Reales
fig.add_trace(go.Scatter(
    x=df_60d['ds_date'], y=df_60d['orders_real'],
    mode='lines+markers', name='Órdenes Reales (Histórico + MTD)',
    line=dict(color='#2563EB', width=2.5),
    marker=dict(size=4)
))

# Línea Forecast Base
fig.add_trace(go.Scatter(
    x=df_60d['ds_date'], y=df_60d['orders_forecast_rooster'],
    mode='lines', name='Forecast Rooster Base',
    line=dict(color='#F59E0B', width=2, dash='dash')
))

# Línea Roja de Proyección Futura (Nacida directamente del histórico real)
fig.add_trace(go.Scatter(
    x=x_proj, y=y_proj,
    mode='lines+markers', name=f'Proyección Reales ({dias_a_proyectar} días)',
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

with st.expander("📋 Ver detalle de datos históricos y proyecciones en tabla"):
    df_display = df_60d[['ds_date', 'orders_real', 'orders_forecast_rooster', 'worked_hours', 'cph_diario']].copy()
    df_display.columns = ['Fecha', 'Órdenes Reales', 'Forecast Rooster', 'Horas Trabajadas', 'CPH ($)']
    st.dataframe(df_display.sort_values('Fecha', ascending=False), use_container_width=True)
