/*
 * Projeto Sompo Seguros - Leitura de sensores (hardware final)
 * FIAP - Tecnologia em Inteligencia Artificial
 * Placa: ESP32 DevKit V1 (30 pinos) - selecionar "ESP32 Dev Module" na IDE
 * Monitor Serial: 115200 baud
 *
 * ---------------------------------------------------------------------------
 * TESTE INCREMENTAL - leia antes de mexer
 * ---------------------------------------------------------------------------
 * O bring-up e feito UM SENSOR POR VEZ. Cada sensor tem uma flag USAR_<X>
 * (1 = ligado, 0 = desligado) que protege QUATRO pontos do codigo:
 *   1) o #include da biblioteca
 *   2) o objeto global
 *   3) a inicializacao no setup()
 *   4) a chamada no loop() e a propria funcao lerX()
 * Com a flag em 0 nada daquele sensor e compilado e nenhum pino dele e tocado,
 * entao o Monitor Serial nao enche de leitura de pino solto e o build nunca
 * quebra por biblioteca ausente.
 *
 * Ordem de bring-up (definida pelo professor):
 *   PASSO 1 - MPU-6050   (I2C)   <- etapa atual
 *   PASSO 2 - AHT10      (I2C)
 *   PASSO 3 - Buzzer
 *   depois  - RC522, MAX6675, KY-026, reed capo, potenciometro
 *   por ultimo - USAR_WIFI (envio ao Supabase), so com os sensores validados
 *
 * ---------------------------------------------------------------------------
 * Sensores e ligacao (mapa de pinos = fonte da verdade)
 * ---------------------------------------------------------------------------
 * - MPU-6050 (GY-521)         -> I2C   SDA=21 SCL=22, AD0 no GND (endereco 0x68)
 * - AHT10 (temp/umid amb.)    -> I2C   SDA=21 SCL=22 (endereco 0x38)
 * - RFID RC522                -> SPI   SCK=18 MISO=19 MOSI=23, SS=5, RST=27
 * - Termopar tipo K + MAX6675 -> SPI   SCK=18 SO=19, CS=15 (nao usa MOSI)
 * - Reed switch capo          -> Digital 32
 * - Reed switch tanque        -> Digital 33
 * - Sensor de chama KY-026    -> Digital 25
 * - Potenciometro (simula ignicao) -> Analogico 34
 * - Buzzer                    -> Digital 26 (tone)
 * - GPS NEO-6M                -> UART Serial2, TX->16, RX->17 (cruzado)
 *
 * Notas de fiacao que ja custaram tempo:
 * - AD0 do MPU-6050 vai no GND. Sem isso o endereco I2C oscila e a leitura
 *   falha de forma intermitente.
 * - Barramento compartilhado NAO e erro: MPU+AHT dividem o I2C; RC522+MAX6675
 *   dividem o SPI, cada um com seu CS proprio (5 e 15).
 * - RC522 e 3.3V. Ligar no 5V queima o modulo.
 * - Reed switches e KY-026 aqui sao modulos ativos com comparador (A0/G/+/D0):
 *   usamos so o DO, e a polaridade/sensibilidade dependem do trimmer da placa.
 * - MAX6675: leitura estranha -> inverter as garras do termopar no bloco verde.
 * - O potenciometro esta no GPIO 34 (ADC1) de proposito: o ADC2 do ESP32 para
 *   de funcionar quando o Wi-Fi liga.
 *
 * Logica de alerta (demo): o potenciometro simula o sinal de ignicao que, no
 * produto final, viria do proprio veiculo. Se o "motor" estiver desligado E o
 * MPU-6050 detectar vibracao fora do normal, dispara alerta (indicio de veiculo
 * sendo mexido enquanto deveria estar parado).
 *
 * ---------------------------------------------------------------------------
 * Envio ao Supabase (USAR_WIFI) - a API Flask le de la
 * ---------------------------------------------------------------------------
 * Cadeia: sensores -> ESP32 -> Wi-Fi -> Supabase -> API Flask -> painel.
 *
 * O envio roda numa TAREFA SEPARADA (nucleo 0), nunca dentro do loop(): um POST
 * HTTPS custa de centenas de ms a segundos, e travar o ciclo de sensores com o
 * alarme tocando seria pior que perder o pacote. O loop() so enfileira.
 *
 * Evento e telemetria tem valor diferente e por isso tem fila diferente:
 *   - eventos: fila FIFO de 16. Nao se perde por falta de rede - e a trilha de
 *     evidencia do sinistro. Falhou o POST, volta para a FRENTE da fila.
 *   - telemetria: caixa de UM slot, sobrescrita. Amostra periodica velha nao
 *     tem valor; melhor mandar a leitura de agora.
 *
 * Contrato de dados (nao mudar de um lado so):
 *   - tabela/colunas: firmware/sql/preparar_supabase.sql
 *   - tipos de evento pontuados: api/scores.py (EIXO_POR_TIPO)
 *   - dispositivo_id TEM de ser "SOMPO-ESP32": e o default de todas as rotas
 *     da API (api/app.py). Outro id grava no banco e a API nao acha.
 *
 * Campo cujo sensor esta desligado e OMITIDO do JSON (vira NULL na coluna).
 * Mandar 0 seria uma medicao falsa e contaminaria as medias da view
 * resumo_diario.
 *
 * Credenciais ficam em segredos.h, ao lado deste arquivo (a Arduino IDE compila
 * todos os arquivos da pasta do sketch). Esta fora do Git. A chave gravada aqui
 * e a PUBLISHABLE - quem a limita a INSERT sao as politicas de RLS.
 *
 * Bibliotecas (Ferramentas > Gerenciar Bibliotecas):
 * - Adafruit MPU6050 2.2.9 (+ Adafruit Unified Sensor + Adafruit BusIO)
 * - Adafruit AHTX0 2.0.6 (serve para AHT10 e AHT20, o codigo nao muda)
 * - TinyGPSPlus 1.0.3 (Mikal Hart, NAO a "TinyGPSPlus-ESP32")
 * - MFRC522 1.4.12 (miguelbalboa/rfid)
 * - MAX6675 0.3.4 (RobTillaart) - API diferente da Adafruit:
 *     construtor MAX6675(cs, miso, clock), exige begin(),
 *     leitura = read() (STATUS_OK == 0) seguido de getCelsius().
 *   Nao trocar por <max6675.h> da Adafruit sem ajustar essas tres coisas.
 * (WiFi, HTTPClient e Wire/SPI sao nativas do core ESP32.)
 */

