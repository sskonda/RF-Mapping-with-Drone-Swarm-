from __future__ import annotations

from pathlib import Path


_SOURCE_PACKAGE = Path(__file__).resolve().parents[1] / "Mapping" / "RF_Mapping" / "rf_mapping"
__path__ = [str(_SOURCE_PACKAGE), *list(__path__)]

__doc__ = "Compatibility package for the Mapping/RF_Mapping/rf_mapping source layout."
