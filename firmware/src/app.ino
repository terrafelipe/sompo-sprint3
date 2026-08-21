// SOMPO Seguros - Sprint 3 - Firmware de demonstracao (furto/incendio)
//
// Escopo: apenas furto/roubo e incendio.
//
// Modelo de operacao:
//   - Potenciometro (34) = CHAVE DE IGNICAO. Girado p/ cima = maquina ligada.
//     Maquina desligada = sistema em VIGILANCIA (monitorando furto).
//   - Cracha (27) = autorizacao. Precisa ser passado ANTES de dar a partida.
//   - Dar partida sem cracha valido = ALERTA de roubo.
//   - Com a maquina desligada: deslocamento (HC-SR04) = reboque; vibracao (MPU) =
//     adulteracao/tentativa de partida forcada.
//   - HC-SR04 mede o quanto a maquina SAIU da posicao onde estacionou: a
//     referencia acompanha a distancia enquanto a maquina esta ligada e congela
//     quando ela desliga. Comparar leituras consecutivas nao funciona (o carreto
//     do reboque e lento demais para gerar salto entre duas amostras).
//   - MPU-6050: a linha de base do repouso e CALIBRADA no boot, nao assumida.
//     Bancada/simulador ficam em ~0 g e a maquina real em ~1 g; assumir 1 g fixo
//     fazia o sensor parado marcar 1 g de vibracao e alarmar sozinho.
//   - Capo (25) / tanque (26) abertos = AVISO brando (pode ser manutencao);
//     so viram alerta forte em horario suspeito.
//   - Horario real vem por NTP (Wi-Fi); 22h-5h agrava a suspeita.
//   - Incendio: DHT22 (temp do escape) + PIR (chama), sempre monitorado.
//
// Bibliotecas: EasyUltrasonic (HC-SR04), Adafruit DHT (DHT22),
// electroniccats/MPU6050 (acelerometro).
//
// Serial separado por contexto: [SISTEMA] [STATUS] [FURTO] [AVISO] [INCENDIO].
// O JSON completo so aparece com TELEMETRIA_SERIAL 1 (util para o relatorio).
//
// Rede: Wi-Fi, servidor web local de status e envio ao Supabase.
//
// O envio roda numa TAREFA SEPARADA (nucleo 0), nunca dentro do loop: um POST
// HTTPS custa de centenas de ms a segundos, e travar o ciclo de 100 ms com o
// alarme tocando seria pior que perder o pacote. O loop so enfileira.
//
// Evento e telemetria tem valor diferente e por isso tem fila diferente:
//   - eventos: fila FIFO de 16. Nao se perde por falta de rede - e a trilha de
//     evidencia do sinistro. Sem cobertura, espera; falhou o POST, volta para a
//     frente da fila.
//   - telemetria: caixa de UM slot, sobrescrita. Amostra periodica velha nao
//     tem valor; melhor mandar a leitura de agora do que a fila de 10 min atras.
//
// Credenciais ficam em segredos.h (fora do Git). A chave gravada aqui e a
// PUBLISHABLE, e quem a limita a INSERT sao as politicas em sql/politicas_rls.sql.
//
// Convencoes: portugues sem acento, loop nao-bloqueante por millis(), falha de
// sensor mantem o ultimo valor valido, histerese no alarme.


#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <time.h>
#include <EasyUltrasonic.h>
#include <DHT.h>
#include <MPU6050.h>

#include "segredos.h"

// ---------------------------------------------------------------------------
// Configuracao
// ---------------------------------------------------------------------------

#define MODO_SIMULACAO    1   // 1 = mapeia DHT p/ faixa de escape real
#define TELEMETRIA_SERIAL 0   // 1 = imprime tambem o JSON completo (p/ relatorio)
#define VALIDAR_CERTIFICADO 0 // 1 = valida o cert TLS do Supabase (producao); 0 = setInsecure (Wokwi/demo)
#define DISPOSITIVO_ID "SOMPO-ESP32"

// Pinos (conforme diagram.json)
#define PIN_POT           34   // chave de ignicao (ADC1, funciona com Wi-Fi)
#define PIN_TRIG          23
#define PIN_ECHO          22
#define PIN_DHT           32
#define PIN_PIR           35
#define PIN_CAPO          25
#define PIN_TANQUE        26
#define PIN_CRACHA        27
#define PIN_LED_VERMELHO  21   // alarme
#define PIN_LED_AMARELO   19   // atencao / aviso
#define PIN_LED_VERDE     18   // normal
#define PIN_BUZZER        17
#define PIN_MPU_SDA       13   // I2C nao-padrao (ver diagram.json)
#define PIN_MPU_SCL       14

// Limiares
#define LIMIAR_IGNICAO        2048   // pot acima disto = maquina ligada (0..4095)
#define TEMP_ESCAPE_ATENCAO   450.0
#define TEMP_ESCAPE_CRITICO   550.0
#define LIMIAR_VIBRACAO       0.15   // g de desvio sobre a linha de base do repouso
#define AMOSTRAS_BASE_VIBRACAO 10    // leituras (1 s) que calibram a linha de base
#define AMOSTRAS_VIBRACAO     3      // leituras seguidas acima do limiar p/ confirmar
#define ALFA_BASE_VIBRACAO    0.02   // adaptacao da linha de base (~5 s a 100 ms)
#define LIMIAR_DESLOCAMENTO   8.0    // cm de afastamento da posicao estacionada
#define MAX_FALHAS_DISTANCIA  5      // leituras invalidas seguidas antes de desistir
#define TRAVA_EVENTO          5000   // ms anti-spam dos eventos continuos
#define AQUECIMENTO_PIR       60000  // ms de warmup do PIR antes de confiar
#define TEMP_MODULO_MIN       -40.0  // faixa de operacao do MPU-6050 (datasheet)
#define TEMP_MODULO_MAX       85.0

