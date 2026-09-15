# Security Policy

## Supported Versions

This repository is an early research prototype. Security fixes should target the
default branch unless a maintained release branch is created later.

## Reporting a Vulnerability

Do not open public issues for exposed credentials, unsafe flight behavior,
remote-code-execution risks, or data leaks. Contact the repository owner
privately and include:

- the affected path or component;
- reproduction steps;
- expected impact;
- any temporary mitigation already applied.

Never commit Wi-Fi credentials, API tokens, SSIDs, passwords, or raw private
network identifiers. The ESP32 credential header is ignored at
`ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.h`.
