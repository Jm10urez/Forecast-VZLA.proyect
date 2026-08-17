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

# Inicializar Session State para eventos ad-hoc
if 'eventos_custom' not in st.session_state:
    st.session_state['eventos_custom'] = []

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
st.sidebar.subheader("🎯 Metas Operativas")
target_utr = st.sidebar.slider("Target UTR (Órdenes/Hora):", min_value=1.20, max_value=2.50, value=1.65, step=0.05)
target_cpo = st.sidebar.slider("Target CPO ($):", min_value=0.80, max_value=2.50, value=1.33, step=0.01)

st.sidebar.markdown("---")
st.sidebar.subheader("🌧️ Modificadores Ad-Hoc / Clustered Events")

with st.sidebar.expander("➕ Agregar Impacto Específico por Día", expanded=False):
    df_valid_temp = df_real[df_real['orders_real'] > 500]
    max_date_temp = df_valid_temp['ds_date'].max() if len(df_valid_temp) > 0 else df_real['ds_date'].max()
    dias_opciones = [(max_date_temp + pd.Timedelta(days=i+1)).strftime('%Y-%m-%d') for i in range(30)]
    
    fecha_evt = st.selectbox("Fecha del Evento:", dias_opciones)
    tipo_evt = st.selectbox("Cluster / Motivo:", [
        "Lluvia Fuerte 🌧️",
        "Lluvia Moderada 🌦️",
        "Feriado / Festivo 🎆",
        "Promoción Agresiva 🚀",
        "Falla Eléctrica / Conectividad ⚡",
        "Cierre Preventivo / Contingencia 🛑"
    ])
    direccion_evt = st.radio("Dirección del Impacto:", ["Positivo (+)", "Negativo (-)"])
    pct_evt = st.slider("Porcentaje de Impacto (%):", min_value=1, max_value=50, value=15, step=1)

    if st.button("📌 Añadir Evento"):
        mult_signo = (pct_evt / 100.0) if direccion_evt == "Positivo (+)" else -(pct_evt / 100.0)
        st.session_state['eventos_custom'].append({
            "fecha": fecha_evt,
            "tipo": tipo_evt,
            "impacto_pct": mult_signo
        })
        st.success(f"Evento añadido para {fecha_evt}")

if len(st.session_state['eventos_custom']) > 0:
    st.sidebar.markdown("**Eventos Activos:**")
    for idx, e in enumerate(st.session_state['eventos_custom']):
        signo_txt = f"+{e['impacto_pct']*100:.0f}%" if e['impacto_pct'] > 0 else f"{e['impacto_pct']*100:.0f}%"
        st.sidebar.caption(f"• **{e['fecha']}**: {e['tipo']} ({signo_txt})")
    if st.sidebar.button("🗑️ Limpiar Todos los Eventos"):
        st.session_state['eventos_custom'] = []
        st.rerun()

# -------------------------------------------------------------------------
# 4. LÓGICA DE PROYECCIÓN REALISTA Y ACOTADA
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
    p_limite_inf = 2000  # Descartar días atípicos caídos a nivel nacional (<2k)
else:
    df_hist = df_real[df_real['city_name'] == sel_ciudad].groupby('ds_date').agg({
        'orders_forecast_rooster': 'sum',
        'orders_real': 'sum',
        'worked_hours': 'sum',
        'cph_diario': 'mean'
    }).reset_index()
    plaza_label = sel_ciudad
    p_limite_inf = 100

df_hist = df_hist.sort_values('ds_date').copy()

# FILTRO ESTRICTO DE ATÍPICOS (Excluye 25 de junio y días con datos incompletos/parciales)
df_valid_reales = df_hist[df_hist['orders_real'] >= p_limite_inf].copy()

if len(df_valid_reales) > 0:
    max_fecha_real = df_valid_reales['ds_date'].max()
    ultimo_val_real = df_valid_reales[df_valid_reales['ds_date'] == max_fecha_real]['orders_real'].values[0]
else:
    max_fecha_real = df_hist['ds_date'].max()
    ultimo_val_real = df_hist[df_hist['ds_date'] == max_fecha_real]['orders_forecast_rooster'].values[0]

# Historia visible de 60 días
df_60d = df_hist[(df_hist['ds_date'] >= (max_fecha_real - pd.Timedelta(days=60))) & (df_hist['ds_date'] <= max_fecha_real)].copy()
inicio_mes_actual = max_fecha_real.replace(day=1)
df_mtd = df_60d[(df_60d['ds_date'] >= inicio_mes_actual) & (df_60d['orders_real'] >= p_limite_inf)]
orders_acumuladas_mtd = int(df_mtd['orders_real'].sum())

# Horizonte
if sel_horizonte == 'Resto del Mes (MTD)':
    ultimo_dia_mes = pd.date_range(start=inicio_mes_actual, periods=1, freq='ME')[0]
    dias_a_proyectar = (ultimo_dia_mes - max_fecha_real).days
    if dias_a_proyectar <= 0:
        dias_a_proyectar = 14
