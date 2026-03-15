import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # /admin
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from admin.main import app  # noqa: E402