// ---------- Teste incremental: ligue um sensor por vez ----------
// Ordem: MPU -> AHT -> BUZZER -> RFID/TERMOPAR/CHAMA/REED/POT -> WIFI
#define USAR_MPU          1   // PASSO 1 - em teste agora
#define USAR_AHT          0   // PASSO 2
#define USAR_BUZZER       0   // PASSO 3
#define USAR_RFID         0
#define USAR_TERMOPAR     0
#define USAR_CHAMA        0
#define USAR_REED_CAPO    0
#define USAR_POT          0
#define USAR_GPS          0   // fora da demo: Sprint Review online, sem sinal indoor
#define USAR_REED_TANQUE  0   // fora da demo: so um reed fisico por vez
#define USAR_WIFI         0   // ULTIMO PASSO: envio ao Supabase (exige segredos.h)

#define DIAG_I2C          1   // scanner I2C no setup (ajuda nos passos 1 e 2)
#define DIAG_TELEMETRIA   0   // 1 = imprime o JSON da telemetria no Serial.
                              //     Funciona com USAR_WIFI 0 - da para conferir o
                              //     payload antes de existir rede.

#include <Wire.h>
#include <stdarg.h>   // vsnprintf da montagem do JSON

#if USAR_RFID || USAR_TERMOPAR
  #include <SPI.h>
#endif
#if USAR_MPU
  #include <Adafruit_MPU6050.h>
  #include <Adafruit_Sensor.h>
#endif
#if USAR_AHT
  #include <Adafruit_AHTX0.h>
  #include <Adafruit_Sensor.h>
#endif
#if USAR_GPS
  #include <TinyGPSPlus.h>
#endif
#if USAR_RFID
  #include <MFRC522.h>
#endif
#if USAR_TERMOPAR
  #include <MAX6675.h>
#endif
#if USAR_WIFI
  #include <WiFi.h>
  #include <WiFiClientSecure.h>
  #include <HTTPClient.h>
  #include <time.h>
  #include "segredos.h"
#endif

// ---------- Pinos ----------
// Ficam sempre definidos (mesmo com a flag em 0): sao o mapa de pinos do projeto.

// I2C (padrao ESP32) - MPU-6050 e AHT10 no mesmo barramento (enderecos diferentes)
#define I2C_SDA 21
#define I2C_SCL 22

// GPS - Serial2 (hardware UART, nao usar SoftwareSerial no ESP32)
#define GPS_RX 16   // ESP32 RX <- GPS TX
#define GPS_TX 17   // ESP32 TX -> GPS RX
#define GPS_BAUD 9600

// SPI compartilhado (VSPI padrao) - RC522 e MAX6675 no mesmo barramento
#define SPI_SCK  18
#define SPI_MISO 19
#define SPI_MOSI 23

// RC522 - pino CS/SS proprio
#define RFID_SS  5
#define RFID_RST 27

// MAX6675 (termopar) - pino CS proprio (nao usa MOSI)
#define TERMOPAR_CS 15

// Reed switches (modulo ativo: A0/G/+/D0, mesmo formato do KY-026 - usa so o DO)
#define REED_CAPO   32
#define REED_TANQUE 33

// Sensor de chama KY-026 (saida digital)
#define CHAMA_PIN 25

// Potenciometro - simula motor ligado/desligado (ADC1: sobrevive ao Wi-Fi)
#define POT_PIN 34

// Buzzer
#define BUZZER_PIN 26

// ---------- Parametros ajustaveis na bancada ----------
#define INTERVALO_CICLO_MS      100    // amostragem dos sensores rapidos
#define INTERVALO_SERIAL_MS     2000   // retrato periodico no Monitor Serial
#define INTERVALO_LENTO_MS      2000   // AHT10 e MAX6675 (conversao lenta)
#define INTERVALO_TELEMETRIA_MS 30000  // amostra gravada no Supabase
#define INTERVALO_SAUDE_MPU_MS  5000   // reconferencia de presenca do MPU no I2C

#define LIMIAR_POT_MOTOR_DESLIGADO 2000  // leitura do pot (0-4095) abaixo disso = "motor desligado"
#define LIMIAR_VIBRACAO 2.0              // desvio em m/s2 do repouso = "vibracao"
#define AMOSTRAS_BASELINE 50             // amostras para calibrar o repouso do MPU
#define AMOSTRAS_VIBRACAO 3              // leituras seguidas acima do limiar p/ confirmar
#define TEMP_ESCAPE_ATENCAO 450.0        // C - termopar tipo K
#define TEMP_ESCAPE_CRITICO 550.0        // C
#define TRAVA_EVENTO_MS 5000             // anti-spam dos eventos continuos

#define GRAVIDADE 9.80665                // m/s2 por g - converte a vibracao para g

// ---------- Identidade e rede ----------
#define DISPOSITIVO_ID "SOMPO-ESP32"     // TEM de bater com o default da API

