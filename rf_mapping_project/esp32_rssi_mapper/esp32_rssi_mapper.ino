#include <WiFi.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "wifi_credentials.h"

constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint32_t WIFI_CONNECT_TIMEOUT_MS = 30000;
constexpr uint32_t WIFI_RETRY_DELAY_MS = 2000;
constexpr uint32_t SAMPLE_INTERVAL_MS = 100;
constexpr size_t SAMPLES_PER_POINT = 50;
constexpr size_t COMMAND_BUFFER_SIZE = 64;
constexpr int32_t MAX_COORDINATE_CM = 100000;
constexpr char SSID_PLACEHOLDER[] = "REPLACE_WITH_YOUR_HOTSPOT_NAME";
constexpr char PASSWORD_PLACEHOLDER[] = "REPLACE_WITH_YOUR_HOTSPOT_PASSWORD";

char commandBuffer[COMMAND_BUFFER_SIZE];
size_t commandLength = 0;
bool commandOverflow = false;

bool credentialsConfigured() {
  return HOTSPOT_SSID[0] != '\0' &&
         strcmp(HOTSPOT_SSID, SSID_PLACEHOLDER) != 0 &&
         strcmp(HOTSPOT_PASSWORD, PASSWORD_PLACEHOLDER) != 0;
}

void printConnectionStatus() {
  Serial.printf(
    "STATUS,CONNECTED,%ld,%ld\n",
    static_cast<long>(WiFi.channel()),
    static_cast<long>(WiFi.RSSI())
  );
}

bool connectToHotspot() {
  if (!credentialsConfigured()) {
    Serial.println("ERROR,SET_HOTSPOT_CREDENTIALS");
    return false;
  }

  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.println("STATUS,CONNECTING");
  WiFi.disconnect();
  WiFi.begin(HOTSPOT_SSID, HOTSPOT_PASSWORD);

  const uint32_t startTime = millis();
  while (WiFi.status() != WL_CONNECTED &&
         millis() - startTime < WIFI_CONNECT_TIMEOUT_MS) {
    delay(WIFI_RETRY_DELAY_MS);
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("ERROR,WIFI_CONNECT_TIMEOUT");
    return false;
  }

  printConnectionStatus();
  Serial.println("READY");
  return true;
}

bool readCommandLine() {
  while (Serial.available() > 0) {
    const char value = static_cast<char>(Serial.read());

    if (value == '\r') {
      continue;
    }

    if (value == '\n') {
      if (commandOverflow) {
        Serial.println("ERROR,COMMAND_TOO_LONG");
        commandLength = 0;
        commandOverflow = false;
        return false;
      }

      commandBuffer[commandLength] = '\0';
      commandLength = 0;
      return true;
    }

    if (commandLength < COMMAND_BUFFER_SIZE - 1) {
      commandBuffer[commandLength++] = value;
    } else {
      commandOverflow = true;
    }
  }

  return false;
}

bool parseMeasurementCommand(int32_t &xCm, int32_t &yCm) {
  long parsedX = 0;
  long parsedY = 0;
  int consumedCharacters = 0;

  const int parsedValues = sscanf(
    commandBuffer,
    "MEASURE,%ld,%ld%n",
    &parsedX,
    &parsedY,
    &consumedCharacters
  );

  if (parsedValues != 2 || commandBuffer[consumedCharacters] != '\0') {
    return false;
  }

  if (parsedX < 0 || parsedY < 0 ||
      parsedX > MAX_COORDINATE_CM || parsedY > MAX_COORDINATE_CM) {
    return false;
  }

  xCm = static_cast<int32_t>(parsedX);
  yCm = static_cast<int32_t>(parsedY);
  return true;
}

void measurePoint(int32_t xCm, int32_t yCm) {
  Serial.printf(
    "START,%ld,%ld,%u\n",
    static_cast<long>(xCm),
    static_cast<long>(yCm),
    static_cast<unsigned>(SAMPLES_PER_POINT)
  );

  uint32_t nextSampleTime = millis();

  for (size_t sampleIndex = 0;
       sampleIndex < SAMPLES_PER_POINT;
       ++sampleIndex) {
    while (static_cast<int32_t>(millis() - nextSampleTime) < 0) {
      delay(1);
    }

    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("ERROR,WIFI_DISCONNECTED_DURING_MEASUREMENT");
      return;
    }

    const uint32_t sampleTime = millis();
    const int32_t rssiDbm = WiFi.RSSI();

    Serial.printf(
      "DATA,%ld,%ld,%u,%lu,%ld\n",
      static_cast<long>(xCm),
      static_cast<long>(yCm),
      static_cast<unsigned>(sampleIndex),
      static_cast<unsigned long>(sampleTime),
      static_cast<long>(rssiDbm)
    );

    nextSampleTime += SAMPLE_INTERVAL_MS;
  }

  Serial.printf(
    "DONE,%ld,%ld,%u\n",
    static_cast<long>(xCm),
    static_cast<long>(yCm),
    static_cast<unsigned>(SAMPLES_PER_POINT)
  );
  Serial.println("READY");
}

void handleCommand() {
  if (strcmp(commandBuffer, "PING") == 0) {
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("READY");
    } else {
      Serial.println("ERROR,WIFI_NOT_CONNECTED");
    }
    return;
  }

  int32_t xCm = 0;
  int32_t yCm = 0;

  if (!parseMeasurementCommand(xCm, yCm)) {
    Serial.println("ERROR,EXPECTED_MEASURE_X_Y");
    return;
  }

  measurePoint(xCm, yCm);
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(WIFI_RETRY_DELAY_MS);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);

  connectToHotspot();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    delay(WIFI_RETRY_DELAY_MS);
    connectToHotspot();
    return;
  }

  if (readCommandLine()) {
    handleCommand();
  }
}
