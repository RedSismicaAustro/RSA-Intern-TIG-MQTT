from abc import ABC, abstractmethod
from src.core.event_grouper import RegionalEvent

class BaseAnalysisModule(ABC):
    @abstractmethod
    def get_name(self) -> str:
        """Retorna el nombre legible del módulo para la interfaz o pipeline de análisis."""
        pass

    @abstractmethod
    def process_event(self, regional_event: RegionalEvent, **kwargs) -> dict:
        """
        Procesa un evento regional y retorna un diccionario estandarizado de resultados:
        - "figure": plotly.graph_objects.Figure (opcional)
        - "metrics": dict (métricas del análisis)
        - "summary": str (resumen textual opcional)
        """
        pass
