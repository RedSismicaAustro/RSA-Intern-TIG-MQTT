from datetime import datetime
import zoneinfo

def utc_to_local(utc_dt: datetime, tz_name: str = "America/Guayaquil") -> datetime:
    """Convierte un objeto datetime UTC a la zona horaria local especificada."""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
    return utc_dt.astimezone(zoneinfo.ZoneInfo(tz_name))

def format_utc_display(utc_dt: datetime) -> str:
    """Formatea datetime a cadena ISO/UTC uniforme."""
    if isinstance(utc_dt, str):
        return utc_dt
    return utc_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

def format_duration(seconds: float) -> str:
    """Formatea segundos a minutos y segundos legibles."""
    mins = int(seconds // 60)
    secs = seconds % 60
    if mins > 0:
        return f"{mins}m {secs:.1f}s"
    return f"{secs:.1f}s"
