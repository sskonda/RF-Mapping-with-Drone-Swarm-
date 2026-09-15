# Autonomy

Planned host-side single-drone behavior includes state estimation, localization,
path planning, trajectory generation, obstacle avoidance, exploration, and
mission control. No autonomous flight implementation is present yet.

Create each subsystem directory when its implementation or design is available.
Low-level ESP32 motor, attitude, altitude, sensor-driver, and failsafe code belongs
under ESP32_Code/Autonomy/Flight_Controller when implemented.

The [architecture](../Docs/Architecture/system_overview.md) defines the planned
camera/IMU pose and geometric-navigation responsibilities. RF evidence remains
an auxiliary mapping input.
