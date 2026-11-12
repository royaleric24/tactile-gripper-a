"""Tactile gripper software package (S1 protocol + S2-A application)."""

from .constants import CONTRACT_VERSION, PROTOCOL_VERSION, SOFTWARE_VERSION
from .sources import DataSource

__all__ = ["CONTRACT_VERSION", "PROTOCOL_VERSION", "SOFTWARE_VERSION", "DataSource"]