elif sel_horizonte == 'Próximos 15 días':
    dias_a_proyectar = 15
else:
    dias_a_proyectar = 30

# PROMEDIO DE ÓRDENES REALES POR DÍA DE LA SEMANA (Últimas 4 semanas limpias)
df_28d_clean = df_valid_reales[df_valid_reales['ds_date'] >= (max_fecha_real - pd.Timedelta(days=28))].copy()
df_28d_clean['dow'] = df_28d_clean['ds_date'].dt.dayofweek

# Perfil base de órdenes reales por día de la semana
real_dow_avg = df_28d_clean.groupby('dow')['orders_real'].mean().to_dict()

# Máximo histórico real registrado en días limpios para poner techo realista
max_historico_real = df_valid_reales['orders_real'].max() if len(df_valid_reales) > 0 else 9600.0

# Mapa de eventos ad-hoc
dict_eventos = {e['fecha']: e['impacto_pct'] for e in st.session_state['eventos_custom']}

# PROYECCIÓN FUTURA FIDELIGNA Y ACOTADA
fechas_futuras = [max_fecha_real + pd.Timedelta(days=i+1) for i in range(dias_a_proyectar)]
y_proj_future = []
dias_quincena = {1, 2, 14, 15, 16, 28, 29, 30, 31}

for f in fechas_futuras:
    # Base tomada directamente de la media real de ese día de la semana
    base_dia = real_dow_avg.get(f.dayofweek, df_28d_clean['orders_real'].mean())
    
    # Impacto de Quincena controlado (Ajuste suave sin disparar la curva)
    if f.day in dias_quincena:
        if f.dayofweek == 4:  # Viernes de quincena
            mult_q = 1.15
        elif f.dayofweek in [5, 6]:  # Fin de semana de quincena
            mult_q = 1.12
        else:  # Día hábil de quincena
            mult_q = 1.08
    else:
        mult_q = 1.0

    # Modificador Ad-Hoc
    f_str = f.strftime('%Y-%m-%d')
    impacto_adhoc = dict_eventos.get(f_str, 0.0)
    mult_adhoc = 1.0 + impacto_adhoc

    val_proyectado = base_dia * mult_q * mult_adhoc
    
    # Techo de seguridad: Nunca sobrepasar el récord histórico real (+3% de margen)
    val_proyectado_acotado = min(val_proyectado, max_historico_real * 1.03)
    y_proj_future.append(val_proyectado_acotado)

# Totales y Métricas Operativas
orders_totales_proyectadas = int(sum(y_proj_future))
orders_dia_promedio = orders_totales_proyectadas / dias_a_proyectar if dias_a_proyectar > 0 else 0

# Estimación Cierre Mensual
estimacion_cierre_mes = orders_acumuladas_mtd + orders_totales_proyectadas if sel_horizonte == 'Resto del Mes (MTD)' else orders_totales_proyectadas

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
st.caption(f"Modelo: Comportamiento Real Histórico Limpio (Acotado a Techo Operativo Real). MTD Acumulado: **{orders_acumuladas_mtd:,}**. Último día real: **{max_fecha_real.strftime('%Y-%m-%d')}**.")

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

kpi1.metric("🏁 Est. Cierre Mensual", f"{estimacion_cierre_mes:,}", "MTD + Proyección")
kpi2.metric("📦 Proyección Resto Mes", f"{orders_totales_proyectadas:,}", f"{int(orders_dia_promedio):,}/día prom")
kpi3.metric("⏱️ Horas Requeridas", f"{horas_totales_requeridas:,}", f"Target UTR: {target_utr:.2f}")
kpi4.metric("💵 Gasto Total Riders", f"${costo_total_pago:,.2f}", f"CPH Base: ${base_cph:.2f}/h")
kpi5.metric(
    "📉 CPO Proyectado", 
    f"${cpo_proyectado:.2f}", 
    f"{delta_cpo:+.2f} vs Target (${target_cpo:.2f})", 
    delta_color="inverse"
)

st.markdown("---")

st.subheader("📈 Evolución Diaria: Histórico Reales vs. Proyección Futura Fideligna")

x_proj = [max_fecha_real] + fechas_futuras
y_proj = [ultimo_val_real] + y_proj_future

fig = go.Figure()

# Línea Histórica Reales
fig.add_trace(go.Scatter(
    x=df_60d['ds_date'], y=df_60d['orders_real'],
    mode='lines+markers', name='Órdenes Reales (Histórico)',
    line=dict(color='#2563EB', width=2.5),
    marker=dict(size=4)
))

# Línea Forecast Base
fig.add_trace(go.Scatter(
    x=df_60d['ds_date'], y=df_60d['orders_forecast_rooster'],
    mode='lines', name='Forecast Rooster Base',
    line=dict(color='#F59E0B', width=2, dash='dash')
))

# Línea Roja Proyectada Realista
fig.add_trace(go.Scatter(
    x=x_proj, y=y_proj,
    mode='lines+markers', name=f'Proyección Modelo ({dias_a_proyectar} días)',
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
