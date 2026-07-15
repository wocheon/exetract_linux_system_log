"""Independent collection modules."""

from .files import collect_files
from .journal import collect_journal
from .prometheus import collect_prometheus
from .system import collect_system_summary

__all__ = ["collect_files", "collect_journal", "collect_prometheus", "collect_system_summary"]
