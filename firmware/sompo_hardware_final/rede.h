// Wi-Fi, NTP e envio ao Supabase (tarefa propria; o loop nunca posta).
#pragma once
#include "bibliotecas.h"
#include "estado.h"
#include "frota.h"

// Intervalo da telemetria: o painel liga o modo ao vivo no banco e a resposta de cada
// envio diz o intervalo. Escrito pela tarefa de rede (nucleo 0), lido pelo loop (nucleo 1).
volatile uint32_t intervaloTelemetria = INTERVALO_TELEMETRIA_MS;

// So aceita os dois valores conhecidos: um valor estranho do servidor nao derruba a placa.
uint32_t intervaloDaResposta(const String &corpo) {
  int k = corpo.indexOf("\"telemetria_ms\"");
  if (k < 0) return INTERVALO_TELEMETRIA_MS;
  int dp = corpo.indexOf(':', k);
  long v = dp < 0 ? 0 : corpo.substring(dp + 1).toInt();
  return v == INTERVALO_TELEMETRIA_AO_VIVO_MS ? INTERVALO_TELEMETRIA_AO_VIVO_MS : INTERVALO_TELEMETRIA_MS;
}

// ---------------------------------------------------------------------------
// Rede: Wi-Fi, NTP e envio ao Supabase (tarefa propria - o loop nunca posta)
// ---------------------------------------------------------------------------
namespace Rede {
#if USAR_WIFI
  struct Payload {
    char categoria[12];
    char json[TAM_PAYLOAD];
  };
  QueueHandle_t caixaTelemetria = NULL;
  unsigned long ok = 0, falha = 0;
  unsigned long ultimaTentativa = 0;
  unsigned long ultimaSincronia = 0;
  bool estavaConectado = false;

