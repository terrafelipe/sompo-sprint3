// Sensor AHT10 (temperatura ambiente e umidade).
#pragma once
#include "bibliotecas.h"
#include "estado.h"

namespace Aht {
#if USAR_AHT
  Adafruit_AHTX0 dev;
  bool ok = false;

  void iniciar() {
    if (!dev.begin()) { Serial.println("ERRO: AHT10 nao encontrado! (0x38 no scanner?)"); return; }
    ok = true;
    Serial.println("AHT10 OK");
  }
  void ler() {
    if (!ok) return;
    sensors_event_t umid, temp;
    dev.getEvent(&umid, &temp);
    Estado::umidadeAr = umid.relative_humidity;
    Estado::tempAmbiente = temp.temperature;
  }
  void imprimir() {
    if (!ok) { Serial.println("AHT10 indisponivel (falhou no setup)"); return; }
    Serial.printf("Ambiente: %.1f C | %.1f %% UR\n", Estado::tempAmbiente, Estado::umidadeAr);
  }
  void telemetria(Json &j) {
    if (!ok) return;
    j.add(",\"temp_ambiente\":%.1f,\"umidade_ar\":%.1f", Estado::tempAmbiente, Estado::umidadeAr);
  }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}
