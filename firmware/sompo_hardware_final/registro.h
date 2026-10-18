// O que vai para a fila: amostra periodica de telemetria e eventos.
#pragma once
#include "bibliotecas.h"
#include "estado.h"
#include "frota.h"
#include "rede.h"
#include "termopar.h"
#include "aht.h"
#include "chama.h"
#include "mpu.h"
#include "motor.h"
#include "reed.h"
#include "rfid.h"
#include "evento.h"

// ---------------------------------------------------------------------------
// Telemetria: uma amostra periodica com o retrato do estado
// ---------------------------------------------------------------------------
namespace Telemetria {
#if USAR_WIFI || DIAG_TELEMETRIA
  void montar(Json &j) {
    j.add("{");
#if USAR_WIFI
    Frota::metadados(j);
#else
    j.add("\"dispositivo_id\":\"%s\"", DISPOSITIVO_ID);
#endif
    Termopar::telemetria(j);
    Aht::telemetria(j);
    Chama::telemetria(j);
    Mpu::telemetria(j);
    Motor::telemetria(j);
    Reed::telemetria(j);
    Rfid::telemetria(j);
    j.add(",\"nivel_risco\":\"%s\"}", Estado.nivelRisco);
  }

  void enviar() {
    Json j;
    montar(j);
#if DIAG_TELEMETRIA
    Serial.printf("[TELEMETRIA] %s\n", j.txt);
#endif
#if USAR_WIFI
    // Sobrescreve: se a anterior ainda nao saiu, a leitura de agora vale mais.
    if (Rede::caixaTelemetria) {
      Rede::Payload p;
      strncpy(p.categoria, "telemetria", sizeof(p.categoria) - 1);
      p.categoria[sizeof(p.categoria) - 1] = '\0';
      memcpy(p.json, j.txt, j.n + 1);
      xQueueOverwrite(Rede::caixaTelemetria, &p);
    }
#endif
  }
#else
  inline void enviar() {}
#endif
}

// ---------------------------------------------------------------------------
// Evento: mensagem legivel no Serial + linha para o Supabase
// ---------------------------------------------------------------------------
// Os tipos precisam existir em api/scores.py, senao o evento chega ao banco
// mas nao pontua no score de risco.
namespace Evento {
  void disparar(const char* ctx, const char* msg, const char* tipo,
                int sev, const char* detalhes) {
    Serial.printf("[%s] %s\n", ctx, msg);
#if USAR_WIFI
    Json j;
    j.add("{");
    Frota::metadados(j);
    j.add(",\"tipo\":\"%s\",\"severidade\":%d", tipo, sev);
    if (Termopar::ok) j.add(",\"temp_escape\":%.1f", Estado.tempEscape);
    j.add(",\"detalhes\":%s}", detalhes);
    if (!Frota::anexarDuravel("eventos", j.txt))
      Serial.println("[EVENTO] falha ao persistir evidencia");
#else
    (void)tipo; (void)sev; (void)detalhes;
#endif
  }
}
