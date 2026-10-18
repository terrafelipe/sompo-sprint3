// Identidade da maquina, autorizacoes RFID e trilha duravel (LittleFS).
#pragma once
#include "bibliotecas.h"
#include "estado.h"

// ---------------------------------------------------------------------------
// Identidade da maquina, autorizacoes RFID e trilha duravel.
// Eventos e transicoes so sao confirmados depois de gravados no LittleFS.
// ---------------------------------------------------------------------------
namespace Frota {
#if USAR_WIFI
  struct Operador { uint64_t id; char uid[21]; };
  enum ResultadoCracha { NEGADO, INICIO, FIM, TROCA, FALHA_PERSISTENCIA };

  Operador operadores[MAX_OPERADORES_CACHE];
  size_t totalOperadores = 0;
  uint64_t equipamentoId = 0, configVersao = 1, sequencia = 0;
  uint64_t operadorAtual = 0;
  char uidAtual[21] = "", sessaoAtual[37] = "", bootId[37] = "";
  bool armazenamentoOK = false;
  SemaphoreHandle_t mutexArquivos = NULL;

  const char* ARQ_FILA = "/fila.ndjson";
  const char* ARQ_FILA_BAK = "/fila.bak";
  const char* ARQ_CONFIG = "/frota.cfg";
  const char* ARQ_SESSAO = "/sessao.cfg";

  bool encerrarSessao(const char* motivo);
  uint64_t operadorPorUid(const char* uid);

  void uuid(char* out) {
    uint8_t b[16];
    for (byte i = 0; i < 16; i += 4) {
      uint32_t r = esp_random();
      memcpy(b + i, &r, 4);
    }
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    snprintf(out, 37,
      "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
      b[0],b[1],b[2],b[3],b[4],b[5],b[6],b[7],b[8],b[9],b[10],b[11],b[12],b[13],b[14],b[15]);
  }

  bool carimboISO(char* txt, size_t n) {
    struct tm t;
    if (!getLocalTime(&t, 5)) return false;
    snprintf(txt, n, "%04d-%02d-%02dT%02d:%02d:%02d%+03d:00",
             t.tm_year + 1900, t.tm_mon + 1, t.tm_mday,
             t.tm_hour, t.tm_min, t.tm_sec, GMT_OFFSET_SEC / 3600);
    return true;
  }

  void metadados(Json &j, const char* registroId = NULL,
                 uint64_t operador = UINT64_MAX, const char* sessao = NULL,
                 const char* uid = NULL) {
    char id[37];
    if (!registroId) { uuid(id); registroId = id; }
    if (operador == UINT64_MAX) operador = operadorAtual;
    if (!sessao) sessao = sessaoAtual;
    if (!uid) uid = uidAtual;
    j.add("\"registro_id\":\"%s\",\"dispositivo_id\":\"%s\"", registroId, DISPOSITIVO_ID);
    if (equipamentoId) j.add(",\"equipamento_id\":%llu", (unsigned long long)equipamentoId);
    if (operador) j.add(",\"operador_id\":%llu", (unsigned long long)operador);
    if (sessao && sessao[0]) j.add(",\"sessao_id\":\"%s\"", sessao);
    if (uid && uid[0]) j.add(",\"uid\":\"%s\"", uid);
    j.add(",\"config_versao\":%llu,\"boot_id\":\"%s\",\"sequencia\":%llu,\"uptime_ms\":%lu",
          (unsigned long long)configVersao, bootId,
          (unsigned long long)sequencia++, millis());
    char quando[40];
    if (carimboISO(quando, sizeof(quando))) j.add(",\"ocorrido_em\":\"%s\"", quando);
  }

