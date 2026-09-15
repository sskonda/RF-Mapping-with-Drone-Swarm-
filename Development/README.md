# Development

[Tests](Tests/unit/) contains the existing unittest suite.
[Datasets](Datasets/) contains the measured survey and acquisition/calibration
examples. Generated experiment outputs remain relative to the caller's working
directory, as before.

Run from the repository root:

```sh
python -m unittest discover -s Development/Tests -v
python -m compileall -q rf_mapper.py rf_mapping Mapping Development/Tests
```

Future standalone simulations, experiments, and utilities belong here when
implemented. The existing rf_mapping.simulation module remains with the runtime
package because it is part of the supported simulate CLI and Python API.

See [CONTRIBUTING.md](../CONTRIBUTING.md) and the
[operator workflow](../Docs/Design/prototype_workflow.md).
