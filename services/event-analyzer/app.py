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

# Opciones formateadas para el dropdown de eventos
event_options = {
    f"{evt.event_id} | {format_utc_display(evt.reference_time_utc)} ({evt.n_stations} est.)": evt
    for evt in events
}

if "applied_event_label" not in st.session_state:
    st.session_state.applied_event_label = None

# Formulario 0: Selección y confirmación de evento regional
with st.sidebar.form("event_form"):
    st.subheader("📅 Selección de Evento Regional")
    
    initial_index = 0
    if st.session_state.applied_event_label in event_options:
        initial_index = list(event_options.keys()).index(st.session_state.applied_event_label)
        
    event_draft = st.selectbox(
        "Selecciona un Evento Regional:",
        options=list(event_options.keys()),
        index=initial_index
    )
    btn_apply_event = st.form_submit_button("✅ Aplicar Selección de Eventos", use_container_width=True)
    if btn_apply_event:
        st.session_state.applied_event_label = event_draft

# Si aún no se ha aplicado ningún evento (estado inicial)
if st.session_state.applied_event_label is None:
    st.info("👈 Por favor selecciona un evento regional en el panel de control y presiona '**✅ Aplicar Selección de Eventos**' para comenzar.")
    st.stop()

selected_event = event_options[st.session_state.applied_event_label]
available_stations = sorted(list(selected_event.stations.keys()))

# Inicializar o actualizar el estado de la sesión cuando cambia el evento seleccionado
if "current_event_id" not in st.session_state or st.session_state.current_event_id != selected_event.event_id:
    st.session_state.current_event_id = selected_event.event_id
    st.session_state.applied_stations = available_stations.copy()
    st.session_state.applied_detrend = True
    st.session_state.applied_bandpass = False
    st.session_state.applied_freq_min = 0.5
    st.session_state.applied_freq_max = 20.0

st.sidebar.markdown("---")

# Formulario 1: Selección y confirmación de estaciones a visualizar
with st.sidebar.form("stations_form"):
    st.subheader("📡 Estaciones a Visualizar")
    stations_draft = st.multiselect(
        "Filtrar Estaciones:",
        options=available_stations,
        default=[s for s in st.session_state.applied_stations if s in available_stations]
    )
    btn_apply_stations = st.form_submit_button("✅ Aplicar Selección de Estaciones", use_container_width=True)
    if btn_apply_stations:
        st.session_state.applied_stations = stations_draft

st.sidebar.markdown("---")

# Formulario 2: Configuración y confirmación de Filtros DSP
with st.sidebar.form("dsp_form"):
    st.subheader("⚙️ Procesamiento de Señal (DSP)")

    detrend_draft = st.checkbox(
        "Remover Tendencia / Media (Detrend)",
        value=st.session_state.applied_detrend,
        help="Remueve la media de la señal y la tendencia lineal antes del desplegado."
    )

    bandpass_draft = st.checkbox(
        "Filtro Pasabanda Butterworth",
        value=st.session_state.applied_bandpass,
        help="Aplica un filtro pasabanda de 4to orden con fase cero."
    )

    col_f1, col_f2 = st.columns(2)
    freq_min_draft = col_f1.number_input("F. Mín (Hz)", min_value=0.01, max_value=20.0, value=st.session_state.applied_freq_min, step=0.1)
    freq_max_draft = col_f2.number_input("F. Máx (Hz)", min_value=0.1, max_value=100.0, value=st.session_state.applied_freq_max, step=1.0)

    btn_apply_dsp = st.form_submit_button("⚡ Aplicar Filtros DSP", use_container_width=True)
    if btn_apply_dsp:
        st.session_state.applied_detrend = detrend_draft
        st.session_state.applied_bandpass = bandpass_draft
        st.session_state.applied_freq_min = freq_min_draft
        st.session_state.applied_freq_max = freq_max_draft

# ==============================================================================
# PANEL PRINCIPAL — MÉTRICAS Y GRÁFICOS
# ==============================================================================

# Métricas de cabecera usando los parámetros aplicados confirmados
col_m1, col_m2, col_m3, col_m4 = st.columns(4)

active_stations = st.session_state.applied_stations
col_m1.metric("📍 Evento Regional", selected_event.event_id, format_utc_display(selected_event.reference_time_utc))
col_m2.metric("📡 Estaciones Seleccionadas", f"{len(active_stations)} / {selected_event.n_stations}", f"Total en red: {len(available_stations)}")
col_m3.metric("⏱️ Duración del Registro", format_duration(selected_event.duration_seconds))

# Generar gráfico Plotly mediante WaveformVisualizer usando la configuración confirmada
visualizer = WaveformVisualizer()

with st.spinner("Cargando y procesando trazas sísmicas MiniSEED..."):
    fig, metrics = visualizer.create_event_figure(
        regional_event=selected_event,
        selected_stations=active_stations,
        apply_detrend=st.session_state.applied_detrend,
        apply_bandpass=st.session_state.applied_bandpass,
        freq_min=st.session_state.applied_freq_min,
        freq_max=st.session_state.applied_freq_max
    )

col_m4.metric("📈 PGA Z Estimado", f"{metrics.get('pga_z', 0.0):.2f}", "Amplitud Máxima (Counts)")

st.markdown("---")

if fig is None:
    st.warning("Selecciona al menos una estación y presiona '✅ Aplicar Selección de Estaciones' para generar la visualización.")
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