#if USAR_WIFI
#define TAM_PAYLOAD              384   // bytes - maior linha JSON que montamos
#define FILA_EVENTOS             16    // eventos guardados enquanto falta rede
#define TIMEOUT_HTTP             8000  // ms - POST inteiro, incluindo handshake TLS
#define MAX_TENTATIVAS_ENVIO     3     // reenvios antes de devolver a fila
#define PAUSA_ENVIO              250   // ms entre POSTs (nao afoga a fila)
#define PAUSA_SEM_REDE           2000  // ms de espera quando o Wi-Fi esta fora
#define INTERVALO_TENTATIVA_WIFI 10000 // ms entre tentativas de reconexao

// Horario (NTP) - Brasil UTC-3, sem horario de verao
#define GMT_OFFSET_SEC      (-3 * 3600)
#define DAYLIGHT_OFFSET_SEC 0
#define NTP_SERVER          "pool.ntp.org"
#elif DIAG_TELEMETRIA
#define TAM_PAYLOAD 384
#endif

// ---------- Objetos ----------
#if USAR_MPU
Adafruit_MPU6050 mpu;
bool mpuOk = false;
#endif

#if USAR_AHT
Adafruit_AHTX0 aht;
bool ahtOk = false;
#endif

#if USAR_GPS
TinyGPSPlus gps;
HardwareSerial gpsSerial(2);
#endif

#if USAR_RFID
MFRC522 rfid(RFID_SS, RFID_RST);

// UIDs dos crachas autorizados (4 bytes). Preencha depois que o passo do RFID
// imprimir o UID da sua tag no Serial: "UID: A1 B2 C3 D4" -> {0xA1,0xB2,0xC3,0xD4}.
// Enquanto estiver com o valor de exemplo, TODA partida vira evento de furto.
const byte UIDS_AUTORIZADOS[][4] = {
  { 0xDE, 0xAD, 0xBE, 0xEF },   // TROCAR pelo UID real
};
#endif

#if USAR_TERMOPAR
// Lib RobTillaart: construtor software SPI e (select, miso, clock) - CS primeiro
MAX6675 termopar(TERMOPAR_CS, SPI_MISO, SPI_SCK);
bool termoparOk = false;
#endif

// ---------- Estado (falha de leitura mantem o ultimo valor valido) ----------
// Ficam fora dos #if porque a telemetria e o calculo de risco leem todos eles;
// com o sensor desligado o valor permanece neutro e o campo e omitido do JSON.
float baselineAccel = GRAVIDADE;   // magnitude media com a placa parada (calibrada)
float ultimaMagnitudeAccel = GRAVIDADE;
float vibracaoG = 0.0;             // desvio sobre o repouso, em g (unidade da coluna)
int   amostrasVibracao = 0;        // leituras seguidas acima do limiar
bool  vibracaoConfirmada = false;

float tempEscape = 25.0;           // C - termopar
float umidadeAr  = 50.0;           // %
bool  chamaDetectada = false;
bool  motorLigado = false;
bool  capoAberto = false;
bool  tanqueAberto = false;
bool  operadorAutorizado = false;  // cracha valido lido nesta sessao (ate desligar)

int severidadeAtual = 0;
const char* nivelRisco = "SEGURO";

// Bordas dos eventos (evento dispara na transicao, nao a cada ciclo)
bool motorAnterior = false;
bool capoAnterior = false;
bool tanqueAnterior = false;
bool chamaAnterior = false;
bool escapeAtencaoAnterior = false;
bool escapeCriticoAnterior = false;
unsigned long ultimaAdulteracao = 0;

// Agendamento do loop (nao-bloqueante: nada de delay() aqui)
unsigned long ultimoCiclo = 0;
unsigned long ultimoLento = 0;
unsigned long ultimoSerial = 0;
unsigned long ultimaSaudeMpu = 0;
unsigned long ultimaTelemetria = 0;
#if USAR_WIFI
unsigned long ultimaTentativaWiFi = 0;
bool wifiEstavaConectado = false;

// Filas do envio (ver o cabecalho: semanticas diferentes de proposito)
struct Payload {
  char tabela[12];
  char json[TAM_PAYLOAD];
};
QueueHandle_t filaEventos = NULL;
QueueHandle_t caixaTelemetria = NULL;
unsigned long envioTotalOk = 0;
unsigned long envioTotalFalha = 0;
unsigned long eventosDescartados = 0;

// CA raiz que autentica o Supabase: Google Trust Services "GTS Root R4"
// (self-signed, valido ate 2036). A cadeia real e supabase.co <- GTS WE1 <-
// GTS Root R4; embutir o root basta para o mbedTLS validar toda a cadeia.
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

// ---------- Declaracoes antecipadas ----------
// A Arduino IDE gera prototipos sozinha, mas o gerador tropeça em funcoes
// dentro de #if - e aqui quase todas estao. Declarar a mao evita "was not
// declared in this scope" quando uma flag muda.

void beep(unsigned int freq, unsigned long dur);
void lerSensoresRapidos();
void lerSensoresLentos();
void calcularNivelRisco();
void verificarEventos();
void imprimirEstado();
void dispararEvento(const char* contexto, const char* mensagem,
                    const char* tipo, int severidade, const char* detalhes);

#if USAR_MPU
void calibrarBaselineMPU();
void lerMPU();
void verificarSaudeMpu();
#endif
#if USAR_AHT
void lerAHT();
#endif
#if USAR_GPS
void lerGPS();
#endif
#if USAR_RFID
bool uidAutorizado();
void lerRFID();
#endif
#if USAR_TERMOPAR
void lerTermopar();
#endif
#if USAR_REED_CAPO || USAR_REED_TANQUE
void lerReedSwitches();
#endif
#if USAR_CHAMA
void lerChama();
#endif
#if USAR_POT
void lerMotor();
#endif
#if USAR_WIFI || DIAG_TELEMETRIA
void anexar(char* buf, size_t cap, size_t &n, const char* fmt, ...);
void montarTelemetria(char* json, size_t cap);
void enviarTelemetria();
#endif
#if USAR_WIFI
void iniciarWiFi();
void manterWiFi();
bool carimboISO(char* txt, size_t n);
bool postarSupabase(const char* tabela, const char* json);
void tarefaEnvio(void* param);
#endif

