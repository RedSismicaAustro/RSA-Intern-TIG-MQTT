import logging
from datetime import timedelta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.core.event_grouper import RegionalEvent
from src.modules.base import BaseAnalysisModule

try:
    from plotly_resampler import FigureResampler
    HAS_RESAMPLER = True
except ImportError:
    HAS_RESAMPLER = False

logger = logging.getLogger(__name__)

STATION_COLORS = [
    "#FF6B35",  # Naranja RSA
    "#00E676",  # Verde Neón
    "#29B6F6",  # Azul Cielo
    "#AB47BC",  # Púrpura
    "#FFD54F",  # Amarillo
    "#FF4081",  # Rosa
    "#26A69A",  # Turquesa
    "#FFA726",  # Ámbar
    "#8D6E63",  # Marrón
    "#78909C",  # Gris Azulado
]

class WaveformVisualizer(BaseAnalysisModule):
    def get_name(self) -> str:
        return "Visualizador de Formas de Onda (Plotly)"

    def process_event(self, regional_event: RegionalEvent, **kwargs) -> dict:
        """
        Punto de entrada estandarizado para la tubería (Pipeline).
        Extrae los parámetros de kwargs y llama a create_event_figure.
        """
        selected_stations = kwargs.get("selected_stations", list(regional_event.stations.keys()))
        apply_detrend = kwargs.get("apply_detrend", True)
        apply_bandpass = kwargs.get("apply_bandpass", False)
        freq_min = kwargs.get("freq_min", 0.5)
        freq_max = kwargs.get("freq_max", 20.0)

        fig, metrics = self.create_event_figure(
            regional_event=regional_event,
            selected_stations=selected_stations,
            apply_detrend=apply_detrend,
            apply_bandpass=apply_bandpass,
            freq_min=freq_min,
            freq_max=freq_max
        )

        return {
            "figure": fig,
            "metrics": metrics,
            "summary": f"Visualización generada para {metrics.get('n_stations', 0)} estaciones."
        }

    def create_event_figure(
        self,
        regional_event: RegionalEvent,
        selected_stations: list[str],
        apply_detrend: bool = True,
        apply_bandpass: bool = False,
        freq_min: float = 0.5,
        freq_max: float = 20.0
    ) -> tuple[go.Figure | None, dict]:
        """
        Carga bajo demanda las trazas de las estaciones seleccionadas,
        aplica filtrado/detrending y genera una figura Plotly interactiva alineada en UTC.
        """
        if not selected_stations:
            return None, {"pga_z": 0.0, "n_stations": 0, "duration_s": 0.0, "traces_count": 0}

        all_streams = regional_event.load_streams()

        traces_to_plot = []
        station_color_map = {}

        color_idx = 0
        for station in selected_stations:
            if station not in all_streams:
                continue

            station_color_map[station] = STATION_COLORS[color_idx % len(STATION_COLORS)]
            color_idx += 1

            st_copy = all_streams[station].copy()

            # Aplicar procesamiento de señal (DSP)
            if apply_detrend:
                try:
                    st_copy.detrend("demean")
                    st_copy.detrend("linear")
                except Exception as e:
                    logger.warning(f"Error al aplicar detrend en {station}: {e}")

            if apply_bandpass and freq_min < freq_max:
                try:
                    for tr in st_copy:
                        fs = tr.stats.sampling_rate
                        nyquist = fs / 2.0
                        fmax_safe = min(freq_max, nyquist * 0.95)
                        fmin_safe = max(freq_min, 0.001)
                        if fmin_safe < fmax_safe:
                            tr.filter("bandpass", freqmin=fmin_safe, freqmax=fmax_safe, corners=4, zerophase=True)
                except Exception as e:
                    logger.warning(f"Error al aplicar filtro pasabanda en {station}: {e}")

            # Ordenar trazas por canal (Z primero, luego N, luego E)
            for tr in sorted(st_copy, key=lambda t: t.stats.channel):
                traces_to_plot.append((station, tr))

        if not traces_to_plot:
            return None, {"pga_z": 0.0, "n_stations": 0, "duration_s": 0.0, "traces_count": 0}

        n_rows = len(traces_to_plot)
        subplot_titles = [f"Estación: {st} | Canal: {tr.stats.channel}" for st, tr in traces_to_plot]

        sub_fig = make_subplots(
            rows=n_rows,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=max(0.01, min(0.04, 1.0 / n_rows)),
            subplot_titles=subplot_titles
        )

        if HAS_RESAMPLER:
            fig = FigureResampler(sub_fig, default_n_shown_samples=3000)
        else:
            fig = sub_fig

        pga_z_max = 0.0
        MAX_POINTS_PER_TRACE = 3000

        for idx, (station, tr) in enumerate(traces_to_plot, start=1):
            start_utc = tr.stats.starttime.datetime
            times_sec = tr.times()
            data = tr.data
            n_points = len(data)

            max_amp = float(np.max(np.abs(data))) if n_points > 0 else 0.0

            if tr.stats.channel.endswith("Z") or tr.stats.channel.endswith("z"):
                if max_amp > pga_z_max:
                    pga_z_max = max_amp

            color = station_color_map.get(station, "#FF6B35")

            if HAS_RESAMPLER:
                # Usar resampler dinámico con datos crudos completos
                times_utc = [start_utc + timedelta(seconds=float(t)) for t in times_sec]
                fig.add_trace(
                    go.Scatter(
                        mode="lines",
                        name=f"{station} ({tr.stats.channel})",
                        line=dict(color=color, width=1.2),
                        hovertemplate=(
                            f"<b>Estación: {station}</b><br>"
                            f"Canal: {tr.stats.channel}<br>"
                            "Hora UTC: %{x|%H:%M:%S.%L}<br>"
                            "Amplitud: %{y:.4f}<extra></extra>"
                        )
                    ),
                    hf_x=times_utc,
                    hf_y=data,
                    row=idx,
                    col=1
                )
            else:
                # Fallback: Decimación dinámica estática
                if n_points > MAX_POINTS_PER_TRACE:
                    step = n_points // MAX_POINTS_PER_TRACE
                    times_sec_plot = times_sec[::step]
                    data_plot = data[::step]
                else:
                    times_sec_plot = times_sec
                    data_plot = data

                times_utc_plot = [start_utc + timedelta(seconds=float(t)) for t in times_sec_plot]

                fig.add_trace(
                    go.Scatter(
                        x=times_utc_plot,
                        y=data_plot,
                        mode="lines",
                        name=f"{station} ({tr.stats.channel})",
                        line=dict(color=color, width=1.2),
                        hovertemplate=(
                            f"<b>Estación: {station}</b><br>"
                            f"Canal: {tr.stats.channel}<br>"
                            "Hora UTC: %{x|%H:%M:%S.%L}<br>"
                            "Amplitud: %{y:.4f}<extra></extra>"
                        )
                    ),
                    row=idx,
                    col=1
                )

            fig.update_yaxes(title_text="Amplitud", row=idx, col=1)

        fig.update_xaxes(title_text="Tiempo UTC", row=n_rows, col=1)

        fig.update_layout(
            template="plotly_dark",
            height=max(450, 180 * n_rows),
            paper_bgcolor="#0E1117",
            plot_bgcolor="#1A1F2E",
            showlegend=False,
            margin=dict(l=60, r=40, t=60, b=50),
            hovermode="x"
        )

        metrics = {
            "pga_z": pga_z_max,
            "n_stations": len(selected_stations),
            "duration_s": regional_event.duration_seconds,
            "traces_count": n_rows
        }

        return fig, metrics