// Horario (NTP) - Brasil UTC-3, sem horario de verao
#define GMT_OFFSET_SEC        (-3 * 3600)
#define DAYLIGHT_OFFSET_SEC   0
#define NTP_SERVER            "pool.ntp.org"
#define HORA_SUSPEITA_INICIO  22     // >= 22h
#define HORA_SUSPEITA_FIM     5      // < 5h

// Intervalos do loop
#define INTERVALO_LEITURA     100    // ms - ciclo principal de sensores/atuadores
#define INTERVALO_DHT         2000   // ms - DHT22 so aceita 1 leitura a cada 2 s
#define INTERVALO_TELEMETRIA  10000  // ms - amostra periodica gravada no Supabase
#define INTERVALO_SAUDE_MPU   5000   // ms - reconferencia de presenca do MPU no I2C

// Supabase (URL e chave publishable ficam em segredos.h)
#define TAM_PAYLOAD           384    // bytes - maior linha JSON que montamos
#define FILA_EVENTOS          16     // eventos guardados enquanto falta rede
#define TIMEOUT_HTTP          8000   // ms - POST inteiro, incluindo handshake TLS
#define MAX_TENTATIVAS_ENVIO  3      // reenvios antes de descartar um evento
#define PAUSA_ENVIO           250    // ms entre POSTs (nao afoga a fila)
#define PAUSA_SEM_REDE        2000   // ms de espera quando o Wi-Fi esta fora

// CA raiz que autentica o Supabase: Google Trust Services "GTS Root R4"
// (self-signed, valido ate 2036). A cadeia real e supabase.co <- GTS WE1 <-
// GTS Root R4; embutir o root basta para o mbedTLS validar toda a cadeia.
// So entra no binario quando VALIDAR_CERTIFICADO=1 - no Wokwi/demo (=0) e omitido.
#if VALIDAR_CERTIFICADO
const char SUPABASE_ROOT_CA[] PROGMEM = R"CERT(
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
#endif

// ---------------------------------------------------------------------------
// Objetos das bibliotecas
// ---------------------------------------------------------------------------

EasyUltrasonic ultrasonic;           // HC-SR04
DHT dht(PIN_DHT, DHT22);             // DHT22
MPU6050 mpu;                         // acelerometro (endereco padrao 0x68)
WebServer server(80);

// ---------------------------------------------------------------------------
// Estado (falha de leitura mantem o ultimo valor valido - nunca zera)
// ---------------------------------------------------------------------------

float tempEscape   = 300.0;          // C (escape em marcha lenta)
float umidadeAr    = 50.0;           // %
float tempModulo   = 25.0;           // C - die do MPU (diagnostico, nao ambiente)
float vibracao     = 0.0;            // g de desvio sobre a linha de base
float distanciaCm  = 100.0;          // cm
float distanciaReferencia = 100.0;   // cm - posicao em que a maquina estacionou
float deltaCm      = 0.0;            // cm de afastamento da referencia

bool maquinaLigada   = false;        // ignicao (potenciometro)
bool emMovimento     = false;
bool chamaDetectada  = false;
bool capoAberto      = false;
bool tanqueAberto    = false;
bool operadorAutorizado = false;     // cracha valido lido nesta sessao
bool suspeitoAgora   = false;        // horario dentro da faixa suspeita

bool temReferencia = false;          // referencia de distancia ja capturada
int  falhasDistancia = 0;            // leituras invalidas seguidas do HC-SR04

bool mpuOk = false;
bool vibracaoConfirmada = false;     // limiar batido em N leituras seguidas
float baseVibracao = 0.0;            // g em repouso (calibrado, nao assumido)
float somaBaseVibracao = 0.0;        // acumulador da calibracao inicial
int amostrasBaseVibracao = 0;        // leituras ja usadas na calibracao
int amostrasVibracao = 0;            // leituras seguidas acima do limiar

// Nivel de risco / alarme
int severidadeAtual = 0;             // maior severidade das condicoes ativas
const char* nivelRisco = "SEGURO";
const char* nivelAnterior = "SEGURO";
bool alarmeLigado = false;
bool buzzerLigado = false;

// Bordas dos eventos
bool crachaAnterior       = false;
bool maquinaAnterior      = false;
bool capoAbertoAnterior   = false;
bool tanqueAbertoAnterior = false;
bool chamaAnterior        = false;
bool escapeCriticoAnterior = false;
bool escapeAtencaoAnterior = false;
unsigned long ultimoFurtoMovimento = 0;
unsigned long ultimaAdulteracao = 0;

// Wi-Fi
#define INTERVALO_TENTATIVA_WIFI 10000   // ms entre tentativas de reconexao
unsigned long ultimaTentativaWiFi = 0;
bool wifiEstavaConectado = false;
bool servidorIniciado = false;

// Envio ao Supabase (ver as duas filas explicadas no cabecalho)
struct Payload {
  char tabela[16];
  char json[TAM_PAYLOAD];
};

QueueHandle_t filaEventos = NULL;      // FIFO 16 - trilha de evidencia, nao se perde
QueueHandle_t caixaTelemetria = NULL;  // 1 slot sobrescrito - so a leitura de agora