// ---------- Helpers ----------

// Bipe que vira no-op enquanto o buzzer nao estiver montado (USAR_BUZZER 0),
// assim chama e alerta de furto chamam beep() sem espalhar #if pela logica.
void beep(unsigned int freq, unsigned long dur) {
#if USAR_BUZZER
  tone(BUZZER_PIN, freq, dur);
#else
  (void)freq;
  (void)dur;
#endif
}

#if DIAG_I2C
// Varre o barramento e lista quem respondeu. Esperado: 0x68 (MPU, AD0 no GND)
// e, a partir do passo 2, 0x38 (AHT10). Barramento vazio = fiacao/alimentacao,
// nao e problema de biblioteca.
void escanearI2C() {
  Serial.println("Scanner I2C: procurando dispositivos...");
  byte encontrados = 0;
  for (byte addr = 0x08; addr < 0x78; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  I2C: dispositivo encontrado em 0x%02X\n", addr);
      encontrados++;
    }
  }
  if (encontrados == 0) {
    Serial.println("  I2C: NENHUM dispositivo. Confira 3.3V, GND, SDA=21, SCL=22 e AD0 no GND.");
  }
}
#endif

#if USAR_MPU
// Media da magnitude do vetor de aceleracao com a placa parada. Usar o valor
// medido (em vez de 9.8 fixo) tira o offset do sensor da conta do limiar.
void calibrarBaselineMPU() {
  float soma = 0;
  for (int i = 0; i < AMOSTRAS_BASELINE; i++) {
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);
    soma += sqrt(a.acceleration.x * a.acceleration.x +
                 a.acceleration.y * a.acceleration.y +
                 a.acceleration.z * a.acceleration.z);
    delay(10);
  }
  baselineAccel = soma / AMOSTRAS_BASELINE;
  ultimaMagnitudeAccel = baselineAccel;
  Serial.printf("MPU-6050 baseline de repouso: %.2f m/s2 (limiar de vibracao: %.2f)\n",
                baselineAccel, (float)LIMIAR_VIBRACAO);
}
#endif

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("=== Sistema Sompo - Inicializando sensores ===");

#if USAR_MPU || USAR_AHT || DIAG_I2C
  Wire.begin(I2C_SDA, I2C_SCL);
#endif

#if DIAG_I2C
  escanearI2C();
#endif

  // MPU-6050
#if USAR_MPU
  if (!mpu.begin()) {
    Serial.println("ERRO: MPU-6050 nao encontrado! (AD0 no GND? 0x68 apareceu no scanner?)");
  } else {
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    mpuOk = true;
    Serial.println("MPU-6050 OK - calibrando repouso, nao mexa na placa...");
    calibrarBaselineMPU();
  }
#endif

  // AHT10
#if USAR_AHT
  if (!aht.begin()) {
    Serial.println("ERRO: AHT10 nao encontrado! (0x38 apareceu no scanner?)");
  } else {
    ahtOk = true;
    Serial.println("AHT10 OK");
  }
#endif

  // GPS
#if USAR_GPS
  gpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX, GPS_TX);
  Serial.println("GPS - aguardando fix...");
#endif

  // SPI (compartilhado por RC522 e MAX6675)
#if USAR_RFID || USAR_TERMOPAR
  SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI);
#endif

#if USAR_RFID
  rfid.PCD_Init();
  Serial.println("RC522 OK");
#endif

  // MAX6675 (lib RobTillaart precisa de begin() explicito)
#if USAR_TERMOPAR
  termopar.begin();
  Serial.println("MAX6675 iniciado");
#endif

  // Reed switches (modulo ativo com comparador - DO ja vem "empurrado", sem pullup)
#if USAR_REED_CAPO
  pinMode(REED_CAPO, INPUT);
#endif
#if USAR_REED_TANQUE
  pinMode(REED_TANQUE, INPUT);
#endif

  // Chama
#if USAR_CHAMA
  pinMode(CHAMA_PIN, INPUT);
#endif

  // Buzzer - bipe curto de autoteste, valida o buzzer sozinho (passo 3),
  // sem depender do potenciometro nem do sensor de chama.
#if USAR_BUZZER
  pinMode(BUZZER_PIN, OUTPUT);
  Serial.println("Buzzer - bipe de teste");
  beep(2500, 200);
  delay(300);
#endif

  // Rede: filas antes do Wi-Fi - um evento pode nascer antes da rede subir e
  // precisa ter onde esperar.
#if USAR_WIFI
  filaEventos = xQueueCreate(FILA_EVENTOS, sizeof(Payload));
  caixaTelemetria = xQueueCreate(1, sizeof(Payload));

  if (!filaEventos || !caixaTelemetria) {
    Serial.println("ERRO: sem RAM para as filas - envio desativado");
  } else {
    // Nucleo 0, junto do Wi-Fi. 8 KB de pilha: o handshake TLS e faminto.
    // Prioridade 1 = abaixo do loop(), entao o ciclo de sensores sempre ganha.
    xTaskCreatePinnedToCore(tarefaEnvio, "envio", 8192, NULL, 1, NULL, 0);
    Serial.println("Tarefa de envio ao Supabase ativa");
  }
  iniciarWiFi();
#endif

  Serial.println("=== Setup concluido ===\n");
}

// ---------------------------------------------------------------------------
// Loop - agendamento por millis(), nunca delay()
// ---------------------------------------------------------------------------
// Tres cadencias: os sensores rapidos (e o RFID, que precisa ser pesquisado a
// cada passagem, senao o cartao teria de ficar encostado dois segundos), os
// sensores de conversao lenta, e o retrato no Serial.

