"""Command entry point with concise startup errors."""
import sys
from .shortcut_overlay import main as run

def main():
    try:
        run()
    except (ConnectionError, OSError, RuntimeError, ValueError) as error:
        sys.exit(f'superhold: {error}')
