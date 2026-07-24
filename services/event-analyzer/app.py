import os
import streamlit as st
from src.core.reader import MseedReader
from src.core.event_grouper import EventGrouper
from src.utils.time_utils import format_utc_display, format_duration

st.set_page_config(
    page_title="RSA — Event Analyzer",
    page_icon="🌋",
    layout="wide",
)

st.title("RSA — Event Analyzer")

data_dir = os.environ.get("DATA_DIR", "/data/events")

@st.cache_data(ttl=300)
def load_and_group_events(path: str):
    reader = MseedReader(data_dir=path)
    files = reader.scan()
    grouper = EventGrouper(window_s=30.0)
    events = grouper.group(files)
    return files, events

st.subheader("Subfase 1B: Diagnóstico de Lectura y Agrupamiento Core")

st.info(f"📁 Directorio montado objetivo: `{data_dir}`")

with st.spinner("Parseando nombres de archivo MiniSEED y agrupando eventos regionales..."):
    files, events = load_and_group_events(data_dir)

col1, col2 = st.columns(2)
col1.metric("Archivos MiniSEED Encontrados", len(files))
col2.metric("Eventos Regionales Agrupados", len(events))

if not events:
    st.warning(f"No se encontraron archivos .mseed en `{data_dir}`. Verifica que el volumen de Google Drive esté correctamente montado.")
else:
    st.success(f"Se agruparon {len(events)} eventos regionales exitosamente a partir de {len(files)} archivos.")

    st.markdown("### Resumen de Eventos Detectados (Primeros 15)")
    for evt in events[:15]:
        with st.expander(f"📍 {evt.event_id} — {format_utc_display(evt.reference_time_utc)} ({evt.n_stations} estaciones)"):
            st.write(f"**Estaciones participantes**: {', '.join(evt.stations.keys())}")
            st.write(f"**Duración estimada**: {format_duration(evt.duration_seconds)}")
            st.write("**Archivos indexados**:")
            for ef in evt.event_files:
                st.text(f" - [{ef.station}] {ef.filename} (Inicio: {ef.start_utc.strftime('%Y-%m-%d %H:%M:%S UTC')})")