void loop() {
#if USAR_WIFI
  manterWiFi();
#endif

  unsigned long agora = millis();

  if (agora - ultimoCiclo >= INTERVALO_CICLO_MS) {
    ultimoCiclo = agora;
    lerSensoresRapidos();
    calcularNivelRisco();
    verificarEventos();
  }

  if (agora - ultimoLento >= INTERVALO_LENTO_MS) {
    ultimoLento = agora;
    lerSensoresLentos();
  }

  if (agora - ultimoSerial >= INTERVALO_SERIAL_MS) {
    ultimoSerial = agora;
    imprimirEstado();
  }

#if USAR_MPU
  if (agora - ultimaSaudeMpu >= INTERVALO_SAUDE_MPU_MS) {
    ultimaSaudeMpu = agora;
    verificarSaudeMpu();
  }
#endif

#if USAR_WIFI || DIAG_TELEMETRIA
  if (agora - ultimaTelemetria >= INTERVALO_TELEMETRIA_MS) {
    ultimaTelemetria = agora;
    enviarTelemetria();
  }
#endif
}

// ---------------------------------------------------------------------------
// Leitura dos sensores (so atualiza o estado - quem imprime e imprimirEstado)
// ---------------------------------------------------------------------------

void lerSensoresRapidos() {
#if USAR_MPU
  lerMPU();
#endif
#if USAR_GPS
  lerGPS();
#endif
#if USAR_RFID
  lerRFID();
#endif
#if USAR_REED_CAPO || USAR_REED_TANQUE
  lerReedSwitches();
#endif
#if USAR_CHAMA
  lerChama();
#endif
#if USAR_POT
  lerMotor();
#endif
}

void lerSensoresLentos() {
#if USAR_AHT
  lerAHT();
#endif
#if USAR_TERMOPAR
  lerTermopar();
#endif
}

#if USAR_MPU
void lerMPU() {
  if (!mpuOk) return;

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  // magnitude total do vetor de aceleracao (parado, fica perto do baseline)
  ultimaMagnitudeAccel = sqrt(a.acceleration.x * a.acceleration.x +
                              a.acceleration.y * a.acceleration.y +
                              a.acceleration.z * a.acceleration.z);

  float desvio = fabs(ultimaMagnitudeAccel - baselineAccel);

  // A coluna 'vibracao' do banco guarda a grandeza em g - o historico foi
  // gravado assim. Sem esta conversao a media do resumo_diario misturaria duas
  // escalas (m/s2 e g) e deixaria de significar coisa alguma.
  vibracaoG = desvio / GRAVIDADE;

  // Uma leitura isolada acima do limiar e ruido; N seguidas e vibracao.
  if (desvio > LIMIAR_VIBRACAO) {
    if (amostrasVibracao < AMOSTRAS_VIBRACAO) amostrasVibracao++;
  } else {
    amostrasVibracao = 0;
  }
  vibracaoConfirmada = (amostrasVibracao >= AMOSTRAS_VIBRACAO);
}

// Com a maquina parada o MPU e o unico sensor de adulteracao. Se ele sumir do
// barramento a deteccao morre CALADA - arrancar o fio seria a forma mais barata
// de burlar o sistema. Perder o sensor e, ele mesmo, um evento de furto.
void verificarSaudeMpu() {
  Wire.beginTransmission(0x68);
  bool presente = (Wire.endTransmission() == 0);

  if (!presente && mpuOk) {
    mpuOk = false;
    vibracaoG = 0.0;              // sem sensor nao se afirma nada sobre vibracao
    amostrasVibracao = 0;
    vibracaoConfirmada = false;
    dispararEvento("FURTO", "MPU-6050 sumiu do barramento - sensor cortado ou solto",
                   "sensor_falha", 3, "{\"sensor\":\"mpu6050\"}");
  }
  if (presente && !mpuOk) {
    mpuOk = true;
    Serial.println("[SISTEMA] MPU-6050 reconectado - recalibrando linha de base");
    calibrarBaselineMPU();
  }
}
#endif

#if USAR_AHT
void lerAHT() {
  if (!ahtOk) return;
  sensors_event_t humidity, temp;
  aht.getEvent(&humidity, &temp);
  umidadeAr = humidity.relative_humidity;
}
#endif

#if USAR_GPS
void lerGPS() {
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }
}
#endif

#if USAR_RFID
bool uidAutorizado() {
  if (rfid.uid.size != 4) return false;   // so comparamos UIDs de 4 bytes
  for (size_t i = 0; i < sizeof(UIDS_AUTORIZADOS) / 4; i++) {
    bool igual = true;
    for (byte b = 0; b < 4; b++) {
      if (rfid.uid.uidByte[b] != UIDS_AUTORIZADOS[i][b]) { igual = false; break; }
    }
    if (igual) return true;
  }
  return false;
}

void lerRFID() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

  Serial.print("RFID detectado - UID:");
  for (byte i = 0; i < rfid.uid.size; i++) {
    Serial.print(rfid.uid.uidByte[i] < 0x10 ? " 0" : " ");
    Serial.print(rfid.uid.uidByte[i], HEX);
  }

  if (uidAutorizado()) {
    operadorAutorizado = true;
    Serial.println("  -> AUTORIZADO");
  } else {
    Serial.println("  -> nao autorizado");
  }
  rfid.PICC_HaltA();
}
#endif

#if USAR_TERMOPAR
void lerTermopar() {
  uint8_t status = termopar.read();
  if (status == STATUS_OK) {
    tempEscape = termopar.getCelsius();   // falha mantem o ultimo valor valido
    termoparOk = true;
  } else {
    termoparOk = false;
  }
}
#endif