  bool anexarDuravel(const char* categoria, const char* json) {
    if (!armazenamentoOK || !mutexArquivos) return false;
    xSemaphoreTake(mutexArquivos, portMAX_DELAY);
    File atual = LittleFS.open(ARQ_FILA, FILE_READ);
    size_t tamanho = atual ? atual.size() : 0;
    if (atual) atual.close();
    size_t necessario = strlen(categoria) + strlen(json) + 2;
    if (tamanho + necessario > LIMITE_FILA_DURAVEL) {
      xSemaphoreGive(mutexArquivos);
      Serial.println("[FROTA] fila duravel cheia; registro nao confirmado");
      return false;
    }
    File f = LittleFS.open(ARQ_FILA, FILE_APPEND);
    bool ok = f && f.print(categoria) && f.print('\t') && f.println(json);
    if (f) { f.flush(); f.close(); }
    xSemaphoreGive(mutexArquivos);
    return ok;
  }

  bool proximoDuravel(String &categoria, String &json) {
    if (!armazenamentoOK || !mutexArquivos) return false;
    xSemaphoreTake(mutexArquivos, portMAX_DELAY);
    File f = LittleFS.open(ARQ_FILA, FILE_READ);
    String linha = f ? f.readStringUntil('\n') : String();
    if (f) f.close();
    xSemaphoreGive(mutexArquivos);
    int tab = linha.indexOf('\t');
    if (tab < 1) return false;
    categoria = linha.substring(0, tab);
    json = linha.substring(tab + 1);
    json.trim();
    return json.length() > 1;
  }

  bool confirmarDuravel() {
    xSemaphoreTake(mutexArquivos, portMAX_DELAY);
    File origem = LittleFS.open(ARQ_FILA, FILE_READ);
    if (!origem) { xSemaphoreGive(mutexArquivos); return false; }
    origem.readStringUntil('\n');
    File destino = LittleFS.open("/fila.tmp", FILE_WRITE);
    bool ok = (bool)destino;
    uint8_t bloco[256];
    while (ok && origem.available()) {
      size_t n = origem.read(bloco, sizeof(bloco));
      ok = destino.write(bloco, n) == n;
    }
    origem.close();
    if (destino) { destino.flush(); destino.close(); }
    if (ok) {
      LittleFS.remove(ARQ_FILA_BAK);
      ok = LittleFS.rename(ARQ_FILA, ARQ_FILA_BAK);
      if (ok) ok = LittleFS.rename("/fila.tmp", ARQ_FILA);
      if (ok) LittleFS.remove(ARQ_FILA_BAK);
      else if (!LittleFS.exists(ARQ_FILA) && LittleFS.exists(ARQ_FILA_BAK))
        LittleFS.rename(ARQ_FILA_BAK, ARQ_FILA);
    } else LittleFS.remove("/fila.tmp");
    xSemaphoreGive(mutexArquivos);
    return ok;
  }

  uint64_t numeroApos(const String &s, const char* chave, int inicio = 0) {
    int p = s.indexOf(chave, inicio);
    if (p < 0) return 0;
    p += strlen(chave);
    while (p < (int)s.length() && (s[p] == ' ' || s[p] == ':')) p++;
    return strtoull(s.c_str() + p, NULL, 10);
  }

  String textoApos(const String &s, const char* chave, int inicio = 0) {
    int p = s.indexOf(chave, inicio);
    if (p < 0) return String();
    p = s.indexOf('"', p + strlen(chave));
    if (p < 0) return String();
    int fim = s.indexOf('"', p + 1);
    return fim < 0 ? String() : s.substring(p + 1, fim);
  }

  bool salvarConfig() {
    xSemaphoreTake(mutexArquivos, portMAX_DELAY);
    File f = LittleFS.open("/frota.tmp", FILE_WRITE);
    if (!f) { xSemaphoreGive(mutexArquivos); return false; }
    f.printf("%llu|%llu\n", (unsigned long long)equipamentoId, (unsigned long long)configVersao);
    for (size_t i = 0; i < totalOperadores; i++)
      f.printf("%llu|%s\n", (unsigned long long)operadores[i].id, operadores[i].uid);
    f.flush(); f.close();
    LittleFS.remove("/frota.bak");
    if (LittleFS.exists(ARQ_CONFIG)) LittleFS.rename(ARQ_CONFIG, "/frota.bak");
    bool ok = LittleFS.rename("/frota.tmp", ARQ_CONFIG);
    if (ok) LittleFS.remove("/frota.bak");
    else if (LittleFS.exists("/frota.bak")) LittleFS.rename("/frota.bak", ARQ_CONFIG);
    xSemaphoreGive(mutexArquivos);
    return ok;
  }

