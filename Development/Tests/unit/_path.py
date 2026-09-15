from __future__ import annotations

import sys
from pathlib import Path


SOFTWARE_ROOT = Path(__file__).resolve().parents[3] / "Mapping" / "RF_Mapping"
software_path = str(SOFTWARE_ROOT)
if software_path not in sys.path:
    sys.path.insert(0, software_path)