#if USAR_REED_CAPO || USAR_REED_TANQUE
void lerReedSwitches() {
#if USAR_REED_CAPO
  capoAberto = digitalRead(REED_CAPO) == HIGH;   // HIGH = contato aberto = capo aberto
#endif
#if USAR_REED_TANQUE
  tanqueAberto = digitalRead(REED_TANQUE) == HIGH;
#endif
}
#endif

#if USAR_CHAMA
void lerChama() {
  chamaDetectada = digitalRead(CHAMA_PIN) == LOW;  // KY-026: LOW = chama detectada
}
#endif

#if USAR_POT
void lerMotor() {
  bool ligadoAgora = analogRead(POT_PIN) >= LIMIAR_POT_MOTOR_DESLIGADO;
  // Desligar encerra a sessao: o cracha tem de ser passado de novo na proxima
  // partida, senao uma autorizacao de ontem valeria para o ladrao de hoje.
  if (!ligadoAgora && motorLigado) operadorAutorizado = false;
  motorLigado = ligadoAgora;
}
#endif

// ---------------------------------------------------------------------------
// Decisao: severidade e nivel de risco (o mesmo que vai na coluna nivel_risco)
// ---------------------------------------------------------------------------

void calcularNivelRisco() {
  int sev = 0;

  // Incendio: monitorado sempre, ligado ou desligado.
  if (chamaDetectada)                        sev = max(sev, 5);
  if (tempEscape >= TEMP_ESCAPE_CRITICO)     sev = max(sev, 4);
  else if (tempEscape >= TEMP_ESCAPE_ATENCAO) sev = max(sev, 2);

  if (!motorLigado) {
    // Parada = vigilancia. Qualquer coisa mexendo na maquina e suspeita.
    if (vibracaoConfirmada) sev = max(sev, 4);
    if (capoAberto)         sev = max(sev, 2);
    if (tanqueAberto)       sev = max(sev, 3);
  } else if (!operadorAutorizado) {
    // Ligada sem cracha valido = roubo em andamento.
    sev = max(sev, 3);
  }

  severidadeAtual = sev;
  if (sev >= 4)      nivelRisco = "CRITICO";
  else if (sev >= 2) nivelRisco = "ATENCAO";
  else               nivelRisco = "SEGURO";
}

// ---------------------------------------------------------------------------
// Eventos - disparam na BORDA, nunca a cada ciclo
// ---------------------------------------------------------------------------
// Os tipos abaixo tem de existir em api/scores.py (EIXO_POR_TIPO/SEVERIDADE_PADRAO),
// senao o evento chega ao banco mas nao pontua no score de risco.

void verificarEventos() {
  unsigned long agora = millis();
  char detalhes[96];

#if USAR_POT
  // Partida: borda de ligar a maquina.
  if (motorLigado && !motorAnterior && !operadorAutorizado) {
    dispararEvento("FURTO", "partida sem cracha autorizado - possivel roubo",
                   "operador_nao_autorizado", 3, "{\"origem\":\"rc522\"}");
  }
  motorAnterior = motorLigado;
#endif

#if USAR_MPU
  // Vibracao com a maquina parada. Substitui o antigo furto_movimento, que
  // dependia do HC-SR04 (fora do hardware atual): aqui nao ha como afirmar
  // deslocamento, so que alguem esta mexendo na maquina.
  if (vibracaoConfirmada && !motorLigado && (agora - ultimaAdulteracao) > TRAVA_EVENTO_MS) {
    ultimaAdulteracao = agora;
    snprintf(detalhes, sizeof(detalhes),
             "{\"vibracao_g\":%.3f,\"limiar_ms2\":%.2f}", vibracaoG, (float)LIMIAR_VIBRACAO);
    dispararEvento("FURTO", "vibracao detectada com a maquina desligada",
                   "furto_adulteracao", 4, detalhes);
    beep(3000, 400);   // 3000 Hz = furto
  }
#endif

#if USAR_REED_CAPO
  if (capoAberto && !capoAnterior && !motorLigado) {
    dispararEvento("AVISO", "capo aberto com a maquina desligada",
                   "furto_capo", 2, "{\"sensor\":\"reed_capo\"}");
  }
  capoAnterior = capoAberto;
#endif

#if USAR_REED_TANQUE
  if (tanqueAberto && !tanqueAnterior && !motorLigado) {
    dispararEvento("AVISO", "tanque aberto com a maquina desligada",
                   "furto_tanque", 3, "{\"sensor\":\"reed_tanque\"}");
  }
  tanqueAnterior = tanqueAberto;
#endif

#if USAR_CHAMA
  if (chamaDetectada && !chamaAnterior) {
    dispararEvento("INCENDIO", "chama detectada", "chama_detectada", 5,
                   "{\"sensor\":\"ky026\"}");
    beep(2000, 500);   // 2000 Hz = chama (frequencia diferente da de furto)
  }
  chamaAnterior = chamaDetectada;
#endif

#if USAR_TERMOPAR
  bool critico = tempEscape >= TEMP_ESCAPE_CRITICO;
  bool atencao = tempEscape >= TEMP_ESCAPE_ATENCAO;

  if (critico && !escapeCriticoAnterior) {
    snprintf(detalhes, sizeof(detalhes), "{\"limiar_c\":%.0f}", (float)TEMP_ESCAPE_CRITICO);
    dispararEvento("INCENDIO", "temperatura do escape critica", "escape_critico", 4, detalhes);
    beep(2000, 500);
  } else if (atencao && !critico && !escapeAtencaoAnterior) {
    snprintf(detalhes, sizeof(detalhes), "{\"limiar_c\":%.0f}", (float)TEMP_ESCAPE_ATENCAO);
    dispararEvento("INCENDIO", "temperatura do escape em atencao", "escape_atencao", 2, detalhes);
  }
  escapeCriticoAnterior = critico;
  escapeAtencaoAnterior = atencao;
#endif

  (void)agora;
  (void)detalhes;
}