volatile int envioTotalOk = 0;         // contadores para a pagina de status
volatile int envioTotalFalha = 0;
volatile int eventosDescartados = 0;   // fila cheia ou tentativas esgotadas
char envioUltimoErro[64] = "";

// Timers do loop
unsigned long bootMillis = 0;
unsigned long ultimaLeitura = 0;
unsigned long ultimaDht = 0;
unsigned long ultimaTelemetria = 0;
unsigned long ultimaSaudeMpu = 0;

// ---------------------------------------------------------------------------
// Hora (NTP)
// ---------------------------------------------------------------------------

// Preenche txt com "HH:MM" e (se pedido) a hora em horaOut.
// Retorna false enquanto a hora ainda nao sincronizou pelo NTP.
bool horaAtual(int* horaOut, char* txt, size_t n) {
  struct tm t;
  if (!getLocalTime(&t, 5)) {          // 5 ms: nao bloqueia o loop
    snprintf(txt, n, "--:--");
    return false;
  }
  if (horaOut) *horaOut = t.tm_hour;
  snprintf(txt, n, "%02d:%02d", t.tm_hour, t.tm_min);
  return true;
}

bool horarioSuspeito() {
  int h;
  char tmp[8];
  if (!horaAtual(&h, tmp, sizeof(tmp))) return false;   // sem hora: nao agrava
  return (h >= HORA_SUSPEITA_INICIO || h < HORA_SUSPEITA_FIM);
}

// Carimbo ISO-8601 com fuso, para o campo criado_em.
//
// Precisa ir junto no payload porque um evento pode ficar minutos na fila
// esperando rede: se deixassemos o banco preencher com now(), a hora gravada
// seria a da RECONEXAO, nao a do arrombamento. Numa trilha de evidencia isso e
// a diferenca entre um registro util e um registro errado.
//
// Retorna false enquanto o NTP nao sincronizou - ai o campo e omitido e o
// default do banco assume, que e o melhor disponivel.
bool carimboISO(char* txt, size_t n) {
  struct tm t;
  if (!getLocalTime(&t, 5)) {
    return false;
  }
  int offsetH = GMT_OFFSET_SEC / 3600;
  snprintf(txt, n, "%04d-%02d-%02dT%02d:%02d:%02d%+03d:00",
           t.tm_year + 1900, t.tm_mon + 1, t.tm_mday,
           t.tm_hour, t.tm_min, t.tm_sec, offsetH);
  return true;
}

// ---------------------------------------------------------------------------
// Wi-Fi
// ---------------------------------------------------------------------------

void iniciarWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID_CFG, WIFI_PASSWORD_CFG);
  ultimaTentativaWiFi = millis();
}

bool estaConectado() {
  return WiFi.status() == WL_CONNECTED;
}

void manterWiFi() {
  bool conectado = estaConectado();

  if (conectado && !wifiEstavaConectado) {
    Serial.print("[SISTEMA] Wi-Fi conectado, IP ");
    Serial.println(WiFi.localIP());
    configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);   // sincroniza a hora
  }
  if (!conectado && wifiEstavaConectado) {
    Serial.println("[SISTEMA] Wi-Fi caiu, reconectando...");
  }
  wifiEstavaConectado = conectado;

  if (conectado) {
    return;
  }
  if (millis() - ultimaTentativaWiFi >= INTERVALO_TENTATIVA_WIFI) {
    ultimaTentativaWiFi = millis();
    WiFi.begin(WIFI_SSID_CFG, WIFI_PASSWORD_CFG);
  }
}

// ---------------------------------------------------------------------------
// Leitura dos sensores
// ---------------------------------------------------------------------------

// Potenciometro como chave de ignicao.
void lerIgnicao() {
  maquinaLigada = analogRead(PIN_POT) > LIMIAR_IGNICAO;
}

// HC-SR04 (EasyUltrasonic): mede o AFASTAMENTO da posicao estacionada.
//
// A referencia acompanha a distancia enquanto a maquina esta ligada (andar e
// normal) e congela no instante em que ela desliga - dali em diante ela e a
// posicao de estacionamento. Sair dessa posicao com a maquina desligada e
// reboque. Comparar duas leituras consecutivas (100 ms) nao serve: reboque e
// lento e nunca gera salto entre amostras vizinhas.
void lerDistancia() {
  float leitura = ultrasonic.getDistanceCM();

  // Fora da faixa util do HC-SR04 => leitura invalida.
  if (leitura <= 0.0 || leitura > 400.0) {
    falhasDistancia++;
    if (falhasDistancia >= MAX_FALHAS_DISTANCIA) {
      emMovimento = false;           // sem leitura confiavel nao se acusa reboque
    }
    return;                          // mantem a ultima distancia valida
  }
  falhasDistancia = 0;
  distanciaCm = leitura;

  // Boot ou maquina ligada: a referencia segue a posicao atual.
  if (!temReferencia || maquinaLigada) {
    distanciaReferencia = leitura;
    temReferencia = true;
    deltaCm = 0.0;
    emMovimento = false;
    return;
  }

  deltaCm = fabs(leitura - distanciaReferencia);
  emMovimento = deltaCm >= LIMIAR_DESLOCAMENTO;
}

