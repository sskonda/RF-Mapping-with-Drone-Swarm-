from __future__ import annotations

import sys
from pathlib import Path


SOFTWARE_ROOT = Path(__file__).resolve().parent / "Mapping" / "RF_Mapping"
software_path = str(SOFTWARE_ROOT)
if software_path not in sys.path:
    sys.path.insert(0, software_path)

from rf_mapping.cli import rf_mapper as _impl


for _name in dir(_impl):
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = getattr(_impl, _name)


if __name__ == "__main__":
    raise SystemExit(_impl.main())
