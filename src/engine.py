"""Обратная совместимость: COLREGInferenceEngine теперь живёт в src.inference.

Этот модуль сохранён как тонкий re-export, чтобы существующие импорты
`from src.engine import COLREGInferenceEngine` продолжали работать.
Логика вывода полностью перенесена в формальный движок прямой цепочки
по декларативной KB МППСС-72 (см. src/formal/, src/inference.py).
"""
from .inference import COLREGInferenceEngine

__all__ = ["COLREGInferenceEngine"]
