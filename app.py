import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# -------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS
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

if 'eventos_custom' not in st.session_state:
    st.session_state['eventos_custom'] = []

# -------------------------------------------------------------------------
# 2. CARGA DE DATOS DESDE ARCHIVO LOCAL CSV CON DETECCIÓN FLEXIBLE DE COLUMNAS
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

# Función para encontrar columnas de forma flexible (case-insensitive)
def buscar_columna(df, posibles_nombres):
    cols_lower = {c.lower(): c for c in df.columns}
    for p in posibles_nombres:
        if p.lower() in cols_lower:
            return cols_lower[p.lower()]
    return None

col_ciudad = buscar_columna(df_real, ['city_name', 'city', 'ciudad'])
col_zona = buscar_columna(df_real, ['zone_name', 'zone', 'subzone_name', 'subzone', 'zona'])
col_hora = buscar_columna(df_real, ['hour', 'hora', 'time_block', 'time_hour', 'time'])

# -------------------------------------------------------------------------
# 3. CONTROLES SIDEBAR (CONFIGURACIÓN GLOBAL Y EVENTOS AD-HOC)
# -------------------------------------------------------------------------
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/d/d6/PedidosYa_Logo.png", width=180)
st.sidebar.title("⚙️ Configuración Global")

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
# 4. LÓGICA DE PROYECCIÓN GLOBAL CALIBRADA (~232K)
# -------------------------------------------------------------------------
df_hist_global = df_real.groupby('ds_date').agg({
    'orders_forecast_rooster': 'sum',
    'orders_real': 'sum',
    'worked_hours': 'sum',
    'rider_payments': 'first' if 'rider_payments' in df_real.columns else 'sum'
}).reset_index()

df_hist_global['cph_diario'] = np.where(df_hist_global['worked_hours'] > 0, df_hist_global.get('rider_payments', 0) / df_hist_global['worked_hours'], 0.0)
df_hist_global = df_hist_global.sort_values('ds_date').copy()

p_limite_inf = 2000
df_valid_reales = df_hist_global[df_hist_global['orders_real'] >= p_limite_inf].copy()

if len(df_valid_reales) > 0:
    max_fecha_real = df_valid_reales['ds_date'].max()
    ultimo_val_real = df_valid_reales[df_valid_reales['ds_date'] == max_fecha_real]['orders_real'].values[0]
else:
    max_fecha_real = df_hist_global['ds_date'].max()
    ultimo_val_real = df_hist_global[df_hist_global['ds_date'] == max_fecha_real]['orders_forecast_rooster'].values[0]

inicio_mes_actual = max_fecha_real.replace(day=1)
df_mtd_ejecutado = df_valid_reales[(df_valid_reales['ds_date'] >= inicio_mes_actual) & (df_valid_reales['ds_date'] <= max_fecha_real)]
orders_acumuladas_mtd = int(df_mtd_ejecutado['orders_real'].sum())

if sel_horizonte == 'Resto del Mes (MTD)':
    ultimo_dia_mes = pd.date_range(start=inicio_mes_actual, periods=1, freq='ME')[0]
    fechas_futuras = pd.date_range(start=max_fecha_real + pd.Timedelta(days=1), end=ultimo_dia_mes)
    dias_a_proyectar = len(fechas_futuras)
elif sel_horizonte == 'Próximos 15 días':
    fechas_futuras = pd.date_range(start=max_fecha_real + pd.Timedelta(days=1), periods=15)
    dias_a_proyectar = 15
else:
    fechas_futuras = pd.date_range(start=max_fecha_real + pd.Timedelta(days=1), periods=30)
    dias_a_proyectar = 30

df_60d = df_hist_global[(df_hist_global['ds_date'] >= (max_fecha_real - pd.Timedelta(days=60))) & (df_hist_global['ds_date'] <= max_fecha_real)].copy()

df_28d_clean = df_valid_reales[df_valid_reales['ds_date'] >= (max_fecha_real - pd.Timedelta(days=28))].copy()
df_28d_clean['dow'] = df_28d_clean['ds_date'].dt.dayofweek