  void carregarConfig() {
    File f = LittleFS.open(ARQ_CONFIG, FILE_READ);
    if (!f) return;
    String cab = f.readStringUntil('\n');
    equipamentoId = strtoull(cab.c_str(), NULL, 10);
    int sep = cab.indexOf('|');
    if (sep >= 0) configVersao = strtoull(cab.c_str() + sep + 1, NULL, 10);
    totalOperadores = 0;
    while (f.available() && totalOperadores < MAX_OPERADORES_CACHE) {
      String linha = f.readStringUntil('\n'); linha.trim();
      sep = linha.indexOf('|');
      if (sep < 1) continue;
      operadores[totalOperadores].id = strtoull(linha.c_str(), NULL, 10);
      linha.substring(sep + 1).toCharArray(operadores[totalOperadores].uid, sizeof(operadores[0].uid));
      totalOperadores++;
    }
    f.close();
  }

  bool aplicarConfig(const String &corpo) {
    uint64_t equipamento = numeroApos(corpo, "\"equipamento_id\"");
    uint64_t versao = numeroApos(corpo, "\"versao\"");
    int lista = corpo.indexOf("\"operadores\"");
    if (!equipamento || !versao || lista < 0) return false;
    Operador novos[MAX_OPERADORES_CACHE];
    size_t total = 0;
    // Percorre objeto a objeto ({...}) porque o jsonb do Postgres ordena as chaves
    // por tamanho: "uid" vem antes de "operador_id", entao nao da para procurar
    // uma chave "a partir" da outra.
    int p = corpo.indexOf('[', lista);
    int fimLista = p < 0 ? -1 : corpo.indexOf(']', p);
    while (total < MAX_OPERADORES_CACHE && p >= 0 && fimLista >= 0) {
      int abre = corpo.indexOf('{', p);
      if (abre < 0 || abre > fimLista) break;
      int fecha = corpo.indexOf('}', abre);
      if (fecha < 0) break;
      String obj = corpo.substring(abre, fecha + 1);
      uint64_t id = numeroApos(obj, "\"operador_id\"");
      String uid = textoApos(obj, "\"uid\"");
      if (id && (uid.length() == 8 || uid.length() == 14 || uid.length() == 20)) {
        novos[total].id = id;
        uid.toUpperCase();
        uid.toCharArray(novos[total].uid, sizeof(novos[total].uid));
        total++;
      }
      p = fecha + 1;
    }
    equipamentoId = equipamento; configVersao = versao; totalOperadores = total;
    memcpy(operadores, novos, total * sizeof(Operador));
    bool salvo = salvarConfig();
    // Revoga se o cracha da sessao saiu da lista OU passou para outro operador
    // (UID de operador excluido reaproveitado): compara o id, nao so o UID.
    bool atualRevogado = sessaoAtual[0] && operadorPorUid(uidAtual) != operadorAtual;
    if (salvo && atualRevogado && !encerrarSessao("autorizacao_revogada"))
      Serial.println("[FROTA] revogacao recebida, mas encerramento aguarda espaco na fila");
    return salvo;
  }

  uint64_t operadorPorUid(const char* uid) {
    for (size_t i = 0; i < totalOperadores; i++)
      if (!strcmp(uid, operadores[i].uid)) return operadores[i].id;
    return 0;
  }

  bool registrarOperacao(const char* tipo, const char* motivo, const char* uid,
                         uint64_t operador, const char* sessao) {
    Json j; j.add("{");
    metadados(j, NULL, operador, sessao, uid);
    j.add(",\"tipo\":\"%s\"", tipo);
    if (motivo && motivo[0]) j.add(",\"motivo\":\"%s\"", motivo);
    j.add("}");
    return anexarDuravel("operacao", j.txt);
  }

