import os
import streamlit as st
from src.core.reader import MseedReader
from src.core.event_grouper import EventGrouper
from src.modules.visualizer import WaveformVisualizer
from src.utils.time_utils import format_utc_display, format_duration

st.set_page_config(
    page_title="RSA — Event Analyzer",
    page_icon="🌋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados para la interfaz RSA
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #FF6B35;
        margin-bottom: 0rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #90A4AE;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🌋 RSA — Event Analyzer</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Red Sísmica del Austro — Sistema Web Modular de Visualización y Análisis Multiestación</div>', unsafe_allow_html=True)

data_dir = os.environ.get("DATA_DIR", "/data/events")

@st.cache_data(ttl=300)
def load_and_group_events(path: str):
    reader = MseedReader(data_dir=path)
    files = reader.scan()
    grouper = EventGrouper(window_s=30.0)
    events = grouper.group(files)
    return files, events

# Carga de datos
with st.spinner("Parseando metadatos de eventos sísmicos en Google Drive..."):
    files, events = load_and_group_events(data_dir)

if not events:
    st.error(f"No se encontraron eventos sísmicos en el directorio `{data_dir}`. Por favor verifica que el volumen de Google Drive esté correctamente montado.")
    st.stop()

# ==============================================================================
# BARRA LATERAL — CONFIGURACIÓN Y DSP
# ==============================================================================
st.sidebar.title("🎛️ Panel de Control")

# Botón para forzar recarga del índice de archivos
if st.sidebar.button("🔄 Recargar Índice de Eventos"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Selección de Evento Regional")

# Opciones formateadas para el dropdown de eventos
event_options = {
    f"{evt.event_id} | {format_utc_display(evt.reference_time_utc)} ({evt.n_stations} est.)": evt
    for evt in events
}

selected_option_label = st.sidebar.selectbox(
    "Selecciona un Evento Regional:",
    options=list(event_options.keys()),
    index=0
)

selected_event = event_options[selected_option_label]

st.sidebar.markdown("---")
st.sidebar.subheader("📡 Estaciones a Visualizar")

available_stations = sorted(list(selected_event.stations.keys()))
selected_stations = st.sidebar.multiselect(
    "Filtrar Estaciones:",
    options=available_stations,
    default=available_stations
)

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Procesamiento de Señal (DSP)")

apply_detrend = st.sidebar.checkbox(
    "Remover Tendencia / Media (Detrend)",
    value=True,
    help="Remueve la media de la señal y la tendencia lineal antes del desplegado."
)

apply_bandpass = st.sidebar.checkbox(
    "Filtro Pasabanda Butterworth",
    value=False,
    help="Aplica un filtro pasabanda de 4to orden con fase cero."
)

freq_min, freq_max = 0.5, 20.0
if apply_bandpass:
    col_f1, col_f2 = st.sidebar.columns(2)
    freq_min = col_f1.number_input("F. Mín (Hz)", min_value=0.01, max_value=20.0, value=0.5, step=0.1)
    freq_max = col_f2.number_input("F. Máx (Hz)", min_value=0.1, max_value=100.0, value=20.0, step=1.0)

# ==============================================================================
# PANEL PRINCIPAL — MÉTRICAS Y GRÁFICOS
# ==============================================================================

# Métricas de cabecera
col_m1, col_m2, col_m3, col_m4 = st.columns(4)

col_m1.metric("📍 Evento Regional", selected_event.event_id, format_utc_display(selected_event.reference_time_utc))
col_m2.metric("📡 Estaciones Seleccionadas", f"{len(selected_stations)} / {selected_event.n_stations}", f"Total en red: {len(available_stations)}")
col_m3.metric("⏱️ Duración del Registro", format_duration(selected_event.duration_seconds))

# Generar gráfico Plotly mediante WaveformVisualizer
visualizer = WaveformVisualizer()

with st.spinner("Cargando y procesando trazas sísmicas MiniSEED..."):
    fig, metrics = visualizer.create_event_figure(
        regional_event=selected_event,
        selected_stations=selected_stations,
        apply_detrend=apply_detrend,
        apply_bandpass=apply_bandpass,
        freq_min=freq_min,
        freq_max=freq_max
    )

col_m4.metric("📈 PGA Z Estimado", f"{metrics.get('pga_z', 0.0):.2f}", "Amplitud Máxima (Counts)")

st.markdown("---")

if fig is None:
    st.warning("Selecciona al menos una estación en la barra lateral para generar la visualización.")
else:
    st.plotly_chart(fig, use_container_width=True)

# Detalles de metadatos en acordeón desplegable
with st.expander("📄 Ver Metadatos del Evento y Archivos de Trazas"):
    st.write(f"**Identificador de Evento**: `{selected_event.event_id}`")
    st.write(f"**Tiempo UTC de Referencia**: `{format_utc_display(selected_event.reference_time_utc)}`")
    st.write(f"**Estaciones Incluidas**: {', '.join(selected_event.stations.keys())}")
    st.markdown("#### Archivos MiniSEED Indexados:")
    for ef in selected_event.event_files:
        st.code(f"[{ef.station}] {ef.filename} -> {ef.file_path}", language="text")