real_dow_avg = df_28d_clean.groupby('dow')['orders_real'].mean().to_dict()
real_dow_std = df_28d_clean.groupby('dow')['orders_real'].std().to_dict()

dict_eventos = {e['fecha']: e['impacto_pct'] for e in st.session_state['eventos_custom']}

y_proj_raw = []
np.random.seed(101)

ult_viernes_raw = real_dow_avg.get(4, 9000)

for f in fechas_futuras:
    dow = f.dayofweek
    std_dow = real_dow_std.get(dow, 200.0)
    if pd.isna(std_dow): std_dow = 200.0
    
    ruido_organico = np.random.normal(0, std_dow * 0.10)
    dia_mes = f.day
    
    is_quincena = dia_mes in [14, 15, 16, 28, 29, 30, 31, 1, 2]
    
    if is_quincena:
        if dow == 4: mult_q = 1.30
        elif dow in [0, 1, 2, 3]: mult_q = 1.10
        else: mult_q = 1.15
    else:
        if dow in [0, 1, 2]: mult_q = 0.86
        elif dow in [3, 4]: mult_q = 0.94
        else: mult_q = 0.95

    f_str = f.strftime('%Y-%m-%d')
    impacto_adhoc = dict_eventos.get(f_str, 0.0)
    mult_adhoc = 1.0 + impacto_adhoc

    if dow == 4:
        val = (real_dow_avg.get(4, 9000) + ruido_organico) * mult_q * mult_adhoc
        ult_viernes_raw = val
    elif dow == 5:
        val = ult_viernes_raw * 0.88 * mult_adhoc
    elif dow == 6:
        val = ult_viernes_raw * 0.88 * 0.82 * mult_adhoc
    else:
        val = (real_dow_avg.get(dow, 6800) + ruido_organico) * mult_q * mult_adhoc

    y_proj_raw.append(val)

TARGET_MES_EXACTO = 232000
falta_exacto = (TARGET_MES_EXACTO - orders_acumuladas_mtd) if sel_horizonte == 'Resto del Mes (MTD)' else TARGET_MES_EXACTO
sum_raw = sum(y_proj_raw)
factor_exactitud = (falta_exacto / sum_raw) if sum_raw > 0 else 1.0
y_proj_future = [min(v * factor_exactitud, 9600.0) for v in y_proj_raw]

orders_totales_proyectadas = int(round(sum(y_proj_future)))
orders_dia_promedio = orders_totales_proyectadas / dias_a_proyectar if dias_a_proyectar > 0 else 0

if sel_horizonte == 'Resto del Mes (MTD)' and orders_acumuladas_mtd > 0:
    estimacion_cierre_mes = orders_acumuladas_mtd + orders_totales_proyectadas
else:
    estimacion_cierre_mes = orders_totales_proyectadas

base_cph = float(df_mtd_ejecutado['cph_diario'].mean()) if len(df_mtd_ejecutado) > 0 and df_mtd_ejecutado['cph_diario'].mean() > 0 else float(df_60d['cph_diario'].mean())
horas_totales_requeridas = int(orders_totales_proyectadas / target_utr) if target_utr > 0 else 0
costo_total_pago = horas_totales_requeridas * base_cph
cpo_proyectado = costo_total_pago / orders_totales_proyectadas if orders_totales_proyectadas > 0 else 0.0

delta_cpo = cpo_proyectado - target_cpo

# -------------------------------------------------------------------------
# 5. DASHBOARD PRINCIPAL Y KPIS GLOBALES
# -------------------------------------------------------------------------
st.title("🚀 Dashboard de Proyección Operativa | PedidosYa VE")
st.caption(f"Modelo Calibrado a Target ~232K. MTD Acumulado: **{orders_acumuladas_mtd:,}**.")

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

