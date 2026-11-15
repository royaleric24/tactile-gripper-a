"""Dashboard pages."""

from .analysis import analysis_page
from .experiments import experiments_page
from .live import live_page

__all__ = ["live_page", "experiments_page", "analysis_page"]