// MPU-6050 (electroniccats): vibracao = desvio da magnitude sobre a LINHA DE
// BASE do repouso, calibrada nas primeiras leituras.
//
// Nao da para assumir 1 g de gravidade: na bancada/simulador o sensor em
// repouso entrega ~0 g, e o desvio fixo de 1 g mantinha o alarme de adulteracao
// preso para sempre. Calibrando, tanto ~0 g quanto ~1 g viram "repouso = zero".
void lerVibracao() {
  if (!mpuOk) {
    return;                          // sem sensor: mantem ultimo valor valido
  }
  int16_t ax, ay, az;
  mpu.getAcceleration(&ax, &ay, &az);

  // Temperatura interna do MPU: e o DIE do proprio chip, nao o ar em volta - le
  // alguns graus acima do ambiente por auto-aquecimento, e dentro da caixa ainda
  // mais. Existe para compensar deriva do giroscopio, nao para medir incendio.
  // Vale como diagnostico do modulo (a caixa esta cozinhando?) e nada alem disso.
  float tm = mpu.getTemperature() / 340.0 + 36.53;   // formula do datasheet
  if (tm > TEMP_MODULO_MIN && tm < TEMP_MODULO_MAX) {
    tempModulo = tm;                 // fora da faixa = leitura invalida
  }

  // 16384 LSB/g na escala padrao +-2g
  float gx = ax / 16384.0;
  float gy = ay / 16384.0;
  float gz = az / 16384.0;
  float magnitude = sqrt(gx * gx + gy * gy + gz * gz);

  // Calibracao: media das primeiras leituras define o repouso.
  if (amostrasBaseVibracao < AMOSTRAS_BASE_VIBRACAO) {
    somaBaseVibracao += magnitude;
    amostrasBaseVibracao++;
    baseVibracao = somaBaseVibracao / amostrasBaseVibracao;
    vibracao = 0.0;
    amostrasVibracao = 0;
    vibracaoConfirmada = false;
    return;
  }

  vibracao = fabs(magnitude - baseVibracao);

  // A base persegue lentamente a magnitude (filtro passa-alta): inclinacao nova
  // ou offset do sensor sao absorvidos, trepidacao (transitoria) nao e.
  baseVibracao += ALFA_BASE_VIBRACAO * (magnitude - baseVibracao);

  // Exige N leituras seguidas: um pico isolado de ruido nao vira furto.
  if (vibracao >= LIMIAR_VIBRACAO) {
    if (amostrasVibracao < AMOSTRAS_VIBRACAO) amostrasVibracao++;
  } else {
    amostrasVibracao = 0;
  }
  vibracaoConfirmada = (amostrasVibracao >= AMOSTRAS_VIBRACAO);
}

// PIR como sensor de chama. Ignora o periodo de aquecimento.
void lerChama() {
  if (millis() - bootMillis < AQUECIMENTO_PIR) {
    chamaDetectada = false;
    return;
  }
  chamaDetectada = (digitalRead(PIN_PIR) == HIGH);
}

// Botoes com INPUT_PULLUP: pressionado = LOW.
void lerBotoes() {
  capoAberto = (digitalRead(PIN_CAPO) == LOW);
  tanqueAberto = (digitalRead(PIN_TANQUE) == LOW);

  // Cracha: confirma na borda (uma vez por leitura), como uma maquininha de cartao.
  bool crachaLido = (digitalRead(PIN_CRACHA) == LOW);
  if (crachaLido && !crachaAnterior) {
    operadorAutorizado = true;
    // Pessoa autorizada no local: reancora a posicao de estacionamento, senao um
    // deslocamento legitimo (manobra, carga) ficaria acusando reboque para sempre.
    temReferencia = false;
    emMovimento = false;
    Serial.println("[SISTEMA] cracha OK - operador autorizado");
  }
  crachaAnterior = crachaLido;
}

// DHT22 (Adafruit): temperatura do escape + umidade. Timer proprio de 2 s.
void lerDht() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();

  if (isnan(t) || isnan(h)) {
    return;                          // falha: mantem ultimo valor valido
  }
  umidadeAr = h;
#if MODO_SIMULACAO
  // Mapeia 20-60 C do DHT para 300-600 C (faixa real de escape),
  // fazendo os limiares de 450/550 valerem na demo.
  tempEscape = 300.0 + (t - 20.0) * 7.5;
#else
  tempEscape = t;
#endif
}

// ---------------------------------------------------------------------------
// Decisao de risco e atuadores
// ---------------------------------------------------------------------------

// Maior severidade entre as condicoes de perigo ATIVAS agora.
void calcularNivelRisco() {
  int sev = 0;

  // Incendio (sempre monitorado)
  if (chamaDetectada)                     sev = max(sev, 5);
  if (tempEscape >= TEMP_ESCAPE_CRITICO)  sev = max(sev, 4);
  if (tempEscape >= TEMP_ESCAPE_ATENCAO)  sev = max(sev, 2);

  if (!maquinaLigada) {
    // Vigilancia: maquina parada
    if (emMovimento)                      sev = max(sev, 4);                 // reboque
    if (vibracaoConfirmada)               sev = max(sev, 4);                 // adulteracao
    if (capoAberto)                       sev = max(sev, suspeitoAgora ? 4 : 2);
    if (tanqueAberto)                     sev = max(sev, suspeitoAgora ? 4 : 3);
    // Vigilancia cega: sem acelerometro nao ha como flagrar adulteracao.
    if (!mpuOk)                           sev = max(sev, suspeitoAgora ? 4 : 2);
  } else {
    // Maquina ligada sem autorizacao = roubo em andamento
    if (!operadorAutorizado)              sev = max(sev, suspeitoAgora ? 4 : 3);
  }

  severidadeAtual = sev;
  if (sev >= 4)      nivelRisco = "CRITICO";
  else if (sev >= 2) nivelRisco = "ATENCAO";
  else               nivelRisco = "SEGURO";
}

