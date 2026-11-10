"""Вкладки главного окна."""

from .editor import EditorTab
from .generator import GeneratorTab
from .info import InfoTab
from .plan import PlanTab
from .quality import QualityTab

__all__ = ["EditorTab", "GeneratorTab", "InfoTab", "PlanTab", "QualityTab"]