  // CA raiz que autentica o Supabase: Google Trust Services "GTS Root R4"
  // (self-signed, valido ate 2036). A cadeia real e supabase.co <- GTS WE1 <-
  // GTS Root R4; embutir o root basta para o mbedTLS validar tudo.
  const char ROOT_CA[] PROGMEM = R"CERT(
-----BEGIN CERTIFICATE-----
MIICCTCCAY6gAwIBAgINAgPlwGjvYxqccpBQUjAKBggqhkjOPQQDAzBHMQswCQYD
VQQGEwJVUzEiMCAGA1UEChMZR29vZ2xlIFRydXN0IFNlcnZpY2VzIExMQzEUMBIG
A1UEAxMLR1RTIFJvb3QgUjQwHhcNMTYwNjIyMDAwMDAwWhcNMzYwNjIyMDAwMDAw
WjBHMQswCQYDVQQGEwJVUzEiMCAGA1UEChMZR29vZ2xlIFRydXN0IFNlcnZpY2Vz
IExMQzEUMBIGA1UEAxMLR1RTIFJvb3QgUjQwdjAQBgcqhkjOPQIBBgUrgQQAIgNi
AATzdHOnaItgrkO4NcWBMHtLSZ37wWHO5t5GvWvVYRg1rkDdc/eJkTBa6zzuhXyi
QHY7qca4R9gq55KRanPpsXI5nymfopjTX15YhmUPoYRlBtHci8nHc8iMai/lxKvR
HYqjQjBAMA4GA1UdDwEB/wQEAwIBhjAPBgNVHRMBAf8EBTADAQH/MB0GA1UdDgQW
BBSATNbrdP9JNqPV2Py1PsVq8JQdjDAKBggqhkjOPQQDAwNpADBmAjEA6ED/g94D
9J+uHXqnLrmvT/aDHQ4thQEd0dlq7A/Cr8deVl5c1RxYIigL9zC2L7F8AjEA8GE8
p/SgguMh1YQdc4acLa/KNJvxn7kjNuK8YAOdgLOaVsjh4rsUecrNIdSUtUlD
-----END CERTIFICATE-----
)CERT";

  // Resultado do envio: ENVIADO; FALHOU (rede, 5xx, token... tenta de novo depois);
  // RECUSADO = o servidor recusou ESTE registro em definitivo e reenviar nunca vai passar.
  enum Envio { ENVIADO, FALHOU, RECUSADO };

  // Uma conexao TLS so, reaproveitada entre os envios: abrir uma por POST custava ~3 s de
  // aperto de mao (o "chegou em" do ao vivo). Falhou? clienteTls.stop() e o proximo reabre.
  // O HTTPClient tambem e unico: o destrutor dele fecha o cliente, entao um local por envio
  // derrubaria a conexao no fim de cada chamada.
  WiFiClientSecure clienteTls;
  HTTPClient httpEnvio;
  bool clienteTlsPronto = false;

  Envio postarRpc(const char* categoria, const char* json) {
    if (!clienteTlsPronto) {
      // Autentica pelo CA raiz embutido. O firmware antigo usava setInsecure()
      // porque o simulador nao trazia o bundle de CAs; com internet real nao ha
      // motivo para aceitar qualquer certificado.
      clienteTls.setCACert(ROOT_CA);
      clienteTls.setTimeout(TIMEOUT_HTTP / 1000);
      clienteTlsPronto = true;
    }

    char url[192];
    snprintf(url, sizeof(url), "%s/rest/v1/rpc/registrar_dispositivo", SUPABASE_URL_CFG);

    HTTPClient &http = httpEnvio;
    const bool reaproveitada = clienteTls.connected();
    const unsigned long t0 = millis();
    if (!http.begin(clienteTls, url)) { Serial.println("[REDE] http.begin() falhou"); return FALHOU; }
    http.setTimeout(TIMEOUT_HTTP);
    http.addHeader("apikey", SUPABASE_CHAVE_CFG);
    http.addHeader("Authorization", "Bearer " SUPABASE_CHAVE_CFG);
    http.addHeader("Content-Type", "application/json");
    String corpo = "{\"p_dispositivo_id\":\"" DISPOSITIVO_ID "\",\"p_token\":\"";
    corpo += DISPOSITIVO_TOKEN_CFG;
    corpo += "\",\"p_categoria\":\"";
    corpo += categoria;
    corpo += "\",\"p_registro\":";
    corpo += json;
    corpo += '}';
    int codigo = http.POST((uint8_t*)corpo.c_str(), corpo.length());
    Envio resultado = (codigo >= 200 && codigo < 300) ? ENVIADO : FALHOU;
    // Diagnostico: quanto o POST leva e se a conexao veio pronta (some quando o envio ficar estavel).
    Serial.printf("[REDE] POST %s HTTP %d em %lu ms (%s)\n", categoria, codigo,
                  millis() - t0, reaproveitada ? "conexao reaproveitada" : "conexao nova");
    if (resultado == ENVIADO) {
      uint32_t novo = intervaloDaResposta(http.getString());
      if (novo != intervaloTelemetria) {
        Serial.printf("[REDE] telemetria a cada %lu s%s\n", (unsigned long)(novo / 1000),
                      novo == INTERVALO_TELEMETRIA_AO_VIVO_MS ? " (ao vivo)" : "");
        intervaloTelemetria = novo;
      }
    }
    if (resultado != ENVIADO) {
      // O corpo do erro do PostgREST diz exatamente o que esta errado (coluna
      // inexistente, RLS negando, JSON invalido). Sem isso a depuracao e cega.
      String erro = (codigo > 0) ? http.getString() : String(http.errorToString(codigo));
      Serial.printf("[REDE] falha no envio - %s HTTP %d: %.120s\n", categoria, codigo, erro.c_str());
      // Registro gravado com o ID antigo do ESP32 (a maquina trocou de ID): o token
      // ja foi aceito, entao o problema e so este registro. Sem descartar, ele
      // travaria a fila para sempre. Token invalido (28000) ou permissao geral
      // negada tem outra mensagem e continua na fila.
      if (codigo >= 400 && codigo < 500 && erro.indexOf("42501") >= 0 &&
          erro.indexOf("alheio a credencial") >= 0) resultado = RECUSADO;
    }
    http.end();
    if (resultado != ENVIADO) clienteTls.stop();   // conexao suspeita: o proximo envio abre outra
    return resultado;
  }

  bool sincronizar() {
    clienteTls.stop();   // so uma sessao TLS viva por vez (RAM)
    WiFiClientSecure cliente;
    cliente.setCACert(ROOT_CA);
    cliente.setTimeout(TIMEOUT_HTTP / 1000);
    char url[192];
    snprintf(url, sizeof(url), "%s/rest/v1/rpc/sincronizar_dispositivo", SUPABASE_URL_CFG);
    HTTPClient http;
    if (!http.begin(cliente, url)) return false;
    http.setTimeout(TIMEOUT_HTTP);
    http.addHeader("apikey", SUPABASE_CHAVE_CFG);
    http.addHeader("Authorization", "Bearer " SUPABASE_CHAVE_CFG);
    http.addHeader("Content-Type", "application/json");
    String corpo = "{\"p_dispositivo_id\":\"" DISPOSITIVO_ID "\",\"p_token\":\"";
    corpo += DISPOSITIVO_TOKEN_CFG;
    corpo += "\"}";
    int codigo = http.POST((uint8_t*)corpo.c_str(), corpo.length());
    String resposta = codigo >= 200 && codigo < 300 ? http.getString() : String();
    http.end();
    bool sucesso = codigo >= 200 && codigo < 300 && Frota::aplicarConfig(resposta);
    if (sucesso) Serial.printf("[FROTA] autorizacoes sincronizadas: versao %llu, %u operador(es)\n",
                               (unsigned long long)Frota::configVersao, (unsigned)Frota::totalOperadores);
    else Serial.printf("[FROTA] sincronizacao falhou HTTP %d; cache preservado\n", codigo);
    return sucesso;
  }

  // Consome primeiro a trilha duravel; telemetria usa uma caixa sobrescrita.
  void tarefa(void*) {
    Payload p;
    for (;;) {
      if (WiFi.status() != WL_CONNECTED) { vTaskDelay(pdMS_TO_TICKS(PAUSA_SEM_REDE)); continue; }
      if (!ultimaSincronia || millis() - ultimaSincronia >= INTERVALO_SINCRONIA_MS) {
        ultimaSincronia = millis();
        sincronizar();
      }

      String categoria, json;
      if (Frota::proximoDuravel(categoria, json)) {
        Envio envio = FALHOU;
        for (int t = 1; t <= MAX_TENTATIVAS_ENVIO && envio == FALHOU; t++) {
          envio = postarRpc(categoria.c_str(), json.c_str());
          if (envio == FALHOU) vTaskDelay(pdMS_TO_TICKS(500 * t));   // recuo progressivo
        }
        if (envio == RECUSADO && Frota::confirmarDuravel()) {
          falha++;
          Serial.printf("[FROTA] registro %s de outro ID do ESP32 descartado da fila\n", categoria.c_str());
        } else if (envio == ENVIADO && Frota::confirmarDuravel()) { ok++; }
        else {
          falha++;
          vTaskDelay(pdMS_TO_TICKS(PAUSA_SEM_REDE));
        }
      } else if (xQueueReceive(caixaTelemetria, &p, 0) == pdTRUE) {
        // Telemetria nao volta para a fila: a proxima amostra ja e melhor.
        if (postarRpc(p.categoria, p.json) == ENVIADO) ok++; else falha++;
      } else {
        vTaskDelay(pdMS_TO_TICKS(PAUSA_ENVIO));
        continue;
      }
      vTaskDelay(pdMS_TO_TICKS(PAUSA_ENVIO));
    }
  }

  void iniciar() {
    caixaTelemetria = xQueueCreate(1, sizeof(Payload));
    if (!caixaTelemetria) {
      Serial.println("ERRO: sem RAM para telemetria - envio desativado");
    } else {
      // Nucleo 0, 8 KB de pilha (o handshake TLS e faminto). Prioridade 1 =
      // abaixo do loop(), entao o ciclo de sensores sempre ganha.
      xTaskCreatePinnedToCore(tarefa, "envio", 8192, NULL, 1, NULL, 0);
      Serial.println("Tarefa de envio ao Supabase ativa");
    }
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID_CFG, WIFI_PASSWORD_CFG);
    ultimaTentativa = millis();
    Serial.printf("Wi-Fi: conectando em \"%s\" (precisa ser 2.4 GHz)\n", WIFI_SSID_CFG);
  }

  void manter() {
    bool conectado = (WiFi.status() == WL_CONNECTED);
    if (conectado && !estavaConectado) {
      Serial.print("[SISTEMA] Wi-Fi conectado, IP ");
      Serial.println(WiFi.localIP());
      configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);
    }
    if (!conectado && estavaConectado) Serial.println("[SISTEMA] Wi-Fi caiu, reconectando...");
    estavaConectado = conectado;

    if (conectado) return;
    if (millis() - ultimaTentativa >= INTERVALO_TENTATIVA_WIFI) {
      ultimaTentativa = millis();
      WiFi.begin(WIFI_SSID_CFG, WIFI_PASSWORD_CFG);
    }
  }

  void imprimir() {
    Serial.printf("Rede: %s | envios ok=%lu falha=%lu\n",
                  WiFi.status() == WL_CONNECTED ? "conectado" : "SEM WI-FI", ok, falha);
  }
#else
  inline void iniciar() {}
  inline void manter() {}
  inline void imprimir() {}
#endif
}
