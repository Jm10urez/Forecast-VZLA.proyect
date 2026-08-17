import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# -------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS CSS PROFESIONALES
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
    
    /* ESTILOS PARA MATRIZ ROOSTER PROFESIONAL */
    .rooster-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 6px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .rooster-table th {
        background-color: #0F172A;
        color: #94A3B8;
        padding: 10px;
        font-size: 13px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        border-radius: 6px;
        text-align: center;
    }
    .rooster-table td {
        background-color: #1E293B;
        color: #F8FAFC;
        padding: 10px;
        border-radius: 8px;
        vertical-align: top;
        min-width: 120px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .week-cell {
        background-color: #0F172A !important;
        color: #38BDF8 !important;
        font-weight: bold;
        vertical-align: middle !important;
        text-align: center;
        font-size: 13px;
    }
    .cell-box {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }
    .val-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 12px;
    }
    .lbl-txt { color: #94A3B8; font-size: 11px; }
    .val-base { color: #E2E8F0; font-weight: 500; }
    .val-model { color: #38BDF8; font-weight: 700; font-size: 13px; }
    
    .badge-pos {
        background-color: rgba(16, 185, 129, 0.15);
        color: #34D399;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 11px;
    }
    .badge-neg {
        background-color: rgba(239, 68, 68, 0.15);
        color: #F87171;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 11px;
    }
    .empty-cell {
        color: #475569;
        text-align: center;
        padding: 15px !important;
        font-size: 14px;
    }
    </style>
""", unsafe_allow_html=True)

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
# 3. CONTROLES SIDEBAR (FILTROS DE ROOSTER: HORA, CIUDAD, ZONA)
# -------------------------------------------------------------------------
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/d/d6/PedidosYa_Logo.png", width=180)
st.sidebar.title("⚙️ Filtros de Rooster")

# 1. Filtro Ciudad
ciudades_lista = sorted([str(c) for c in df_real['city_name'].dropna().unique() if str(c) not in ['None', 'nan']])
sel_ciudad = st.sidebar.selectbox("🏙️ Ciudad:", ['TODAS'] + ciudades_lista)

df_temp_ciudad = df_real if sel_ciudad == 'TODAS' else df_real[df_real['city_name'] == sel_ciudad]

# 2. Filtro Zona
col_zona = 'zone_name' if 'zone_name' in df_real.columns else ('subzone_name' if 'subzone_name' in df_real.columns else None)
if col_zona:
    zonas_lista = sorted([str(z) for z in df_temp_ciudad[col_zona].dropna().unique() if str(z) not in ['None', 'nan']])
    sel_zona = st.sidebar.selectbox("📍 Zona / Subzona:", ['TODAS'] + zonas_lista)
else:
    sel_zona = 'TODAS'

# 3. Filtro Hora
col_hora = 'hour' if 'hour' in df_real.columns else ('time_block' if 'time_block' in df_real.columns else None)
if col_hora:
    horas_lista = sorted([int(h) for h in df_temp_ciudad[col_hora].dropna().unique() if pd.notna(h)])
    sel_hora = st.sidebar.selectbox("⏰ Hora:", ['TODAS'] + horas_lista)
else:
    sel_hora = 'TODAS'

st.sidebar.markdown("---")
sel_horizonte = st.sidebar.selectbox("📅 Horizonte de Proyección:", ['Resto del Mes (MTD)', 'Próximos 15 días', 'Próximos 30 días'])

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Metas Operativas")
target_utr = st.sidebar.slider("Target UTR (Órdenes/Hora):", min_value=1.20, max_value=2.50, value=1.65, step=0.05)
target_cpo = st.sidebar.slider("Target CPO ($):", min_value=0.80, max_value=2.50, value=1.33, step=0.01)

# -------------------------------------------------------------------------
# 4. FILTRADO DE DATOS Y LÓGICA DE PROYECCIÓN
# -------------------------------------------------------------------------
df_filtered = df_real.copy()

if sel_ciudad != 'TODAS':
    df_filtered = df_filtered[df_filtered['city_name'] == sel_ciudad]
if col_zona and sel_zona != 'TODAS':
    df_filtered = df_filtered[df_filtered[col_zona] == sel_zona]
if col_hora and sel_hora != 'TODAS':
    df_filtered = df_filtered[df_filtered[col_hora] == sel_hora]

# Agrupación diaria
df_hist = df_filtered.groupby('ds_date').agg({
    'orders_forecast_rooster': 'sum',
    'orders_real': 'sum',
    'worked_hours': 'sum',
    'rider_payments': 'first' if 'rider_payments' in df_filtered.columns else 'sum'
}).reset_index()

df_hist['cph_diario'] = np.where(df_hist['worked_hours'] > 0, df_hist.get('rider_payments', 0) / df_hist['worked_hours'], 0.0)
df_hist = df_hist.sort_values('ds_date').copy()

p_limite_inf = 50 if sel_ciudad != 'TODAS' else 2000
df_valid_reales = df_hist[df_hist['orders_real'] >= p_limite_inf].copy()

if len(df_valid_reales) > 0:
    max_fecha_real = df_valid_reales['ds_date'].max()
    ultimo_val_real = df_valid_reales[df_valid_reales['ds_date'] == max_fecha_real]['orders_real'].values[0]
else:
    max_fecha_real = df_hist['ds_date'].max()
    ultimo_val_real = df_hist[df_hist['ds_date'] == max_fecha_real]['orders_forecast_rooster'].values[0]

df_60d = df_hist[(df_hist['ds_date'] >= (max_fecha_real - pd.Timedelta(days=60))) & (df_hist['ds_date'] <= max_fecha_real)].copy()
inicio_mes_actual = max_fecha_real.replace(day=1)
df_mtd = df_60d[(df_60d['ds_date'] >= inicio_mes_actual) & (df_60d['orders_real'] >= p_limite_inf)]
orders_acumuladas_mtd = int(df_mtd['orders_real'].sum())

if sel_horizonte == 'Resto del Mes (MTD)':
    ultimo_dia_mes = pd.date_range(start=inicio_mes_actual, periods=1, freq='ME')[0]
    dias_a_proyectar = (ultimo_dia_mes - max_fecha_real).days
    if dias_a_proyectar <= 0:
        dias_a_proyectar = 14
elif sel_horizonte == 'Próximos 15 días':
    dias_a_proyectar = 15
else:
    dias_a_proyectar = 30

# DOW BASELINE
df_28d_clean = df_valid_reales[df_valid_reales['ds_date'] >= (max_fecha_real - pd.Timedelta(days=28))].copy()
df_28d_clean['dow'] = df_28d_clean['ds_date'].dt.dayofweek

real_dow_avg = df_28d_clean.groupby('dow')['orders_real'].mean().to_dict()
real_dow_std = df_28d_clean.groupby('dow')['orders_real'].std().to_dict()

# Corrección Sábado > Domingo
val_sabado = real_dow_avg.get(5, df_28d_clean['orders_real'].mean() if len(df_28d_clean)>0 else 100)
val_domingo = real_dow_avg.get(6, df_28d_clean['orders_real'].mean() if len(df_28d_clean)>0 else 100)

if val_domingo >= val_sabado:
    real_dow_avg[6] = val_sabado * 0.88

factor_calibracion_target = 1.0303
fechas_futuras = [max_fecha_real + pd.Timedelta(days=i+1) for i in range(dias_a_proyectar)]
y_proj_future = []

np.random.seed(101)

for i, f in enumerate(fechas_futuras):
    dow = f.dayofweek
    base_dow = real_dow_avg.get(dow, df_28d_clean['orders_real'].mean() if len(df_28d_clean)>0 else 100)
    std_dow = real_dow_std.get(dow, 25.0)
    if pd.isna(std_dow): std_dow = 25.0
    
    ruido_organico = np.random.normal(0, std_dow * 0.25)
    dia_mes = f.day
    factor_fase_mes = 0.985 if (1 <= dia_mes <= 7 or 16 <= dia_mes <= 22) else 1.015
        
    if dia_mes in [15, 30, 31]:
        mult_q = 1.15 if dow == 5 else (1.08 if dow == 6 else 1.12)
    elif dia_mes in [1, 16]:
        mult_q = 1.12 if dow == 5 else (1.06 if dow == 6 else 1.10)
    elif dia_mes in [2, 14, 28, 29]:
        mult_q = 1.06
    else:
        mult_q = 1.0

    val_raw = (base_dow + ruido_organico) * factor_calibracion_target * factor_fase_mes * mult_q
    y_proj_future.append(val_raw)

orders_totales_proyectadas = int(sum(y_proj_future))
orders_dia_promedio = orders_totales_proyectadas / dias_a_proyectar if dias_a_proyectar > 0 else 0
estimacion_cierre_mes = orders_acumuladas_mtd + orders_totales_proyectadas if sel_horizonte == 'Resto del Mes (MTD)' else orders_totales_proyectadas

# -------------------------------------------------------------------------
# 5. DASHBOARD PRINCIPAL
# -------------------------------------------------------------------------
st.title("🚀 Dashboard de Proyección Operativa | Matriz Rooster")
st.caption(f"Filtros Activos: Ciudad: **{sel_ciudad}** | Zona: **{sel_zona}** | Hora: **{sel_hora}**")

kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric("🏁 Est. Cierre Mensual", f"{estimacion_cierre_mes:,}", "MTD + Proyección")
kpi2.metric("📦 Resto del Mes", f"{orders_totales_proyectadas:,}", f"{int(orders_dia_promedio):,}/día prom")
kpi3.metric("🎯 Target UTR", f"{target_utr:.2f}")

st.markdown("---")

# -------------------------------------------------------------------------
# 6. CONSTRUCCIÓN DE MATRIZ HTML LIMPIA Y ELEGANTE
# -------------------------------------------------------------------------
st.subheader("📅 Matriz Semanal Comparativa (Rooster Base vs. Modelo Ajustado)")

df_grid_hist = df_hist[['ds_date', 'orders_forecast_rooster', 'orders_real']].copy()
df_grid_hist.columns = ['ds_date', 'rooster', 'sugerido']

# Base Rooster futura de referencia (Promedio histórico reciente si no hay forecast futuro disponible)
val_rooster_ref = df_grid_hist['rooster'].tail(14).mean() if len(df_grid_hist) > 0 else 6801.0

df_grid_fut = pd.DataFrame({
    'ds_date': fechas_futuras,
    'rooster': [val_rooster_ref]*len(fechas_futuras),
    'sugerido': y_proj_future
})

df_grid_all = pd.concat([df_grid_hist, df_grid_fut], ignore_index=True)
df_grid_all['ds_date'] = pd.to_datetime(df_grid_all['ds_date'])

df_grid_all['week_start'] = df_grid_all['ds_date'].apply(lambda d: d - pd.Timedelta(days=d.weekday()))
df_grid_all['dow_name'] = df_grid_all['ds_date'].dt.strftime('%A')

dias_semana = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
dias_espanol = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

semanas_unicas = sorted(df_grid_all['week_start'].unique(), reverse=True)[:5]

# Renderizar Tabla HTML nativa con CSS
html_table = '<table class="rooster-table">'
html_table += '<thead><tr><th>Semanas</th>' + ''.join([f'<th>{d}</th>' for d in dias_espanol]) + '</tr></thead><tbody>'

for sem in semanas_unicas:
    html_table += f'<tr><td class="week-cell">{sem.strftime("%Y-%m-%d")}</td>'
    df_sem = df_grid_all[df_grid_all['week_start'] == sem]
    
    for dow in dias_semana:
        match = df_sem[df_sem['dow_name'] == dow]
        if len(match) > 0:
            val_rooster = match['rooster'].values[0]
            val_sug = match['sugerido'].values[0]
            var_pct = ((val_sug - val_rooster) / val_rooster * 100) if val_rooster > 0 else 0.0
            
            signo = "+" if var_pct >= 0 else ""
            badge_class = "badge-pos" if var_pct >= 0 else "badge-neg"
            
            cell_content = f'''
            <td>
                <div class="cell-box">
                    <div class="val-row">
                        <span class="lbl-txt">Rooster:</span>
                        <span class="val-base">{int(val_rooster):,}</span>
                    </div>
                    <div class="val-row">
                        <span class="lbl-txt">Ajustado:</span>
                        <span class="val-model">{int(val_sug):,}</span>
                    </div>
                    <div style="text-align: right; margin-top: 4px;">
                        <span class="{badge_class}">{signo}{var_pct:.1f}%</span>
                    </div>
                </div>
            </td>
            '''
            html_table += cell_content
        else:
            html_table += '<td class="empty-cell">-</td>'
            
    html_table += '</tr>'

html_table += '</tbody></table>'

st.markdown(html_table, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# -------------------------------------------------------------------------
# 7. GRÁFICA DE EVOLUCIÓN DIARIA
# -------------------------------------------------------------------------
st.subheader("📈 Evolución Diaria: Histórico Reales vs. Proyección Futura")

x_proj = [max_fecha_real] + fechas_futuras
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
    height=420,
    template='plotly_white',
    hovermode='x unified',
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=20, r=20, t=30, b=20)
)

st.plotly_chart(fig, use_container_width=True)
