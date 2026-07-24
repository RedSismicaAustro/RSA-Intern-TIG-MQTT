import logging
from dataclasses import dataclass, field
from datetime import datetime
import obspy
from src.core.reader import EventFile

logger = logging.getLogger(__name__)

@dataclass
class RegionalEvent:
    event_id: str
    reference_time_utc: datetime
    stations: dict[str, list[EventFile]] = field(default_factory=dict)
    event_files: list[EventFile] = field(default_factory=list)

    @property
    def n_stations(self) -> int:
        return len(self.stations)

    @property
    def duration_seconds(self) -> float:
        if not self.event_files:
            return 0.0
        max_duration = 0.0
        for ef in self.event_files:
            dur = (ef.end_utc - ef.start_utc).total_seconds()
            if dur > max_duration:
                max_duration = dur
        return float(max_duration)

    def load_streams(self) -> dict[str, obspy.Stream]:
        """Carga bajo demanda los streams ObsPy de las estaciones participantes."""
        streams = {}
        for station, efiles in self.stations.items():
            combined_st = obspy.Stream()
            for ef in efiles:
                combined_st += ef.load_stream()
            streams[station] = combined_st
        return streams


class EventGrouper:
    def __init__(self, window_s: float = 30.0):
        self.window_s = window_s

    def group(self, event_files: list[EventFile]) -> list[RegionalEvent]:
        """
        Agrupa una lista de EventFile por coincidencia de tiempo de inicio UTC dentro de window_s.
        Retorna la lista de RegionalEvent ordenada de forma descendente (más recientes primero).
        """
        if not event_files:
            return []

        sorted_files = sorted(event_files, key=lambda ef: ef.start_utc)

        groups: list[list[EventFile]] = []
        current_group: list[EventFile] = []

        for ef in sorted_files:
            if not current_group:
                current_group.append(ef)
            else:
                ref_time = current_group[0].start_utc
                time_diff = abs((ef.start_utc - ref_time).total_seconds())
                if time_diff <= self.window_s:
                    current_group.append(ef)
                else:
                    groups.append(current_group)
                    current_group = [ef]

        if current_group:
            groups.append(current_group)

        regional_events = []
        for group in groups:
            ref_time = group[0].start_utc
            event_id = f"EVT-{ref_time.strftime('%Y%m%d-%H%M%S')}"

            stations_dict: dict[str, list[EventFile]] = {}
            for ef in group:
                if ef.station not in stations_dict:
                    stations_dict[ef.station] = [ef]
                else:
                    stations_dict[ef.station].append(ef)

            regional_events.append(RegionalEvent(
                event_id=event_id,
                reference_time_utc=ref_time,
                stations=stations_dict,
                event_files=group
            ))

        regional_events.sort(key=lambda re: re.reference_time_utc, reverse=True)
        return regional_events
