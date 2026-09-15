# Contributing

Keep contributions scoped to the repository taxonomy in `README.md`.

## Development

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s Development/Tests -v
python -m compileall -q rf_mapper.py rf_mapping Mapping Development/Tests
```

## Guidelines

- Keep RF-only evidence separate from collision-safe geometry claims.
- Preserve raw measurement data and metadata needed for reproducibility.
- Add tests for behavior changes in `Mapping/RF_Mapping/rf_mapping/`.
- Keep generated outputs out of commits unless they are intentional fixtures in
  `Development/Datasets/examples/`.
- Do not commit local credentials or board-specific assumptions that have not
  been verified on hardware.