// ---------------------------------------------------------------------------
// Retrato periodico no Serial (a cada INTERVALO_SERIAL_MS)
// ---------------------------------------------------------------------------

void imprimirEstado() {
#if USAR_MPU
  if (mpuOk) {
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);
    Serial.printf("Acel (m/s2): X=%.2f Y=%.2f Z=%.2f\n",
                  a.acceleration.x, a.acceleration.y, a.acceleration.z);
    Serial.printf("Giro (rad/s): X=%.2f Y=%.2f Z=%.2f\n", g.gyro.x, g.gyro.y, g.gyro.z);

    // Esta e a linha usada para calibrar LIMIAR_VIBRACAO na bancada: parado o
    // desvio fica perto de 0; batendo na mesa ele sobe.
    float desvio = fabs(ultimaMagnitudeAccel - baselineAccel);
    Serial.printf("|a|=%.2f m/s2 (desvio %.2f, limiar %.2f | %.3f g)%s\n",
                  ultimaMagnitudeAccel, desvio, (float)LIMIAR_VIBRACAO, vibracaoG,
                  vibracaoConfirmada ? "  <-- VIBRACAO" : "");
  } else {
    Serial.println("MPU-6050 indisponivel (falhou no setup ou sumiu do barramento)");
  }
#endif

#if USAR_AHT
  if (ahtOk) {
    sensors_event_t humidity, temp;
    aht.getEvent(&humidity, &temp);
    Serial.printf("Ambiente: %.1f C | %.1f %% UR\n", temp.temperature, humidity.relative_humidity);
  } else {
    Serial.println("AHT10 indisponivel (falhou no setup)");
  }
#endif

#if USAR_GPS
  if (gps.location.isValid()) {
    Serial.printf("GPS: Lat=%.6f Lon=%.6f\n", gps.location.lat(), gps.location.lng());
  } else {
    Serial.println("GPS: sem fix ainda");
  }
#endif

#if USAR_TERMOPAR
  if (termoparOk) Serial.printf("Termopar: %.1f C\n", tempEscape);
  else            Serial.println("Termopar: erro de leitura (confira fiacao/CS)");
#endif

#if USAR_REED_CAPO
  Serial.printf("Capo: %s\n", capoAberto ? "ABERTO" : "fechado");
#endif
#if USAR_REED_TANQUE
  Serial.printf("Tanque: %s\n", tanqueAberto ? "ABERTO" : "fechado");
#endif

#if USAR_CHAMA
  if (chamaDetectada) Serial.println("!!! CHAMA DETECTADA !!!");
#endif

#if USAR_POT
  Serial.printf("Potenciometro (motor): %s | operador: %s\n",
                motorLigado ? "ligado" : "DESLIGADO",
                operadorAutorizado ? "autorizado" : "sem cracha");
#endif

#if USAR_POT && USAR_MPU
  if (!motorLigado && vibracaoConfirmada) {
    Serial.println("!!! ALERTA: vibracao detectada com motor desligado !!!");
  }
#endif

  Serial.printf("Risco: %s (severidade %d)\n", nivelRisco, severidadeAtual);

#if USAR_WIFI
  Serial.printf("Rede: %s | envios ok=%lu falha=%lu | eventos perdidos=%lu\n",
                WiFi.status() == WL_CONNECTED ? "conectado" : "SEM WI-FI",
                envioTotalOk, envioTotalFalha, eventosDescartados);
#endif

  Serial.println("--------------------------------------");
}

// ---------------------------------------------------------------------------
// Montagem do JSON
// ---------------------------------------------------------------------------
#if USAR_WIFI || DIAG_TELEMETRIA

// Acrescenta ao buffer respeitando o limite. snprintf devolve o tamanho que
// TERIA sido escrito; sem este clamp o cursor passaria do fim e o "cap - n"
// seguinte viraria negativo (size_t gigante) - estouro de buffer classico.
void anexar(char* buf, size_t cap, size_t &n, const char* fmt, ...) {
  if (n + 1 >= cap) return;
  va_list args;
  va_start(args, fmt);
  int escrito = vsnprintf(buf + n, cap - n, fmt, args);
  va_end(args);
  if (escrito < 0) return;
  if ((size_t)escrito >= cap - n) n = cap - 1;   // truncou
  else                            n += (size_t)escrito;
}

// Campo cujo sensor esta desligado NAO entra no JSON (a coluna fica NULL).
// Mandar 0 seria inventar uma medicao e estragar as medias do resumo_diario.
void montarTelemetria(char* json, size_t cap) {
  size_t n = 0;
  anexar(json, cap, n, "{\"dispositivo_id\":\"%s\"", DISPOSITIVO_ID);

#if USAR_WIFI
  char quando[40];
  if (carimboISO(quando, sizeof(quando))) {
    anexar(json, cap, n, ",\"criado_em\":\"%s\"", quando);
  }
#endif

#if USAR_TERMOPAR
  if (termoparOk) anexar(json, cap, n, ",\"temp_escape\":%.1f", tempEscape);
#endif
#if USAR_AHT
  if (ahtOk) anexar(json, cap, n, ",\"umidade_ar\":%.1f", umidadeAr);
#endif
#if USAR_CHAMA
  anexar(json, cap, n, ",\"chama_detectada\":%s", chamaDetectada ? "true" : "false");
#endif
#if USAR_MPU
  if (mpuOk) anexar(json, cap, n, ",\"vibracao\":%.3f", vibracaoG);
#endif
#if USAR_POT
  anexar(json, cap, n, ",\"motor_ligado\":%s", motorLigado ? "true" : "false");
#endif
  // distancia_cm e em_movimento nao tem sensor no hardware atual (o HC-SR04
  // saiu do projeto) - ficam NULL de proposito.

  anexar(json, cap, n, ",\"nivel_risco\":\"%s\"}", nivelRisco);
}
#endif

