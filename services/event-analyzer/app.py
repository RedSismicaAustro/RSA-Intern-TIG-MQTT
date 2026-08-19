import os
import json
from datetime import datetime, timezone
import streamlit as st

from src.core.reader import MseedReader, EventFile
from src.core.event_grouper import EventGrouper, RegionalEvent
from src.core.influx_client import InfluxEventsClient
from src.modules.visualizer import WaveformVisualizer
from src.utils.time_utils import format_utc_display, format_utc_time_only, format_duration

try:
    from plotly_resampler import register_plotly_resampler
    resampler_host = os.environ.get("RESAMPLER_HOST", "ubuntu-server")
    register_plotly_resampler(mode="Dash", port=8050, host="0.0.0.0")
except Exception:
    pass

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
    .badge-auto {
        background-color: #2196F3;
        color: white;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 0.9rem;
        font-weight: bold;
    }
    .badge-manual {
        background-color: #FF9800;
        color: white;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 0.9rem;
        font-weight: bold;
    }
    .badge-confirmed {
        background-color: #4CAF50;
        color: white;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 0.9rem;
        font-weight: bold;
    }
    .badge-discarded {
        background-color: #F44336;
        color: white;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 0.9rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🌋 RSA — Event Analyzer</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Red Sísmica del Austro — Sistema Web Modular de Visualización y Análisis Multiestación</div>', unsafe_allow_html=True)

data_dir = os.environ.get("DATA_DIR", "/data/events")
influx_client = InfluxEventsClient()
is_influx_online = influx_client.ping()

# ==============================================================================
# GESTIÓN DE ESTADO DE SESIÓN
# ==============================================================================
if "optimistic_status" not in st.session_state:
    st.session_state.optimistic_status = {}  # {event_id: "confirmed" | "discarded"}

if "applied_event_id" not in st.session_state:
    st.session_state.applied_event_id = None

# ==============================================================================
# OBTENCIÓN DEL ÍNDICE DE FECHAS (INFLUXDB PRIMARIO + FALLBACK DISCO)
# ==============================================================================
@st.cache_data(ttl=60)
def get_catalog_dates():
    """Consulta las fechas disponibles en InfluxDB."""
    if is_influx_online:
        dates = influx_client.get_recorded_dates()
        if dates:
            return dates, "influx"
    return [], "none"

@st.cache_data(ttl=300)
def load_and_group_events_disk(path: str):
    """Fallback: Escaneo de Google Drive si InfluxDB no tiene datos."""
    reader = MseedReader(data_dir=path)
    files = reader.scan()
    grouper = EventGrouper(window_s=30.0)
    events = grouper.group(files)
    return files, events

available_dates, catalog_source = get_catalog_dates()

# Fallback si no hay fechas en InfluxDB
disk_events = []
if not available_dates:
    with st.spinner("Indexando eventos desde almacenamiento en disco (Google Drive)..."):
        _, disk_events = load_and_group_events_disk(data_dir)
        if disk_events:
            events_by_date_disk = {}
            for evt in disk_events:
                d = evt.reference_time_utc.date()
                if d not in events_by_date_disk:
                    events_by_date_disk[d] = []
                events_by_date_disk[d].append(evt)
            available_dates = sorted(list(events_by_date_disk.keys()))
            catalog_source = "disk"

if not available_dates:
    st.error(f"No se encontraron eventos sísmicos en InfluxDB ni en `{data_dir}`. Por favor verifica que los servicios estén activos.")
    st.stop()

# ==============================================================================
# BARRA LATERAL — CONFIGURACIÓN Y DSP
# ==============================================================================
st.sidebar.title("🎛️ Panel de Control")

# Indicador de estado del índice
if catalog_source == "influx":
    st.sidebar.success("⚡ Índice rápido: **InfluxDB conectado**", icon="🗄️")
else:
    st.sidebar.warning("📂 Índice local: **Almacenamiento Drive**", icon="📁")

if st.sidebar.button("🔄 Recargar Catálogo"):
    st.cache_data.clear()
    st.session_state.optimistic_status = {}
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Selección de Evento Regional")

min_date = available_dates[0]
max_date = available_dates[-1]

st.sidebar.caption(f"🗓️ Rango: **{min_date.strftime('%Y-%m-%d')}** a **{max_date.strftime('%Y-%m-%d')}** ({len(available_dates)} días)")

selected_date = st.sidebar.date_input(
    "1. Selecciona la Fecha:",
    value=max_date,
    min_value=min_date,
    max_value=max_date
)

# Cargar eventos del día seleccionado
day_events_data = []
events_by_id_map = {}

def get_status_icon(evt_type: str) -> str:
    icons = {
        "auto": "🤖",
        "manual": "👤",
        "confirmed": "✅",
        "discarded": "❌"
    }
    return icons.get(evt_type, "📍")

if catalog_source == "influx":
    day_events_raw = influx_client.get_events_by_date(selected_date)
    for evt in day_events_raw:
        evt_id = evt["event_id"]
        # Aplicar estado optimista si fue modificado en esta sesión
        current_status = st.session_state.optimistic_status.get(evt_id, evt.get("event_type", "auto"))
        evt["event_type"] = current_status
        events_by_id_map[evt_id] = evt
        day_events_data.append(evt)
else:
    day_events_objects = [e for e in disk_events if e.reference_time_utc.date() == selected_date]
    for evt in day_events_objects:
        evt_id = evt.event_id
        current_status = st.session_state.optimistic_status.get(evt_id, "auto")
        evt_dict = {
            "event_id": evt_id,
            "event_type": current_status,
            "source": "disk_scan",
            "reference_time_utc": evt.reference_time_utc,
            "timestamp_utc": evt.reference_time_utc.isoformat(),
            "stations": list(evt.stations.keys()),
            "stations_str": ",".join(evt.stations.keys()),
            "n_stations": evt.n_stations,
            "duration_s": evt.duration_seconds,
            "request_id": evt_id,
            "details": {},
            "raw_details_str": "{}"
        }
        events_by_id_map[evt_id] = evt_dict
        day_events_data.append(evt_dict)

if not day_events_data:
    st.sidebar.warning(f"No hay eventos registrados para el {selected_date}.")
    st.session_state.applied_event_id = None
    st.stop()

event_ids_list = [e["event_id"] for e in day_events_data]

def format_event_selector_label(evt_id: str) -> str:
    evt = events_by_id_map.get(evt_id)
    if not evt:
        return evt_id
    current_status = st.session_state.optimistic_status.get(evt_id, evt.get("event_type", "auto"))
    icon = get_status_icon(current_status)
    time_str = format_utc_time_only(evt["reference_time_utc"]) if evt.get("reference_time_utc") else "--:--"
    return f"{icon} {time_str} ({evt['n_stations']} est.) — {evt_id}"

# Determinar índice preseleccionado
default_idx = 0
if st.session_state.applied_event_id in event_ids_list:
    default_idx = event_ids_list.index(st.session_state.applied_event_id)

selected_event_id = st.sidebar.selectbox(
    "2. Selecciona un Evento del Día:",
    options=event_ids_list,
    format_func=format_event_selector_label,
    index=default_idx
)

btn_apply = st.sidebar.button("✅ Aplicar Selección de Evento", use_container_width=True)
if btn_apply or st.session_state.applied_event_id is None:
    st.session_state.applied_event_id = selected_event_id

# Validar que el evento aplicado exista en el día actual
if st.session_state.applied_event_id not in events_by_id_map:
    st.session_state.applied_event_id = event_ids_list[0]

selected_event_dict = events_by_id_map[st.session_state.applied_event_id]

# ==============================================================================
# RESOLUCIÓN LAZY LOADING DE ARCHIVOS MINI-SEED (OBSPY)
# ==============================================================================
reader = MseedReader(data_dir=data_dir)
ref_dt = selected_event_dict.get("reference_time_utc") or datetime.now(timezone.utc)
stations_target = selected_event_dict.get("stations", [])

with st.spinner("Buscando trazas sísmicas MiniSEED bajo demanda..."):
    matched_event_files = reader.scan_event(ref_time=ref_dt, stations=stations_target, window_s=120.0)

# Construir objeto RegionalEvent
stations_dict = {}
for ef in matched_event_files:
    if ef.station not in stations_dict:
        stations_dict[ef.station] = [ef]
    else:
        stations_dict[ef.station].append(ef)

current_regional_event = RegionalEvent(
    event_id=selected_event_dict["event_id"],
    reference_time_utc=ref_dt,
    stations=stations_dict,
    event_files=matched_event_files
)

available_stations = sorted(list(stations_dict.keys())) if stations_dict else stations_target

# Inicializar o actualizar estado de sesión para el evento actual
if "current_event_id" not in st.session_state or st.session_state.current_event_id != current_regional_event.event_id:
    st.session_state.current_event_id = current_regional_event.event_id
    st.session_state.applied_stations = available_stations.copy()
    st.session_state.applied_detrend = True
    st.session_state.applied_bandpass = False
    st.session_state.applied_freq_min = 0.5
    st.session_state.applied_freq_max = 20.0

st.sidebar.markdown("---")

# Formulario 1: Selección de estaciones a visualizar
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

# Formulario 2: Filtros DSP
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
# PANEL PRINCIPAL — CLASIFICACIÓN, MÉTRICAS Y GRÁFICOS
# ==============================================================================

# Estado actual
current_evt_type = st.session_state.optimistic_status.get(
    selected_event_dict["event_id"],
    selected_event_dict.get("event_type", "auto")
)

badge_class = f"badge-{current_evt_type}"
badge_labels = {
    "auto": "🤖 Automático (Correlador)",
    "manual": "👤 Manual (Extracción Solicitada)",
    "confirmed": "✅ Confirmado (Evento Sísmico Real)",
    "discarded": "❌ Descartado (Falsa Alarma / Ruido)"
}
badge_text = badge_labels.get(current_evt_type, current_evt_type.upper())

col_status, col_btn_confirm, col_btn_discard = st.columns([2, 1, 1])

with col_status:
    st.markdown(f"**Estado del Evento:** <span class='{badge_class}'>{badge_text}</span>", unsafe_allow_html=True)

with col_btn_confirm:
    if st.button("✅ Confirmar Evento", use_container_width=True, disabled=(current_evt_type == "confirmed")):
        ok, msg = influx_client.publish_classification(
            event_id=selected_event_dict["event_id"],
            new_type="confirmed",
            current_event=selected_event_dict
        )
        if ok:
            st.session_state.optimistic_status[selected_event_dict["event_id"]] = "confirmed"
            st.toast("✅ Evento confirmado y emitido a MQTT/Telegraf", icon="🎉")
            st.rerun()
        else:
            st.error(f"Error al publicar clasificación: {msg}")

with col_btn_discard:
    if st.button("❌ Descartar Evento", use_container_width=True, disabled=(current_evt_type == "discarded")):
        ok, msg = influx_client.publish_classification(
            event_id=selected_event_dict["event_id"],
            new_type="discarded",
            current_event=selected_event_dict
        )
        if ok:
            st.session_state.optimistic_status[selected_event_dict["event_id"]] = "discarded"
            st.toast("❌ Evento descartado y sincronizado", icon="🗑️")
            st.rerun()
        else:
            st.error(f"Error al publicar clasificación: {msg}")

st.markdown("---")

# Métricas de cabecera
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
active_stations = st.session_state.applied_stations
col_m1.metric("📍 Evento Regional", current_regional_event.event_id, format_utc_display(current_regional_event.reference_time_utc))
col_m2.metric("📡 Estaciones Seleccionadas", f"{len(active_stations)} / {len(available_stations)}", f"Estaciones: {', '.join(active_stations)}")
col_m3.metric("⏱️ Duración del Registro", format_duration(selected_event_dict.get("duration_s", 120.0)))

# Generar gráfico Plotly mediante WaveformVisualizer
visualizer = WaveformVisualizer()

if matched_event_files:
    with st.spinner("Cargando y procesando trazas sísmicas con ObsPy..."):
        fig, metrics = visualizer.create_event_figure(
            regional_event=current_regional_event,
            selected_stations=active_stations,
            apply_detrend=st.session_state.applied_detrend,
            apply_bandpass=st.session_state.applied_bandpass,
            freq_min=st.session_state.applied_freq_min,
            freq_max=st.session_state.applied_freq_max
        )
    col_m4.metric("📈 PGA Z Estimado", f"{metrics.get('pga_z', 0.0):.2f}", "Amplitud Máxima (Counts)")
else:
    fig = None
    col_m4.metric("📈 PGA Z Estimado", "N/A", "Sin trazas en disco")

st.markdown("---")

if fig is None:
    if not matched_event_files:
        st.warning(f"⚠️ No se encontraron archivos `.mseed` locales para las estaciones ({', '.join(stations_target)}) en la fecha `{ref_dt.strftime('%Y-%m-%d')}`. Se muestran únicamente los metadatos registrados en InfluxDB.")
    else:
        st.warning("Selecciona al menos una estación y presiona '✅ Aplicar Selección de Estaciones' para generar la visualización.")
else:
    st.plotly_chart(fig, use_container_width=True)

# Acordeón de metadatos detallados
with st.expander("📄 Ver Metadatos del Evento y Archivos de Trazas", expanded=False):
    st.write(f"**Identificador de Evento (`event_id`)**: `{selected_event_dict['event_id']}`")
    st.write(f"**Tipo de Evento (`event_type`)**: `{current_evt_type}`")
    st.write(f"**Origen de Detección (`source`)**: `{selected_event_dict.get('source')}`")
    st.write(f"**Tiempo UTC de Referencia**: `{format_utc_display(ref_dt)}`")
    st.write(f"**Estaciones Participantes**: {selected_event_dict.get('stations_str', ', '.join(stations_target))}")
    st.write(f"**Solicitud Broadcast (`request_id`)**: `{selected_event_dict.get('request_id', 'N/A')}`")

    details_obj = selected_event_dict.get("details", {})
    if details_obj and isinstance(details_obj, dict) and "detections" in details_obj:
        st.markdown("#### 🎯 Detecciones Coincidentes del Correlador:")
        det_list = details_obj.get("detections", [])
        for d in det_list:
            st.markdown(f"- **Estación {d.get('station')}**: Fase `{d.get('phase')}` | Probabilidad: `{d.get('probability', 0.0):.4f}` | Hora: `{d.get('timestamp')}`")

    st.markdown("#### 📁 Archivos MiniSEED Resueltos en Disco:")
    if matched_event_files:
        for ef in matched_event_files:
            st.code(f"[{ef.station}] {ef.filename} -> {ef.file_path}", language="text")
    else:
        st.info("No hay archivos MiniSEED locales asociados para este evento.")
