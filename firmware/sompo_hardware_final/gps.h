// GPS NEO-6M.
#pragma once
#include "bibliotecas.h"

namespace Gps {
#if USAR_GPS
  TinyGPSPlus dev;
  HardwareSerial porta(2);

  void iniciar() {
    porta.begin(GPS_BAUD, SERIAL_8N1, GPS_RX, GPS_TX);
    Serial.println("GPS - aguardando fix...");
  }
  void ler() { while (porta.available() > 0) dev.encode(porta.read()); }
  void imprimir() {
    if (dev.location.isValid())
      Serial.printf("GPS: Lat=%.6f Lon=%.6f\n", dev.location.lat(), dev.location.lng());
    else
      Serial.println("GPS: sem fix ainda");
  }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void imprimir() {}
#endif
}
