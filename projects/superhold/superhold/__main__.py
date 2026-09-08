import sys
from .cli import main

try:
    raise SystemExit(main())
except (ConnectionError, OSError, RuntimeError, ValueError) as error:
    sys.exit(f"superhold: {error}")
