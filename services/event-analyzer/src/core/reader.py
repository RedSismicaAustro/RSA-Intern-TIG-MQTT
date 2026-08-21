import os
import re
import glob
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import obspy

logger = logging.getLogger(__name__)

# Patrón de nombre de archivo: <ESTACION>_<YYYYMMDD>_<HHMMSS>.mseed
FILENAME_PATTERN = re.compile(r"^([A-Za-z0-9]+)_(\d{8})_(\d{6})\.(?:mseed|MSEED)$")

@dataclass
class EventFile:
    station: str
    file_path: str
    start_utc: datetime
    end_utc: datetime
    filename: str

    def load_stream(self) -> obspy.Stream:
        """Carga el stream ObsPy completo de forma diferida (solo cuando el usuario selecciona el evento)."""
        return obspy.read(self.file_path)

class MseedReader:
    def __init__(self, data_dir: str = "/data/events"):
        self.data_dir = data_dir

    def scan(self) -> list[EventFile]:
        """
        Escanea de forma ULTRA RÁPIDA el sistema de archivos buscando nombres .mseed/.MSEED
        y parseando la estación y fecha/hora UTC directamente desde el nombre del archivo.
        No realiza ninguna lectura de disco/red con ObsPy durante el escaneo.
        """
        if not os.path.exists(self.data_dir):
            logger.warning(f"Directorio de eventos no encontrado: {self.data_dir}")
            return []

        # Buscar todos los archivos .mseed / .MSEED bajo data_dir/*/events/
        pattern_lower = os.path.join(self.data_dir, "*", "events", "*.mseed")
        pattern_upper = os.path.join(self.data_dir, "*", "events", "*.MSEED")
        
        filepaths = glob.glob(pattern_lower)
        filepaths.extend(glob.glob(pattern_upper))

        event_files = []
        for fp in filepaths:
            filename = os.path.basename(fp)
            match = FILENAME_PATTERN.match(filename)

            if match:
                station_code = match.group(1)
                date_str = match.group(2)
                time_str = match.group(3)

                try:
                    dt_naive = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                    start_utc = dt_naive.replace(tzinfo=timezone.utc)
                    # Duración estándar por defecto: 120 segundos
                    end_utc = start_utc + timedelta(seconds=120)

                    event_files.append(EventFile(
                        station=station_code,
                        file_path=fp,
                        start_utc=start_utc,
                        end_utc=end_utc,
                        filename=filename
                    ))
                except ValueError as ve:
                    logger.warning(f"No se pudo parsear la fecha de {filename}: {ve}")
                    continue
            else:
                # Fallback para nombres no estandarizados: inferir estación desde directorio padre
                parts = fp.split(os.sep)
                st_code = parts[-3] if len(parts) >= 3 and parts[-2] == "events" else parts[-2]
                file_mtime = datetime.fromtimestamp(os.path.getmtime(fp), tz=timezone.utc)
                
                event_files.append(EventFile(
                    station=st_code,
                    file_path=fp,
                    start_utc=file_mtime,
                    end_utc=file_mtime + timedelta(seconds=120),
                    filename=filename
                ))

        event_files.sort(key=lambda ef: ef.start_utc)
        return event_files

    def _normalize_station_variants(self, station: str) -> set[str]:
        """Genera variantes comunes de códigos de estación (ej. CHA2 <-> CHA02, DEV0 <-> DEV00)."""
        st = station.strip()
        variants = {st, st.upper(), st.lower()}
        match = re.match(r"^([A-Za-z]+)(\d+)$", st)
        if match:
            prefix, num_str = match.group(1), match.group(2)
            num = int(num_str)
            variants.add(f"{prefix}{num}".upper())
            variants.add(f"{prefix}{num:02d}".upper())
            variants.add(f"{prefix}{num}".lower())
            variants.add(f"{prefix}{num:02d}".lower())
        return variants

    def scan_event(self, ref_time: datetime, stations: list[str] = None, window_s: float = 120.0) -> list[EventFile]:
        """
        Busca de forma selectiva los archivos .mseed de un evento específico
        filtrando por la fecha del evento (YYYYMMDD) y ventana temporal de coincidencia.
        """
        if not os.path.exists(self.data_dir):
            return []

        # Rango de fechas a buscar (día del evento y días adyacentes por si cruza 00:00 UTC)
        date_candidates = {
            (ref_time - timedelta(days=1)).strftime("%Y%m%d"),
            ref_time.strftime("%Y%m%d"),
            (ref_time + timedelta(days=1)).strftime("%Y%m%d")
        }

        # Generar conjunto de variantes de estaciones objetivo
        target_station_variants = set()
        if stations:
            for st in stations:
                target_station_variants.update(self._normalize_station_variants(st))

        found_paths = set()
        for d_str in date_candidates:
            pats = [
                os.path.join(self.data_dir, "*", "events", f"*{d_str}*.mseed"),
                os.path.join(self.data_dir, "*", "events", f"*{d_str}*.MSEED")
            ]
            for p in pats:
                for fp in glob.glob(p):
                    found_paths.add(fp)

        matched_files = []
        for fp in found_paths:
            filename = os.path.basename(fp)
            match = FILENAME_PATTERN.match(filename)
            if match:
                st_code = match.group(1)
                d_str = match.group(2)
                t_str = match.group(3)
                try:
                    dt_naive = datetime.strptime(f"{d_str}_{t_str}", "%Y%m%d_%H%M%S")
                    start_utc = dt_naive.replace(tzinfo=timezone.utc)
                    # Comprobar si coincide en la ventana temporal del evento
                    if abs((start_utc - ref_time).total_seconds()) <= window_s:
                        # Si hay filtro de estaciones, verificar coincidencia o incluir
                        if not target_station_variants or any(v in target_station_variants for v in self._normalize_station_variants(st_code)):
                            matched_files.append(EventFile(
                                station=st_code,
                                file_path=fp,
                                start_utc=start_utc,
                                end_utc=start_utc + timedelta(seconds=120),
                                filename=filename
                            ))
                except ValueError:
                    continue

        matched_files.sort(key=lambda ef: ef.start_utc)
        return matched_files

