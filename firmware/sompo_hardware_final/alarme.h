// Buzzer: bipes de feedback e alarme continuo.
#pragma once
#include "config.h"
#include "estado.h"

// Bipe que vira no-op sem o buzzer montado - chama e furto chamam sem saber.
namespace Alarme {
#if USAR_BUZZER
  void iniciar() { pinMode(BUZZER_PIN, OUTPUT); }
  void beep(unsigned f, unsigned long d) { tone(BUZZER_PIN, f, d); }
  void continuo(unsigned f) { tone(BUZZER_PIN, f); }   // sem duracao: toca ate noTone()
  void parar() { noTone(BUZZER_PIN); }
  void autoteste() { Serial.println("Buzzer - bipe de teste"); beep(BUZZER_FREQ_FURTO, 200); delay(300); }

  // --- Bipes curtos de FEEDBACK (cracha/ima), distintos do alarme continuo. ---
  // Bloqueiam ~80-520 ms DE PROPOSITO (mesmo padrao do autoteste). Sao chamados nos
  // ler() ANTES de Alarme::atualizar() no mesmo ciclo, entao o bipe completa e o
  // alarme continuo (se houver ameaca) e reavaliado logo depois - fogo tem prioridade.
  void bipeConfirma() {                 // cracha AUTORIZADO: 2 bipes curtos ascendentes
    beep(1500, 120); delay(150);
    beep(2500, 120); delay(150);
    noTone(BUZZER_PIN);
  }
  void bipeNega() {                     // cracha NAO autorizado: 1 bipe longo grave
    beep(400, 500); delay(520);
    noTone(BUZZER_PIN);
  }
  void bipeToque() {                    // ima encostado/retirado do reed: 1 bipe curtinho
    beep(1200, 80); delay(90);
    noTone(BUZZER_PIN);
  }

  // Alarme CONTINUO: enquanto houver ameaca ativa o buzzer nao para; sem ameaca,
  // silencia. Chamado todo ciclo (100 ms) no loop(). Fogo tem prioridade e tom proprio.
  void atualizar() {
    bool fogo  = Estado::chamaDetectada || Estado::tempEscape >= TEMP_ESCAPE_ATENCAO;
    // Furto so soa ARMADO (sem cracha). Passar o cracha (desarmar) cala o furto -
    // mas NUNCA o fogo. Ligada e sem cracha ja e furto por si so.
    bool furto = !Estado::operadorAutorizado &&
                 ((!Estado::motorLigado &&
                    (Estado::vibracaoConfirmada || Estado::capoAberto || Estado::tanqueAberto))
                  || Estado::motorLigado);
    if (fogo)       continuo(BUZZER_FREQ_CHAMA);
    else if (furto) continuo(BUZZER_FREQ_FURTO);
    else            parar();
  }
#else
  inline void iniciar() {}
  inline void beep(unsigned, unsigned long) {}
  inline void continuo(unsigned) {}
  inline void parar() {}
  inline void autoteste() {}
  inline void atualizar() {}
  inline void bipeConfirma() {}
  inline void bipeNega() {}
  inline void bipeToque() {}
#endif
}
