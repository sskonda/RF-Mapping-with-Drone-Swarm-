# ESP32 Code

All code executing directly on an ESP32 belongs here.

The implemented [RSSI sketch](RF_Capture/RSSI/esp32_rssi_mapper/) connects to a
2.4 GHz hotspot and answers PING and MEASURE commands at 115200 baud. Keep the
sketch directory named esp32_rssi_mapper so Arduino recognizes its matching
esp32_rssi_mapper.ino file. The local wifi_credentials.h must remain beside it.

Follow the [firmware setup and serial workflow](../Docs/Design/prototype_workflow.md).
The exact board target is still unresolved. CSI is described in the
[follow-on research](../Docs/Research/CSI_FOLLOW_ON.md).

Future flight-controller code belongs in Autonomy/Flight_Controller; navigation
interfaces, RF capture, communications, sensor drivers, and shared utilities
should receive directories when implemented.