// Histerese: liga no CRITICO, so desliga no SEGURO. ATENCAO mantem o estado.
void atualizarAlarme() {
  if (severidadeAtual >= 4)      alarmeLigado = true;
  else if (severidadeAtual == 0) alarmeLigado = false;
}

// LEDs seguem o estado; buzzer acompanha o alarme (troca so na borda).
void atualizarAlertas() {
  digitalWrite(PIN_LED_VERMELHO, alarmeLigado ? HIGH : LOW);
  digitalWrite(PIN_LED_AMARELO, (!alarmeLigado && severidadeAtual >= 2) ? HIGH : LOW);
  digitalWrite(PIN_LED_VERDE,   (!alarmeLigado && severidadeAtual < 2) ? HIGH : LOW);

  if (alarmeLigado && !buzzerLigado) {
    tone(PIN_BUZZER, 2000);
    buzzerLigado = true;
  } else if (!alarmeLigado && buzzerLigado) {
    noTone(PIN_BUZZER);
    buzzerLigado = false;
  }
}

// ---------------------------------------------------------------------------
// Envio ao Supabase (tarefa propria - o loop nunca fala com a rede)
// ---------------------------------------------------------------------------

// Um POST. Devolve true so com 2xx.
bool postarSupabase(const char* tabela, const char* json) {
  WiFiClientSecure cliente;

  // Validacao do certificado do servidor, controlada por VALIDAR_CERTIFICADO:
  //   1 = autentica o Supabase pelo CA raiz embutido (producao, fecha a porta ao
  //       man-in-the-middle);
  //   0 = setInsecure: criptografa mas NAO valida - aceitavel no Wokwi/demo (que
  //       nao traz o bundle de CAs), NAO em producao.
#if VALIDAR_CERTIFICADO
  cliente.setCACert(SUPABASE_ROOT_CA);
#else
  cliente.setInsecure();
#endif
  cliente.setTimeout(TIMEOUT_HTTP / 1000);

  char url[160];
  snprintf(url, sizeof(url), "%s/rest/v1/%s", SUPABASE_URL_CFG, tabela);

  HTTPClient http;
  if (!http.begin(cliente, url)) {
    snprintf(envioUltimoErro, sizeof(envioUltimoErro), "begin() falhou em %s", tabela);
    return false;
  }
  http.setTimeout(TIMEOUT_HTTP);
  http.addHeader("apikey", SUPABASE_CHAVE_CFG);
  http.addHeader("Authorization", "Bearer " SUPABASE_CHAVE_CFG);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Prefer", "return=minimal");   // sem eco do registro: economiza RAM

  int codigo = http.POST((uint8_t*)json, strlen(json));
  bool ok = (codigo >= 200 && codigo < 300);

  if (!ok) {
    // O corpo do erro do PostgREST diz exatamente o que esta errado (coluna
    // inexistente, RLS negando, JSON invalido). Sem isso a depuracao e cega.
    String corpo = (codigo > 0) ? http.getString() : String(http.errorToString(codigo));
    snprintf(envioUltimoErro, sizeof(envioUltimoErro), "%s HTTP %d: %.40s",
             tabela, codigo, corpo.c_str());
    Serial.print("[REDE] falha no envio - ");
    Serial.println(envioUltimoErro);
  }
  http.end();
  return ok;
}

// Consumidora das duas filas. Roda no nucleo 0 (o Wi-Fi tambem vive la); o
// loop() do Arduino fica sozinho no nucleo 1 e nunca espera pela rede.
void tarefaEnvio(void* param) {
  Payload p;

  for (;;) {
    if (WiFi.status() != WL_CONNECTED) {
      vTaskDelay(pdMS_TO_TICKS(PAUSA_SEM_REDE));
      continue;                        // sem rede as filas so esperam
    }

    // Evento tem prioridade sobre telemetria: e o que nao pode se perder.
    if (xQueueReceive(filaEventos, &p, 0) == pdTRUE) {
      bool ok = false;
      for (int tentativa = 1; tentativa <= MAX_TENTATIVAS_ENVIO && !ok; tentativa++) {
        ok = postarSupabase(p.tabela, p.json);
        if (!ok) vTaskDelay(pdMS_TO_TICKS(500 * tentativa));   // recuo progressivo
      }
      if (ok) {
        envioTotalOk++;
      } else {
        envioTotalFalha++;
        // Esgotou as tentativas. Volta para a FRENTE da fila para preservar a
        // ordem cronologica - a nao ser que a fila esteja cheia, e ai o evento
        // se perde de verdade e isso precisa aparecer na pagina de status.
        if (xQueueSendToFront(filaEventos, &p, 0) != pdTRUE) {
          eventosDescartados++;
          Serial.println("[REDE] fila cheia - EVENTO PERDIDO");
        }
        vTaskDelay(pdMS_TO_TICKS(PAUSA_SEM_REDE));
      }
    } else if (xQueueReceive(caixaTelemetria, &p, 0) == pdTRUE) {
      // Telemetria nao volta para a fila: a proxima amostra ja e melhor que esta.
      if (postarSupabase(p.tabela, p.json)) envioTotalOk++;
      else                                  envioTotalFalha++;
    } else {
      vTaskDelay(pdMS_TO_TICKS(PAUSA_ENVIO));   // nada a fazer
      continue;
    }

    vTaskDelay(pdMS_TO_TICKS(PAUSA_ENVIO));
  }
}

// ---------------------------------------------------------------------------
// Eventos (mensagem legivel por contexto + linha para o Supabase)
// ---------------------------------------------------------------------------

