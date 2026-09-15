# Contributing

Keep contributions scoped to the repository taxonomy in `README.md`.

## Development

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ./Mapping/RF_Mapping pytest
python -m unittest discover -s Development/Tests/RF_Mapping -v
python -m pytest -q
python -m compileall -q rf_mapper.py Mapping/RF_Mapping/src Development/Tests
python -m pip wheel ./Mapping/RF_Mapping --no-deps --wheel-dir /tmp/rf-mapping-wheels
```

Install the canonical package before running tests or launchers. Tests use the
installed package, without PYTHONPATH configuration. Explicit unittest discovery
keeps Development an organizational folder rather than a Python runtime package.
See the [RF subsystem README](Mapping/RF_Mapping/README.md) for package ownership.

## Guidelines

- Keep RF-only evidence separate from collision-safe geometry claims.
- Preserve raw measurement data and metadata needed for reproducibility.
- Add tests for behavior changes in `Mapping/RF_Mapping/src/rf_mapping/`.
- Keep generated outputs out of commits unless they are intentional fixtures in
  `Development/Datasets/RF_Mapping/`.
- Do not commit local credentials or board-specific assumptions that have not
  been verified on hardware.
