# Development

[Tests](Tests/RF_Mapping/) contains the existing unittest suite.
[Datasets](Datasets/RF_Mapping/) contains the measured survey and acquisition/calibration
examples. Generated experiment outputs remain relative to the caller's working
directory, as before.

Run from the repository root:

```sh
python -m pip install -e ./Mapping/RF_Mapping
python -m unittest discover -s Development/Tests/RF_Mapping -v
python -m compileall -q rf_mapper.py Mapping/RF_Mapping/src Development/Tests
```

Development is an organizational folder, not a Python runtime package. Use the
explicit discovery path above so every RF test runs against the installed package.

Future standalone simulations, experiments, and utilities belong here when
implemented. The existing rf_mapping.simulation module remains with the runtime
package because it is part of the supported simulate CLI and Python API.

[Reports](Reports/) holds repository migration audits. The original reorganization
report is historical and intentionally retains the paths used at that time.
The [RF package cleanup verification](Reports/rf_package_cleanup_verification.md)
records the canonical package migration, preserved files, tests and build checks.

See [CONTRIBUTING.md](../CONTRIBUTING.md) and the
[operator workflow](../Docs/Design/RF_Mapping/prototype_workflow.md).