void dispararEvento(const char* contexto, const char* mensagem,
                    const char* tipo, int severidade, const char* detalhes) {
  Serial.print("[");
  Serial.print(contexto);
  Serial.print("] ");
  Serial.println(mensagem);

  // criado_em so entra se o NTP ja sincronizou; sem ele, o default do banco vale.
  char quando[40];
  char campoData[64] = "";
  if (carimboISO(quando, sizeof(quando))) {
    snprintf(campoData, sizeof(campoData), "\"criado_em\":\"%s\",", quando);
  }

  Payload p;
  strncpy(p.tabela, "eventos", sizeof(p.tabela) - 1);
  p.tabela[sizeof(p.tabela) - 1] = '\0';
  snprintf(p.json, sizeof(p.json),
    "{\"dispositivo_id\":\"%s\",%s\"tipo\":\"%s\",\"severidade\":%d,"
    "\"temp_escape\":%.1f,\"detalhes\":%s}",
    DISPOSITIVO_ID, campoData, tipo, severidade, tempEscape, detalhes);

#if TELEMETRIA_SERIAL
  Serial.print("          ");
  Serial.println(p.json);
#endif

  if (xQueueSend(filaEventos, &p, 0) != pdTRUE) {
    eventosDescartados++;
    Serial.println("[REDE] fila de eventos cheia - EVENTO PERDIDO");
  }
}

// Com a maquina parada o MPU e o unico sensor de adulteracao. Se ele sumir do
// barramento, a deteccao de vibracao morre CALADA - arrancar o fio do sensor
// seria a forma mais barata de burlar o sistema. Entao perder o sensor e, ele
// mesmo, um evento de furto, e nao apenas uma linha de log.
void verificarSaudeMpu() {
  bool presente = mpu.testConnection();

  if (!presente && mpuOk) {
    mpuOk = false;
    vibracao = 0.0;                  // sem sensor nao se afirma nada sobre vibracao
    amostrasVibracao = 0;
    vibracaoConfirmada = false;
    dispararEvento("FURTO", "MPU6050 sumiu do barramento - sensor cortado ou solto",
                   "sensor_falha", 3, "{\"sensor\":\"mpu6050\"}");
  }
  if (presente && !mpuOk) {
    mpuOk = true;
    somaBaseVibracao = 0.0;          // sensor voltou: linha de base do zero
    amostrasBaseVibracao = 0;
    Serial.println("[SISTEMA] MPU6050 reconectado - recalibrando linha de base");
  }
}

void verificarEventos() {
  unsigned long agora = millis();
  char hora[8];
  horaAtual(NULL, hora, sizeof(hora));

  // --- Partida: borda de ligar a maquina ---
  if (maquinaLigada && !maquinaAnterior) {
    if (!operadorAutorizado) {
      char msg[96];
      snprintf(msg, sizeof(msg), "partida sem cracha as %s - possivel roubo", hora);
      char det[112];
      snprintf(det, sizeof(det), "{\"hora\":\"%s\",\"horario_suspeito\":%s}",
               hora, suspeitoAgora ? "true" : "false");
      dispararEvento("FURTO", msg, "operador_nao_autorizado", suspeitoAgora ? 4 : 3, det);
    } else {
      Serial.print("[SISTEMA] partida autorizada as ");
      Serial.println(hora);
    }
  }
  if (!maquinaLigada && maquinaAnterior) {
    operadorAutorizado = false;      // desligou: exige novo cracha na proxima partida
    Serial.println("[SISTEMA] maquina desligada - em vigilancia");
  }
  maquinaAnterior = maquinaLigada;

  // --- Vigilancia: apenas com a maquina desligada ---
  if (!maquinaLigada) {
    // furto_movimento (reboque): continuo, protegido pela trava de 5 s.
    if (emMovimento && agora - ultimoFurtoMovimento >= TRAVA_EVENTO) {
      ultimoFurtoMovimento = agora;
      char msg[112];
      snprintf(msg, sizeof(msg),
        "maquina saiu %.0f cm da posicao estacionada - possivel reboque", deltaCm);
      char det[112];
      snprintf(det, sizeof(det),
               "{\"distancia_cm\":%.1f,\"referencia_cm\":%.1f,\"delta_cm\":%.1f}",
               distanciaCm, distanciaReferencia, deltaCm);
      dispararEvento("FURTO", msg, "furto_movimento", 4, det);
    }

    // furto_adulteracao (vibracao com a maquina parada): continuo, trava de 5 s.
    if (vibracaoConfirmada && agora - ultimaAdulteracao >= TRAVA_EVENTO) {
      ultimaAdulteracao = agora;
      char det[48];
      snprintf(det, sizeof(det), "{\"vibracao\":%.2f}", vibracao);
      dispararEvento("FURTO", "vibracao com a maquina desligada - possivel adulteracao",
                     "furto_adulteracao", 4, det);
    }

    // furto_capo (borda): aviso brando, ou alerta forte em horario suspeito.
    if (capoAberto && !capoAbertoAnterior) {
      if (suspeitoAgora) {
        char msg[80];
        snprintf(msg, sizeof(msg), "capo aberto na madrugada as %s", hora);
        dispararEvento("FURTO", msg, "furto_capo", 4, "{\"capo_aberto\":true}");
      } else {
        dispararEvento("AVISO", "capo aberto com a maquina desligada (pode ser manutencao)",
                       "furto_capo", 2, "{\"capo_aberto\":true}");
      }
    }

    // furto_tanque (borda): aviso brando, ou alerta forte em horario suspeito.
    if (tanqueAberto && !tanqueAbertoAnterior) {
      if (suspeitoAgora) {
        char msg[80];
        snprintf(msg, sizeof(msg), "tanque aberto na madrugada as %s", hora);
        dispararEvento("FURTO", msg, "furto_tanque", 4, "{\"tanque_aberto\":true}");
      } else {
        dispararEvento("AVISO", "tanque aberto com a maquina desligada (pode ser manutencao)",
                       "furto_tanque", 3, "{\"tanque_aberto\":true}");
      }
    }
  }
  capoAbertoAnterior = capoAberto;
  tanqueAbertoAnterior = tanqueAberto;

  // --- Incendio: sempre monitorado ---
  // temp_escape ja viaja como coluna propria em todo evento (ver dispararEvento),
  // entao 'detalhes' aqui so carrega o que a coluna nao diz.
  if (chamaDetectada && !chamaAnterior) {
    dispararEvento("INCENDIO", "chama detectada!", "chama_detectada", 5,
                   "{\"chama\":true}");
  }
  chamaAnterior = chamaDetectada;

  bool critico = tempEscape >= TEMP_ESCAPE_CRITICO;
  if (critico && !escapeCriticoAnterior) {
    char msg[48];
    snprintf(msg, sizeof(msg), "escape critico: %.0f C", tempEscape);
    dispararEvento("INCENDIO", msg, "escape_critico", 4,
                   "{\"limiar\":\"critico\"}");
  }
  escapeCriticoAnterior = critico;

  // So avisa de atencao quando NAO passou direto para critico: um unico salto
  // de temperatura nao deve gerar dois eventos de gravidades diferentes.
  bool atencao = tempEscape >= TEMP_ESCAPE_ATENCAO;
  if (atencao && !escapeAtencaoAnterior && !critico) {
    char msg[48];
    snprintf(msg, sizeof(msg), "escape em atencao: %.0f C", tempEscape);
    dispararEvento("INCENDIO", msg, "escape_atencao", 2,
                   "{\"limiar\":\"atencao\"}");
  }
  escapeAtencaoAnterior = atencao;
}

