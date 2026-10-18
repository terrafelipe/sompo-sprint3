// Bibliotecas de cada sensor (so entram com a flag USAR_* ligada).
#pragma once
#include "config.h"

#include <Wire.h>
#include <stdarg.h>
#if USAR_RFID || USAR_TERMOPAR
  #include <SPI.h>
#endif
#if USAR_MPU
  #include <Adafruit_MPU6050.h>
#endif
#if USAR_AHT
  #include <Adafruit_AHTX0.h>
#endif
#if USAR_MPU || USAR_AHT
  #include <Adafruit_Sensor.h>
#endif
#if USAR_GPS
  #include <TinyGPSPlus.h>
#endif
#if USAR_RFID
  #include <MFRC522.h>
#endif
#if USAR_TERMOPAR
  #include <MAX6675.h>
#endif
#if USAR_WIFI
  #include <WiFi.h>
  #include <WiFiClientSecure.h>
  #include <HTTPClient.h>
  #include <LittleFS.h>
  #include <time.h>
  #include "segredos.h"
#endif
