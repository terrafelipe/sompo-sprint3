// Sensor de chama KY-026 (A0 analogico).
#pragma once
#include "config.h"
#include "estado.h"
#include "evento.h"

namespace Chama {
#if USAR_CHAMA
  bool anterior = false;
  int  leituraRaw = 4095;   // ultimo A0 lido (0-4095); alto = sem chama

  // O D0 (digital) deste KY-026 queimou numa inversao de VCC/GND - fica travado.
  // O estagio analogico (A0) sobreviveu: o raw CAI em direcao a 0 quanto mais
  // perto a chama. Lemos A0 no GPIO35 (ADC1, que aguenta o Wi-Fi; o antigo D0/25
  // era ADC2 e o ADC2 morre com o radio ligado) e aplicamos LIMIAR_CHAMA por
  // software. GPIO34 e so-de-entrada: nao precisa de pinMode.
  void iniciar() {}
  void ler() {
    leituraRaw = analogRead(CHAMA_PIN);
    Estado.chamaDetectada = leituraRaw < LIMIAR_CHAMA;   // perto da chama = raw baixo
  }
  void eventos() {
    if (Estado.chamaDetectada && !anterior) {
      char det[48];
      snprintf(det, sizeof(det), "{\"sensor\":\"ky026\",\"a0\":%d}", leituraRaw);
      Evento::disparar("INCENDIO", "chama detectada", "chama_detectada", 5, det);
    }
    anterior = Estado.chamaDetectada;
  }
  // Imprime o raw SEMPRE: e assim que se calibra o LIMIAR_CHAMA - anote o valor
  // parado (baseline) e o valor com a chama na distancia desejada; ponha o limiar no meio.
  void imprimir() {
    Serial.printf("Chama: A0=%d (limiar %d)%s\n", leituraRaw, LIMIAR_CHAMA,
                  Estado.chamaDetectada ? "  <-- CHAMA DETECTADA" : "");
  }
  void telemetria(Json &j) {
    j.add(",\"chama_detectada\":%s", Estado.chamaDetectada ? "true" : "false");
  }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void eventos() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}