// ---------------------------------------------------------------------------
// Status e telemetria
// ---------------------------------------------------------------------------

// Imprime so quando o nivel de risco muda (evita poluir o console).
void imprimirStatus() {
  if (strcmp(nivelRisco, nivelAnterior) != 0) {
    Serial.print("[STATUS] ");
    Serial.print(nivelAnterior);
    Serial.print(" -> ");
    Serial.println(nivelRisco);
    nivelAnterior = nivelRisco;
  }
}

// Monta e enfileira uma linha da tabela 'telemetria'.
//
// As colunas seguem exatamente o schema do Supabase - temp_modulo e mpuOk NAO
// entram aqui porque nao existem como coluna, e o PostgREST rejeitaria a linha
// inteira (PGRST204). Os dois vivem na pagina de status, e a perda do MPU ja
// chega ao banco pelo canal certo: o evento 'sensor_falha'.
void enviarTelemetria() {
  char quando[40];
  char campoData[64] = "";
  if (carimboISO(quando, sizeof(quando))) {
    snprintf(campoData, sizeof(campoData), "\"criado_em\":\"%s\",", quando);
  }

  Payload p;
  strncpy(p.tabela, "telemetria", sizeof(p.tabela) - 1);
  p.tabela[sizeof(p.tabela) - 1] = '\0';
  snprintf(p.json, sizeof(p.json),
    "{\"dispositivo_id\":\"%s\",%s\"temp_escape\":%.1f,\"umidade_ar\":%.1f,"
    "\"chama_detectada\":%s,\"vibracao\":%.2f,\"motor_ligado\":%s,"
    "\"distancia_cm\":%.1f,\"em_movimento\":%s,\"nivel_risco\":\"%s\"}",
    DISPOSITIVO_ID, campoData, tempEscape, umidadeAr,
    chamaDetectada ? "true" : "false", vibracao, maquinaLigada ? "true" : "false",
    distanciaCm, emMovimento ? "true" : "false", nivelRisco);

#if TELEMETRIA_SERIAL
  Serial.print("[TELEMETRIA] ");
  Serial.println(p.json);
#endif

  // Sobrescreve: se a anterior ainda nao saiu, a leitura de agora vale mais.
  xQueueOverwrite(caixaTelemetria, &p);
}

// Pagina de status com auto-refresh.
void tratarRaiz() {
  char hora[8];
  horaAtual(NULL, hora, sizeof(hora));

  int naFila = filaEventos ? uxQueueMessagesWaiting(filaEventos) : 0;

  char html[1900];
  snprintf(html, sizeof(html),
    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
    "<meta http-equiv='refresh' content='5'>"
    "<title>SOMPO ESP32</title></head><body>"
    "<h1>SOMPO - Monitor furto/incendio</h1>"
    "<p>Hora: %s | Maquina: <b>%s</b> | Operador: <b>%s</b></p>"
    "<p>Nivel de risco: <b>%s</b> | Alarme: <b>%s</b></p>"
    "<ul>"
    "<li>Temp escape: %.1f C</li>"
    "<li>Umidade ar: %.1f %%</li>"
    "<li>Chama: %s</li>"
    "<li>Vibracao: %.2f g (base %.2f g, limiar %.2f g)</li>"
    "<li>MPU-6050: <b>%s</b> | temp do modulo: %.1f C</li>"
    "<li>Distancia: %.0f cm | estacionou em %.0f cm</li>"
    "<li>Reboque: %s (saiu %.0f cm, limiar %.0f cm)</li>"
    "<li>Capo aberto: %s | Tanque aberto: %s</li>"
    "</ul>"
    "<h2>Supabase</h2>"
    "<ul>"
    "<li>Enviados: %d | falhas: %d</li>"
    "<li>Eventos na fila: <b>%d</b> de %d | perdidos: <b>%d</b></li>"
    "<li>Ultimo erro: %s</li>"
    "</ul></body></html>",
    hora,
    maquinaLigada ? "LIGADA" : "desligada (vigilancia)",
    operadorAutorizado ? "autorizado" : "sem cracha",
    nivelRisco, alarmeLigado ? "ATIVO" : "inativo",
    tempEscape, umidadeAr,
    chamaDetectada ? "sim" : "nao",
    vibracao, baseVibracao, (float)LIMIAR_VIBRACAO,
    mpuOk ? "ok" : "SEM RESPOSTA", tempModulo,
    distanciaCm, distanciaReferencia,
    emMovimento ? "SIM" : "nao", deltaCm, (float)LIMIAR_DESLOCAMENTO,
    capoAberto ? "sim" : "nao", tanqueAberto ? "sim" : "nao",
    envioTotalOk, envioTotalFalha,
    naFila, FILA_EVENTOS, eventosDescartados,
    envioUltimoErro[0] ? envioUltimoErro : "nenhum");

  server.send(200, "text/html", html);
}