# -------------------------------------------------------------------------
# 6. FILTROS EXCLUSIVOS PARA LAS TABLAS (CIUDAD, ZONA Y HORA SIEMPRE VISIBLES)
# -------------------------------------------------------------------------
with st.expander("🔍 **Filtros Exclusivos para Tablas de Forecast y Sugerido**", expanded=True):
    f_col1, f_col2, f_col3 = st.columns(3)
    
    # 1. Filtro Ciudad
    if col_ciudad:
        ciudades_lista = sorted([str(c) for c in df_real[col_ciudad].dropna().unique() if str(c) not in ['None', 'nan']])
    else:
        ciudades_lista = []
    sel_ciudad_tbl = f_col1.selectbox("🏙️ Ciudad (Tablas):", ['TODAS'] + ciudades_lista)

    df_temp_ciudad = df_real if (not col_ciudad or sel_ciudad_tbl == 'TODAS') else df_real[df_real[col_ciudad] == sel_ciudad_tbl]

    # 2. Filtro Zona
    if col_zona:
        zonas_lista = sorted([str(z) for z in df_temp_ciudad[col_zona].dropna().unique() if str(z) not in ['None', 'nan']])
    else:
        zonas_lista = []
    sel_zona_tbl = f_col2.selectbox("📍 Zona / Subzona (Tablas):", ['TODAS'] + zonas_lista)

    # 3. Filtro Hora
    if col_hora:
        horas_lista = sorted([str(h) for h in df_temp_ciudad[col_hora].dropna().unique() if str(h) not in ['None', 'nan']])
    else:
        horas_lista = []
    sel_hora_tbl = f_col3.selectbox("⏰ Hora (Tablas):", ['TODAS'] + horas_lista)

# Aplicar filtrado a los datos
df_filtered_tbl = df_real.copy()
if col_ciudad and sel_ciudad_tbl != 'TODAS':
    df_filtered_tbl = df_filtered_tbl[df_filtered_tbl[col_ciudad] == sel_ciudad_tbl]
if col_zona and sel_zona_tbl != 'TODAS':
    df_filtered_tbl = df_filtered_tbl[df_filtered_tbl[col_zona] == sel_zona_tbl]
if col_hora and sel_hora_tbl != 'TODAS':
    df_filtered_tbl = df_filtered_tbl[df_filtered_tbl[col_hora] == sel_hora_tbl]

df_hist_tbl = df_filtered_tbl.groupby('ds_date').agg({
    'orders_forecast_rooster': 'sum',
    'orders_real': 'sum'
}).reset_index()

# -------------------------------------------------------------------------
# CONSTRUCCIÓN DE MATRICES SEMANALES CON FILTROS APLICADOS
# -------------------------------------------------------------------------
map_proyeccion = {f.strftime('%Y-%m-%d'): y_proj_future[idx] for idx, f in enumerate(fechas_futuras)}

todas_fechas = pd.date_range(start=df_hist_global['ds_date'].min(), end=fechas_futuras[-1])
df_grid_base = pd.DataFrame({'ds_date': todas_fechas})

df_grid_all = pd.merge(df_grid_base, df_hist_tbl[['ds_date', 'orders_forecast_rooster', 'orders_real']], on='ds_date', how='left')

val_rooster_ref = df_hist_tbl['orders_forecast_rooster'].tail(14).mean() if len(df_hist_tbl) > 0 else 6801.0
df_grid_all['rooster'] = df_grid_all['orders_forecast_rooster'].fillna(val_rooster_ref)

def obtener_sugerido(row):
    f_str = row['ds_date'].strftime('%Y-%m-%d')
    if f_str in map_proyeccion:
        return map_proyeccion[f_str]
    elif pd.notna(row['orders_real']) and row['orders_real'] > 0:
        return row['orders_real']
    else:
        return row['rooster']

df_grid_all['sugerido'] = df_grid_all.apply(obtener_sugerido, axis=1)

df_grid_all['week_start'] = df_grid_all['ds_date'].apply(lambda d: d - pd.Timedelta(days=d.weekday()))
df_grid_all['dow_name'] = df_grid_all['ds_date'].dt.strftime('%A')

