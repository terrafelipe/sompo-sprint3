// Termopar MAX6675 (temperatura do escape).
#pragma once
#include "bibliotecas.h"
#include "estado.h"
#include "evento.h"

namespace Termopar {
#if USAR_TERMOPAR
  // Lib RobTillaart: construtor (select, miso, clock) - CS primeiro, nao o clock.
  // Pinos PROPRIOS (13/4), fora do SPI do RC522: o modulo MAX6675 nao libera a
  // linha MISO quando nao esta selecionado e travava a leitura do cartao.
  MAX6675 dev(TERMOPAR_CS, TERMOPAR_SO, TERMOPAR_SCK);
  bool ok = false;
  bool atencaoAnterior = false, criticoAnterior = false;

  void iniciar() { dev.begin(); Serial.println("MAX6675 iniciado"); }

  void ler() {
    if (dev.read() == STATUS_OK) { Estado.tempEscape = dev.getCelsius(); ok = true; }
    else                         { ok = false; }   // mantem o ultimo valor valido
  }

  void eventos() {
    bool critico = Estado.tempEscape >= TEMP_ESCAPE_CRITICO;
    bool atencao = Estado.tempEscape >= TEMP_ESCAPE_ATENCAO;
    char det[64];
    if (critico && !criticoAnterior) {
      snprintf(det, sizeof(det), "{\"limiar_c\":%.0f}", (float)TEMP_ESCAPE_CRITICO);
      Evento::disparar("INCENDIO", "temperatura do escape critica", "escape_critico", 4, det);
    } else if (atencao && !critico && !atencaoAnterior) {
      snprintf(det, sizeof(det), "{\"limiar_c\":%.0f}", (float)TEMP_ESCAPE_ATENCAO);
      Evento::disparar("INCENDIO", "temperatura do escape em atencao", "escape_atencao", 2, det);
    }
    criticoAnterior = critico;
    atencaoAnterior = atencao;
  }

  void imprimir() {
    if (ok) Serial.printf("Termopar: %.1f C\n", Estado.tempEscape);
    else    Serial.println("Termopar: erro de leitura (confira fiacao/CS)");
  }
  void telemetria(Json &j) { if (ok) j.add(",\"temp_escape\":%.1f", Estado.tempEscape); }
#else
  const bool ok = false;
  inline void iniciar() {}
  inline void ler() {}
  inline void eventos() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}
