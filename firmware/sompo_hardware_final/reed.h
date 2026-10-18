// Reed switches do capo e do tanque.
#pragma once
#include "config.h"
#include "estado.h"
#include "alarme.h"
#include "evento.h"

// Reed switches: modulos ativos com comparador (A0/G/+/D0), so o DO e usado -
// o DO ja vem "empurrado", entao nao leva pullup.
namespace Reed {
#if USAR_REED_CAPO || USAR_REED_TANQUE
  bool capoAnterior = false, tanqueAnterior = false;
  bool capoBeepAnt = false, tanqueBeepAnt = false;   // estado anterior SO p/ o bipe de feedback

  void iniciar() {
#if USAR_REED_CAPO
    pinMode(REED_CAPO, INPUT);
#endif
#if USAR_REED_TANQUE
    pinMode(REED_TANQUE, INPUT);
#endif
  }
  void ler() {
#if USAR_REED_CAPO
    Estado::capoAberto = digitalRead(REED_CAPO) == HIGH;    // HIGH = contato aberto
    // Bipe curto a cada troca de estado (ima encostado/retirado no reed do capo).
    if (Estado::capoAberto != capoBeepAnt) { Alarme::bipeToque(); capoBeepAnt = Estado::capoAberto; }
#endif
#if USAR_REED_TANQUE
    Estado::tanqueAberto = digitalRead(REED_TANQUE) == HIGH;
    if (Estado::tanqueAberto != tanqueBeepAnt) { Alarme::bipeToque(); tanqueBeepAnt = Estado::tanqueAberto; }
#endif
  }
  void eventos() {
#if USAR_REED_CAPO
    if (Estado::capoAberto && !capoAnterior && !Estado::motorLigado && !Estado::operadorAutorizado)
      Evento::disparar("AVISO", "capo aberto com a maquina desligada",
                       "furto_capo", 2, "{\"sensor\":\"reed_capo\"}");
    capoAnterior = Estado::capoAberto;
#endif
#if USAR_REED_TANQUE
    if (Estado::tanqueAberto && !tanqueAnterior && !Estado::motorLigado && !Estado::operadorAutorizado)
      Evento::disparar("AVISO", "tanque aberto com a maquina desligada",
                       "furto_tanque", 3, "{\"sensor\":\"reed_tanque\"}");
    tanqueAnterior = Estado::tanqueAberto;
#endif
  }
  void imprimir() {
#if USAR_REED_CAPO
    Serial.printf("Capo: %s\n", Estado::capoAberto ? "ABERTO" : "fechado");
#endif
#if USAR_REED_TANQUE
    Serial.printf("Tanque: %s\n", Estado::tanqueAberto ? "ABERTO" : "fechado");
#endif
  }
  void telemetria(Json &j) {
#if USAR_REED_CAPO
    j.add(",\"capo_aberto\":%s", Estado::capoAberto ? "true" : "false");
#endif
#if USAR_REED_TANQUE
    j.add(",\"tanque_aberto\":%s", Estado::tanqueAberto ? "true" : "false");
#endif
  }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void eventos() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}