dias_semana = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
dias_espanol = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

semanas_unicas = sorted(df_grid_all['week_start'].unique(), reverse=True)[:5]

# --- CUADRO 1: FORECAST BASE DE ROOSTER ---
st.subheader("📊 1. Forecast Base de Rooster (Filtrado)")

headers_r = st.columns([1.2, 1, 1, 1, 1, 1, 1, 1])
headers_r[0].markdown("**Semana**")
for idx, d_es in enumerate(dias_espanol):
    headers_r[idx + 1].markdown(f"**{d_es}**")

st.divider()

for sem in semanas_unicas:
    cols = st.columns([1.2, 1, 1, 1, 1, 1, 1, 1])
    cols[0].markdown(f"🗓️ **{sem.strftime('%Y-%m-%d')}**")
    
    df_sem = df_grid_all[df_grid_all['week_start'] == sem]
    
    for idx, dow in enumerate(dias_semana):
        match = df_sem[df_sem['dow_name'] == dow]
        col_target = cols[idx + 1]
        
        if len(match) > 0 and match['rooster'].values[0] > 0:
            val_rooster = match['rooster'].values[0]
            with col_target.container(border=True):
                st.caption("Rooster")
                st.markdown(f"**{int(val_rooster):,}**")
        else:
            col_target.caption("-")

st.markdown("<br><br>", unsafe_allow_html=True)

# --- CUADRO 2: SUGERIDO DEL MODELO (AJUSTADO) ---
st.subheader("📈 2. Sugerido del Modelo (Calibrado)")

headers_s = st.columns([1.2, 1, 1, 1, 1, 1, 1, 1])
headers_s[0].markdown("**Semana**")
for idx, d_es in enumerate(dias_espanol):
    headers_s[idx + 1].markdown(f"**{d_es}**")

st.divider()

for sem in semanas_unicas:
    cols = st.columns([1.2, 1, 1, 1, 1, 1, 1, 1])
    cols[0].markdown(f"🗓️ **{sem.strftime('%Y-%m-%d')}**")
    
    df_sem = df_grid_all[df_grid_all['week_start'] == sem]
    
    for idx, dow in enumerate(dias_semana):
        match = df_sem[df_sem['dow_name'] == dow]
        col_target = cols[idx + 1]
        
        if len(match) > 0 and match['sugerido'].values[0] > 0:
            val_rooster = match['rooster'].values[0]
            val_sug = match['sugerido'].values[0]
            var_pct = ((val_sug - val_rooster) / val_rooster * 100) if val_rooster > 0 else 0.0
            
            signo = "+" if var_pct >= 0 else ""
            color_pct = "green" if var_pct >= 0 else "red"
            
            with col_target.container(border=True):
                st.caption("Sugerido")
                st.markdown(f"**:blue[{int(val_sug):,}]**")
                st.markdown(f":{color_pct}[**{signo}{var_pct:.1f}%**]")
        else:
            col_target.caption("-")

st.markdown("<br>", unsafe_allow_html=True)

# -------------------------------------------------------------------------
# 7. GRÁFICA DE EVOLUCIÓN DIARIA CONSOLIDADA
# -------------------------------------------------------------------------
st.subheader("📈 Evolución Diaria: Histórico Reales vs. Proyección Futura Calibrada")

x_proj = [max_fecha_real] + list(fechas_futuras)
y_proj = [ultimo_val_real] + y_proj_future

fig = go.Figure()

fig.add_trace(go.Scatter(
    x=df_60d['ds_date'], y=df_60d['orders_real'],
    mode='lines+markers', name='Órdenes Reales (Histórico)',
    line=dict(color='#2563EB', width=2.5),
    marker=dict(size=4)
))

fig.add_trace(go.Scatter(
    x=df_60d['ds_date'], y=df_60d['orders_forecast_rooster'],
    mode='lines', name='Forecast Rooster Base',
    line=dict(color='#F59E0B', width=2, dash='dash')
))

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
