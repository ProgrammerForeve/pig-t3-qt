"""Вкладки главного окна."""

from .editor import EditorTab
from .generator import GeneratorTab
from .history import HistoryTab
from .info import InfoTab
from .plan import PlanTab
from .quality import QualityTab

__all__ = [
    "EditorTab",
    "GeneratorTab",
    "HistoryTab",
    "InfoTab",
    "PlanTab",
    "QualityTab",
]
