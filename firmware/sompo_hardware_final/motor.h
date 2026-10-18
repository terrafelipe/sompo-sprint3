// Potenciometro que simula a ignicao.
#pragma once
#include "config.h"
#include "estado.h"
#include "evento.h"

// Potenciometro simula a ignicao que, no produto final, viria do veiculo.
namespace Motor {
#if USAR_POT
  bool anterior = false;

  void ler() {
    // O pot so diz se a maquina esta ligada. Quem arma/desarma e SO o cracha
    // (Rfid::ler) - por isso nao mexemos em operadorAutorizado aqui (antes, o
    // ruido do pot perto do limiar zerava a autorizacao sozinho).
    Estado.motorLigado = analogRead(POT_PIN) >= LIMIAR_POT_MOTOR_DESLIGADO;
  }
  void eventos() {
    if (Estado.motorLigado && !anterior && !Estado.operadorAutorizado)
      Evento::disparar("FURTO", "partida sem cracha autorizado - possivel roubo",
                       "operador_nao_autorizado", 3, "{\"origem\":\"rc522\"}");
    anterior = Estado.motorLigado;
  }
  void imprimir() {
    Serial.printf("Motor: %s | operador: %s\n",
                  Estado.motorLigado ? "LIGADO" : "desligado",
                  Estado.operadorAutorizado ? "autorizado" : "sem cracha");
  }
  void telemetria(Json &j) {
    j.add(",\"motor_ligado\":%s", Estado.motorLigado ? "true" : "false");
  }
#else
  inline void ler() {}
  inline void eventos() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}