// ---------------------------------------------------------------------------
// Rede: Wi-Fi, NTP e envio ao Supabase (tarefa propria - o loop nunca posta)
// ---------------------------------------------------------------------------
#if USAR_WIFI

void iniciarWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID_CFG, WIFI_PASSWORD_CFG);
  ultimaTentativaWiFi = millis();
  Serial.printf("Wi-Fi: conectando em \"%s\" (precisa ser 2.4 GHz)\n", WIFI_SSID_CFG);
}

void manterWiFi() {
  bool conectado = (WiFi.status() == WL_CONNECTED);

  if (conectado && !wifiEstavaConectado) {
    Serial.print("[SISTEMA] Wi-Fi conectado, IP ");
    Serial.println(WiFi.localIP());
    configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);   // sincroniza a hora
  }
  if (!conectado && wifiEstavaConectado) {
    Serial.println("[SISTEMA] Wi-Fi caiu, reconectando...");
  }
  wifiEstavaConectado = conectado;

  if (conectado) return;
  if (millis() - ultimaTentativaWiFi >= INTERVALO_TENTATIVA_WIFI) {
    ultimaTentativaWiFi = millis();
    WiFi.begin(WIFI_SSID_CFG, WIFI_PASSWORD_CFG);
  }
}

// Retorna false enquanto o NTP nao sincronizou - ai o campo criado_em e omitido
// e o default do banco (now()) assume, que e o melhor disponivel.
bool carimboISO(char* txt, size_t n) {
  struct tm t;
  if (!getLocalTime(&t, 5)) return false;
  int offsetH = GMT_OFFSET_SEC / 3600;
  snprintf(txt, n, "%04d-%02d-%02dT%02d:%02d:%02d%+03d:00",
           t.tm_year + 1900, t.tm_mon + 1, t.tm_mday,
           t.tm_hour, t.tm_min, t.tm_sec, offsetH);
  return true;
}

// Um POST. Devolve true so com 2xx.
bool postarSupabase(const char* tabela, const char* json) {
  WiFiClientSecure cliente;

  // Autentica o Supabase pelo CA raiz embutido. O firmware antigo usava
  // setInsecure() porque o simulador nao trazia o bundle de CAs; com internet
  // real nao ha motivo para aceitar qualquer certificado.
  cliente.setCACert(SUPABASE_ROOT_CA);
  cliente.setTimeout(TIMEOUT_HTTP / 1000);

  char url[160];
  snprintf(url, sizeof(url), "%s/rest/v1/%s", SUPABASE_URL_CFG, tabela);

  HTTPClient http;
  if (!http.begin(cliente, url)) {
    Serial.println("[REDE] http.begin() falhou");
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
    Serial.printf("[REDE] falha no envio - %s HTTP %d: %.80s\n",
                  tabela, codigo, corpo.c_str());
  }
  http.end();
  return ok;
}

// Consumidora das duas filas. Roda no nucleo 0 (o Wi-Fi tambem vive la); o
// loop() fica sozinho no nucleo 1 e nunca espera pela rede.
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
        // se perde de verdade e isso precisa aparecer no Serial.
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

void enviarTelemetria() {
  Payload p;
  strncpy(p.tabela, "telemetria", sizeof(p.tabela) - 1);
  p.tabela[sizeof(p.tabela) - 1] = '\0';
  montarTelemetria(p.json, sizeof(p.json));

#if DIAG_TELEMETRIA
  Serial.print("[TELEMETRIA] ");
  Serial.println(p.json);
#endif

  // Sobrescreve: se a anterior ainda nao saiu, a leitura de agora vale mais.
  if (caixaTelemetria) xQueueOverwrite(caixaTelemetria, &p);
}

#elif DIAG_TELEMETRIA
// Sem Wi-Fi, mas com o diagnostico ligado: monta e imprime o payload, para
// conferir o contrato de dados antes de existir rede.
void enviarTelemetria() {
  char json[TAM_PAYLOAD];
  montarTelemetria(json, sizeof(json));
  Serial.print("[TELEMETRIA] ");
  Serial.println(json);
}
#endif

// ---------------------------------------------------------------------------
// Disparo de evento: mensagem legivel no Serial + linha para o Supabase
// ---------------------------------------------------------------------------

void dispararEvento(const char* contexto, const char* mensagem,
                    const char* tipo, int severidade, const char* detalhes) {
  Serial.printf("[%s] %s\n", contexto, mensagem);

#if USAR_WIFI
  if (!filaEventos) return;

  size_t n = 0;
  Payload p;
  strncpy(p.tabela, "eventos", sizeof(p.tabela) - 1);
  p.tabela[sizeof(p.tabela) - 1] = '\0';

  anexar(p.json, sizeof(p.json), n, "{\"dispositivo_id\":\"%s\"", DISPOSITIVO_ID);

  char quando[40];
  if (carimboISO(quando, sizeof(quando))) {
    anexar(p.json, sizeof(p.json), n, ",\"criado_em\":\"%s\"", quando);
  }
  anexar(p.json, sizeof(p.json), n, ",\"tipo\":\"%s\",\"severidade\":%d", tipo, severidade);
#if USAR_TERMOPAR
  if (termoparOk) anexar(p.json, sizeof(p.json), n, ",\"temp_escape\":%.1f", tempEscape);
#endif
  anexar(p.json, sizeof(p.json), n, ",\"detalhes\":%s}", detalhes);

  if (xQueueSend(filaEventos, &p, 0) != pdTRUE) {
    eventosDescartados++;
    Serial.println("[REDE] fila de eventos cheia - EVENTO PERDIDO");
  }
#else
  (void)tipo;
  (void)severidade;
  (void)detalhes;
#endif
}
