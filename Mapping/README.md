# Mapping

Mapping converts sensor measurements into environmental information.

The active [RF mapping package](RF_Mapping/rf_mapping/) provides host acquisition,
calibration, RF field inference, attenuation evidence, and visualization.
Its existing Python module boundaries and imports are preserved, including
the simulation module exposed by the CLI.

Camera-based 3D reconstruction and cross-sensor fusion remain planned. Add
Camera_3D_Mapping, Sensor_Fusion, or shared Visualization areas when they contain
implementation or concrete design work.

See the [complete operator workflow](../Docs/Design/prototype_workflow.md).
RF acquisition firmware lives in [ESP32_Code](../ESP32_Code/).
