"""Preserve the old checkout import path without a duplicate implementation."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'superhold'))
from superhold import __path__, __version__
