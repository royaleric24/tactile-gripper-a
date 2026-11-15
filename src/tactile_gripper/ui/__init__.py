"""NiceGUI dashboard for S2-A."""

from .pages import analysis_page, experiments_page, live_page
from .server import create_ui, main

__all__ = ["create_ui", "main", "live_page", "experiments_page", "analysis_page"]