  bool salvarSessao(const char* sessao, uint64_t operador, const char* uid) {
    xSemaphoreTake(mutexArquivos, portMAX_DELAY);
    File f = LittleFS.open(ARQ_SESSAO, FILE_WRITE);
    if (!f) { xSemaphoreGive(mutexArquivos); return false; }
    bool ok = f.printf("%s|%llu|%s\n", sessao, (unsigned long long)operador, uid) > 0;
    f.flush(); f.close();
    xSemaphoreGive(mutexArquivos);
    return ok;
  }

  bool comecarSessao(uint64_t operador, const char* uid) {
    char sessao[37]; uuid(sessao);
    if (!salvarSessao(sessao, operador, uid)) return false;
    if (!registrarOperacao("inicio", "rfid", uid, operador, sessao)) {
      LittleFS.remove(ARQ_SESSAO); return false;
    }
    operadorAtual = operador;
    strncpy(uidAtual, uid, sizeof(uidAtual) - 1);
    strncpy(sessaoAtual, sessao, sizeof(sessaoAtual) - 1);
    Estado.operadorAutorizado = true;
    return true;
  }

  bool encerrarSessao(const char* motivo) {
    if (!sessaoAtual[0]) return true;
    if (!registrarOperacao("fim", motivo, uidAtual, operadorAtual, sessaoAtual)) return false;
    LittleFS.remove(ARQ_SESSAO);
    operadorAtual = 0; uidAtual[0] = '\0'; sessaoAtual[0] = '\0';
    Estado.operadorAutorizado = false;
    return true;
  }

  ResultadoCracha processarCracha(const char* uid) {
    uint64_t operador = operadorPorUid(uid);
    if (!operador) {
      registrarOperacao("tentativa_negada", "cracha_nao_autorizado", uid, 0, "");
      return NEGADO;
    }
    if (!sessaoAtual[0]) return comecarSessao(operador, uid) ? INICIO : FALHA_PERSISTENCIA;
    if (operadorAtual == operador)
      return encerrarSessao("rfid") ? FIM : FALHA_PERSISTENCIA;
    if (!encerrarSessao("troca_operador")) return FALHA_PERSISTENCIA;
    return comecarSessao(operador, uid) ? TROCA : FALHA_PERSISTENCIA;
  }

  void recuperarInterrupcao() {
    File f = LittleFS.open(ARQ_SESSAO, FILE_READ);
    if (!f) return;
    String linha = f.readStringUntil('\n'); f.close();
    int a = linha.indexOf('|'), b = linha.indexOf('|', a + 1);
    if (a < 1 || b < 0) { LittleFS.remove(ARQ_SESSAO); return; }
    String sessao = linha.substring(0, a), uid = linha.substring(b + 1); uid.trim();
    uint64_t operador = strtoull(linha.c_str() + a + 1, NULL, 10);
    if (registrarOperacao("fim", "reinicio", uid.c_str(), operador, sessao.c_str()))
      LittleFS.remove(ARQ_SESSAO);
  }

  void iniciar() {
    uuid(bootId);
    mutexArquivos = xSemaphoreCreateMutex();
    armazenamentoOK = mutexArquivos && LittleFS.begin(true);
    if (!armazenamentoOK) { Serial.println("ERRO: LittleFS indisponivel; RFID nao sera confirmado"); return; }
    if (!LittleFS.exists(ARQ_FILA) && LittleFS.exists(ARQ_FILA_BAK))
      LittleFS.rename(ARQ_FILA_BAK, ARQ_FILA);
    carregarConfig();
    recuperarInterrupcao();
    Serial.printf("Frota: equipamento=%llu config=%llu operadores=%u\n",
      (unsigned long long)equipamentoId, (unsigned long long)configVersao, (unsigned)totalOperadores);
  }
#else
  enum ResultadoCracha { NEGADO, INICIO, FIM, TROCA, FALHA_PERSISTENCIA };
  inline void iniciar() {}
  inline ResultadoCracha processarCracha(const char*) { return NEGADO; }
#endif
}