// ---------------------------------------------------------------------------
// setup / loop
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  bootMillis = millis();

  // A tarefa de envio roda no nucleo 0 e faz um handshake TLS a cada POST - cripto
  // pesada que segura o nucleo 0 por alguns segundos e nao cede para a tarefa IDLE0,
  // disparando o Task Watchdog (task_wdt: IDLE0) e abortando. A tarefa de envio e de
  // baixa prioridade e ja tem timeout proprio (TIMEOUT_HTTP), entao tiramos a IDLE0
  // do watchdog: um envio demorado deixa de derrubar o dispositivo.
  disableCore0WDT();

  // I2C em pinos nao-padrao para o MPU-6050 (ver diagram.json).
  Wire.begin(PIN_MPU_SDA, PIN_MPU_SCL);
  mpu.initialize();
  mpuOk = mpu.testConnection();

  dht.begin();
  ultrasonic.attach(PIN_TRIG, PIN_ECHO);

  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_CAPO, INPUT_PULLUP);
  pinMode(PIN_TANQUE, INPUT_PULLUP);
  pinMode(PIN_CRACHA, INPUT_PULLUP);
  pinMode(PIN_LED_VERMELHO, OUTPUT);
  pinMode(PIN_LED_AMARELO, OUTPUT);
  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  // Le a ignicao ja no boot para nao gerar uma "partida" falsa.
  lerIgnicao();
  maquinaAnterior = maquinaLigada;

  Serial.println("[SISTEMA] SOMPO iniciado");
  Serial.println(mpuOk ? "[SISTEMA] MPU6050 ok" : "[SISTEMA] MPU6050 nao encontrado!");
  Serial.println(maquinaLigada ? "[SISTEMA] maquina ligada"
                               : "[SISTEMA] maquina desligada - em vigilancia");

  // Filas antes do Wi-Fi: um evento pode nascer antes da rede subir e precisa
  // ter onde esperar.
  filaEventos = xQueueCreate(FILA_EVENTOS, sizeof(Payload));
  caixaTelemetria = xQueueCreate(1, sizeof(Payload));

  if (!filaEventos || !caixaTelemetria) {
    Serial.println("[SISTEMA] sem RAM para as filas - envio desativado");
  } else {
    // Nucleo 0, junto do Wi-Fi. 8 KB de pilha: o handshake TLS e faminto.
    // Prioridade 1 = abaixo do loop(), entao o ciclo de sensores sempre ganha.
    xTaskCreatePinnedToCore(tarefaEnvio, "envio", 8192, NULL, 1, NULL, 0);
    Serial.println("[SISTEMA] tarefa de envio ao Supabase ativa");
  }

  iniciarWiFi();
}

void loop() {
  manterWiFi();

  if (estaConectado() && !servidorIniciado) {
    server.on("/", tratarRaiz);
    server.begin();
    servidorIniciado = true;
    Serial.println("[SISTEMA] servidor web ativo");
  }
  if (servidorIniciado) {
    server.handleClient();
  }

  unsigned long agora = millis();

  // DHT22: leitura propria a cada 2 s.
  if (agora - ultimaDht >= INTERVALO_DHT) {
    ultimaDht = agora;
    lerDht();
  }

  // Presenca do MPU no barramento: perder o sensor e evento, nao silencio.
  if (agora - ultimaSaudeMpu >= INTERVALO_SAUDE_MPU) {
    ultimaSaudeMpu = agora;
    verificarSaudeMpu();
  }

  // Ciclo principal a cada 100 ms.
  if (agora - ultimaLeitura >= INTERVALO_LEITURA) {
    ultimaLeitura = agora;
    suspeitoAgora = horarioSuspeito();
    lerIgnicao();
    lerDistancia();
    lerVibracao();
    lerChama();
    lerBotoes();
    calcularNivelRisco();
    atualizarAlarme();
    atualizarAlertas();
    verificarEventos();
    imprimirStatus();
  }

  // Telemetria periodica: a cada 10s, MESMO em vigilancia (maquina desligada), para
  // o painel receber uma linha nova continuamente. O estado da ignicao viaja no
  // proprio campo motor_ligado, entao a leitura parada tambem tem valor.
  if (agora - ultimaTelemetria >= INTERVALO_TELEMETRIA) {
    ultimaTelemetria = agora;
    enviarTelemetria();
  }
}
