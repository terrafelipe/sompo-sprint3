// Leitor RFID RC522 (cracha arma/desarma).
#pragma once
#include "bibliotecas.h"
#include "estado.h"
#include "frota.h"
#include "alarme.h"

namespace Rfid {
#if USAR_RFID
  MFRC522 dev(RFID_SS, RFID_RST);
  unsigned long ultimoToque = 0;   // anti-repique: 1 arma/desarma por aproximacao

  void iniciar() { dev.PCD_Init(); Serial.println("RC522 OK"); }

  void ler() {
    if (!dev.PICC_IsNewCardPresent() || !dev.PICC_ReadCardSerial()) return;
    char uid[21] = "";
    size_t cursor = 0;
    Serial.print("RFID detectado - UID:");
    for (byte i = 0; i < dev.uid.size; i++) {
      Serial.print(dev.uid.uidByte[i] < 0x10 ? " 0" : " ");
      Serial.print(dev.uid.uidByte[i], HEX);
      if (cursor + 2 < sizeof(uid)) cursor += snprintf(uid + cursor, sizeof(uid) - cursor, "%02X", dev.uid.uidByte[i]);
    }
    if (millis() - ultimoToque > 1500) {
      ultimoToque = millis();
      Frota::ResultadoCracha resultado = Frota::processarCracha(uid);
      if (resultado == Frota::NEGADO) {
        Serial.println("  -> nao autorizado");
        Alarme::bipeNega();
      } else if (resultado == Frota::FALHA_PERSISTENCIA) {
        Serial.println("  -> falha ao gravar historico; sessao nao confirmada");
        Alarme::bipeNega();
      } else {
        const char* estado = resultado == Frota::INICIO ? "SESSAO INICIADA" :
                             resultado == Frota::FIM ? "SESSAO ENCERRADA" : "OPERADOR TROCADO";
        Serial.printf("  -> %s\n", estado);
        Alarme::bipeConfirma();
      }
    }
    dev.PICC_HaltA();
  }
  void telemetria(Json &j) {
    j.add(",\"operador_autorizado\":%s", Estado.operadorAutorizado ? "true" : "false");
  }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void telemetria(Json&) {}
#endif
}
