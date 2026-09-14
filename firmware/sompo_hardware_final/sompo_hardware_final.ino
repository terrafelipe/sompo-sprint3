/*
 * Projeto Sompo Seguros - Monitor de furto/incendio (hardware final)
 * FIAP - Tecnologia em Inteligencia Artificial
 * Placa: ESP32 DevKit V1 | FQBN esp32:esp32:esp32 | Serial 115200
 *
 * Cadeia: sensores -> ESP32 -> Wi-Fi -> Supabase -> API Flask -> painel.
 *
 * BRING-UP INCREMENTAL: cada sensor tem uma flag USAR_<X>. Cada sensor tambem
 * e um NAMESPACE com a mesma interface (iniciar/ler/imprimir/eventos/telemetria).
 * Com a flag em 0 o namespace vira um conjunto de no-ops vazios, entao os pontos
 * de chamada nao precisam de #if e o compilador elimina tudo. Ligue um por vez:
 *   MPU -> AHT -> BUZZER -> RFID/TERMOPAR/CHAMA/REED/POT -> WIFI (por ultimo)
 *
 * MAPA DE PINOS (fonte da verdade)
 *   MPU-6050   I2C  SDA=21 SCL=22   AD0 no GND (fixa o endereco em 0x68)
 *   AHT10      I2C  SDA=21 SCL=22   (0x38 - divide o barramento com o MPU)
 *   RC522      SPI  SCK=18 MISO=19 MOSI=23  SS=5  RST=27   SO 3.3V (5V queima)
 *   MAX6675    bit-bang  SO=13 SCK=4  CS=15  (pinos proprios: NAO no SPI do RC522)
 *   Reed capo / tanque  32 / 33     KY-026 chama  25
 *   Potenciometro  34 (ADC1: o ADC2 morre quando o Wi-Fi liga)
 *   Buzzer 26      GPS NEO-6M  TX->16 RX->17 (cruzado)
 * I2C (MPU+AHT) e compartilhado de proposito. O MAX6675 saiu do SPI do RC522:
 * o modulo nao liberava o MISO e travava a leitura do cartao - agora tem pinos so seus.
 *
 * CONTRATO DE DADOS - nao mudar de um lado so:
 *   colunas  -> firmware/sql/preparar_supabase.sql
 *   eventos  -> api/scores.py (EIXO_POR_TIPO)
 *   dispositivo_id TEM de ser "SOMPO-ESP32" (default das rotas em api/app.py)
 * Campo cujo sensor esta desligado e OMITIDO do JSON (coluna NULL). Mandar 0
 * seria inventar medicao e estragar as medias da view resumo_diario.
 *
 * REDE: o POST roda numa tarefa no nucleo 0 - o loop() so enfileira, nunca fala
 * com a rede. Duas filas de proposito: eventos em FIFO de 16 que nao se perde
 * (trilha de evidencia do sinistro) e telemetria em caixa de 1 slot sobrescrita
 * (a amostra de agora vale mais que a velha). Credenciais em segredos.h.
 *
 * BIBLIOTECAS: Adafruit MPU6050 2.2.9 (+Unified Sensor +BusIO), Adafruit AHTX0
 * 2.0.6 (serve AHT10 e AHT20), TinyGPSPlus 1.0.3 (Mikal Hart), MFRC522 1.4.12,
 * MAX6675 0.3.4 do RobTillaart - API DIFERENTE da Adafruit: construtor
 * (cs, miso, clock), exige begin(), leitura read() (STATUS_OK==0) + getCelsius().
 *
 * Detalhes de montagem e teste: docs/COMO_TESTAR.md
 */

// ---------- Ligue um sensor por vez ----------
#define USAR_MPU          1
#define USAR_AHT          1
#define USAR_BUZZER       1
#define USAR_RFID         1
#define USAR_TERMOPAR     1
#define USAR_CHAMA        0   // modulo KY-026 defeituoso (DO travado) - religar com sensor novo
#define USAR_REED_CAPO    1
#define USAR_POT          0   // pot nao montado: motor fica sempre "desligado"
#define USAR_GPS          1   // montado (sem fix indoor: Serial mostra "sem fix")
#define USAR_REED_TANQUE  1
#define USAR_WIFI         1   // ULTIMO PASSO: envio ao Supabase (exige segredos.h)

#define DIAG_I2C          1   // scanner I2C no setup (ajuda nos passos 1 e 2)
#define DIAG_TELEMETRIA   0   // imprime o JSON no Serial; funciona com USAR_WIFI 0

#include <Wire.h>
#include <stdarg.h>
#if USAR_RFID || USAR_TERMOPAR
  #include <SPI.h>
#endif
#if USAR_MPU
  #include <Adafruit_MPU6050.h>
#endif
#if USAR_AHT
  #include <Adafruit_AHTX0.h>
#endif
#if USAR_MPU || USAR_AHT
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
#define I2C_SDA 21
#define I2C_SCL 22
#define GPS_RX  16          // ESP32 RX <- GPS TX
#define GPS_TX  17          // ESP32 TX -> GPS RX
#define GPS_BAUD 9600
#define SPI_SCK  18
#define SPI_MISO 19
#define SPI_MOSI 23
#define RFID_SS  5
#define RFID_RST 27
#define TERMOPAR_CS 15
#define TERMOPAR_SO  13   // MAX6675 e software SPI: SO em pino proprio (nao no 19)
#define TERMOPAR_SCK 4    // ...e SCK proprio - assim nao briga com o MISO do RC522
#define REED_CAPO   32
#define REED_TANQUE 33
#define CHAMA_PIN   25
#define POT_PIN     34
#define BUZZER_PIN  26

// ---------- Parametros ajustaveis na bancada ----------
#define INTERVALO_CICLO_MS      100    // amostragem dos sensores rapidos
#define INTERVALO_SERIAL_MS     2000   // retrato periodico no Monitor Serial
#define INTERVALO_LENTO_MS      2000   // AHT10 e MAX6675 (conversao lenta)
#define INTERVALO_TELEMETRIA_MS 30000  // amostra gravada no Supabase
#define INTERVALO_SAUDE_MPU_MS  5000   // reconferencia do MPU no barramento

#define LIMIAR_POT_MOTOR_DESLIGADO 2000  // pot (0-4095) abaixo disso = desligado
#define LIMIAR_VIBRACAO     2.0          // desvio em m/s2 do repouso = vibracao
#define AMOSTRAS_BASELINE   50           // amostras que calibram o repouso
#define AMOSTRAS_VIBRACAO   3            // leituras seguidas p/ confirmar
#define TEMP_ESCAPE_ATENCAO 450.0        // C - termopar tipo K
#define TEMP_ESCAPE_CRITICO 550.0        // C
#define TRAVA_EVENTO_MS     5000         // anti-spam dos eventos continuos
#define GRAVIDADE           9.80665      // m/s2 por g

#define DISPOSITIVO_ID "SOMPO-ESP32"     // TEM de bater com o default da API
#define TAM_PAYLOAD    384               // maior linha JSON que montamos

#if USAR_WIFI
  #define FILA_EVENTOS             16    // eventos guardados enquanto falta rede
  #define TIMEOUT_HTTP             8000  // ms - POST inteiro, com handshake TLS
  #define MAX_TENTATIVAS_ENVIO     3     // reenvios antes de devolver a fila
  #define PAUSA_ENVIO              250   // ms entre POSTs (nao afoga a fila)
  #define PAUSA_SEM_REDE           2000  // ms de espera sem Wi-Fi
  #define INTERVALO_TENTATIVA_WIFI 10000 // ms entre tentativas de reconexao
  #define GMT_OFFSET_SEC      (-3 * 3600)   // Brasil UTC-3, sem horario de verao
  #define DAYLIGHT_OFFSET_SEC 0
  #define NTP_SERVER          "pool.ntp.org"
#endif

// ---------------------------------------------------------------------------
// Estado compartilhado - falha de leitura mantem o ultimo valor valido.
// Vive fora dos namespaces de sensor porque risco, telemetria e Serial leem
// tudo; com o sensor desligado o valor fica neutro e o campo some do JSON.
// ---------------------------------------------------------------------------
namespace Estado {
  float baselineAccel = GRAVIDADE;    // magnitude media parada (calibrada)
  float magnitudeAccel = GRAVIDADE;
  float vibracaoG = 0.0;              // desvio sobre o repouso, em g
  bool  vibracaoConfirmada = false;

  float tempEscape   = 25.0;          // C - termopar (escape)
  float tempAmbiente = 25.0;          // C - AHT10
  float umidadeAr    = 50.0;          // %
  bool  chamaDetectada = false;
  bool  motorLigado = false;
  bool  capoAberto = false;
  bool  tanqueAberto = false;
  bool  operadorAutorizado = false;   // cracha valido nesta sessao

  int severidade = 0;
  const char* nivelRisco = "SEGURO";
}

// Monta JSON respeitando o limite do buffer. snprintf devolve o tamanho que
// TERIA sido escrito; sem o clamp o cursor passa do fim e o "cap - n" seguinte
// vira negativo (size_t gigante) - estouro de buffer classico.
struct Json {
  char txt[TAM_PAYLOAD];
  size_t n = 0;
  void add(const char* fmt, ...) {
    if (n + 1 >= sizeof(txt)) return;
    va_list a;
    va_start(a, fmt);
    int w = vsnprintf(txt + n, sizeof(txt) - n, fmt, a);
    va_end(a);
    if (w < 0) return;
    n = ((size_t)w >= sizeof(txt) - n) ? sizeof(txt) - 1 : n + (size_t)w;
  }
};

// Duas unicas declaracoes antecipadas: os sensores usam as duas, e elas
// dependem de coisas definidas mais abaixo.
namespace Evento {
  void disparar(const char* ctx, const char* msg, const char* tipo,
                int sev, const char* detalhes);
}

// Bipe que vira no-op sem o buzzer montado - chama e furto chamam sem saber.
namespace Alarme {
#if USAR_BUZZER
  void iniciar() { pinMode(BUZZER_PIN, OUTPUT); }
  void beep(unsigned f, unsigned long d) { tone(BUZZER_PIN, f, d); }
  void autoteste() { Serial.println("Buzzer - bipe de teste"); beep(2500, 200); delay(300); }
#else
  inline void iniciar() {}
  inline void beep(unsigned, unsigned long) {}
  inline void autoteste() {}
#endif
}

// ---------------------------------------------------------------------------
// Sensores - um namespace por sensor, mesma interface em todos
// ---------------------------------------------------------------------------

namespace Mpu {
#if USAR_MPU
  Adafruit_MPU6050 dev;
  bool ok = false;
  int amostrasAcima = 0;
  unsigned long ultimoEvento = 0;

  // Media da magnitude com a placa parada. Usar o valor medido (em vez de 9.8
  // fixo) tira o offset do sensor da conta do limiar.
  void calibrar() {
    float soma = 0;
    for (int i = 0; i < AMOSTRAS_BASELINE; i++) {
      sensors_event_t a, g, t;
      dev.getEvent(&a, &g, &t);
      soma += sqrt(a.acceleration.x * a.acceleration.x +
                   a.acceleration.y * a.acceleration.y +
                   a.acceleration.z * a.acceleration.z);
      delay(10);
    }
    Estado::baselineAccel = soma / AMOSTRAS_BASELINE;
    Estado::magnitudeAccel = Estado::baselineAccel;
    Serial.printf("MPU-6050 baseline de repouso: %.2f m/s2 (limiar: %.2f)\n",
                  Estado::baselineAccel, (float)LIMIAR_VIBRACAO);
  }

  void iniciar() {
    if (!dev.begin()) {
      Serial.println("ERRO: MPU-6050 nao encontrado! (AD0 no GND? 0x68 no scanner?)");
      return;
    }
    dev.setAccelerometerRange(MPU6050_RANGE_8_G);
    dev.setGyroRange(MPU6050_RANGE_500_DEG);
    dev.setFilterBandwidth(MPU6050_BAND_21_HZ);
    ok = true;
    Serial.println("MPU-6050 OK - calibrando repouso, nao mexa na placa...");
    calibrar();
  }

  void ler() {
    if (!ok) return;
    sensors_event_t a, g, t;
    dev.getEvent(&a, &g, &t);
    Estado::magnitudeAccel = sqrt(a.acceleration.x * a.acceleration.x +
                                  a.acceleration.y * a.acceleration.y +
                                  a.acceleration.z * a.acceleration.z);
    float desvio = fabs(Estado::magnitudeAccel - Estado::baselineAccel);

    // A coluna 'vibracao' guarda g - o historico foi gravado assim. Sem esta
    // conversao a media do resumo_diario misturaria m/s2 com g.
    Estado::vibracaoG = desvio / GRAVIDADE;

    // Uma leitura isolada acima do limiar e ruido; N seguidas e vibracao.
    if (desvio > LIMIAR_VIBRACAO) { if (amostrasAcima < AMOSTRAS_VIBRACAO) amostrasAcima++; }
    else                          { amostrasAcima = 0; }
    Estado::vibracaoConfirmada = (amostrasAcima >= AMOSTRAS_VIBRACAO);
  }

  // Parada a maquina, o MPU e o unico sensor de adulteracao. Se ele sumir, a
  // deteccao morre CALADA - arrancar o fio seria a forma mais barata de burlar
  // o sistema. Perder o sensor e, ele mesmo, um evento de furto.
  void saude() {
    Wire.beginTransmission(0x68);
    bool presente = (Wire.endTransmission() == 0);
    if (!presente && ok) {
      ok = false;
      Estado::vibracaoG = 0.0;
      amostrasAcima = 0;
      Estado::vibracaoConfirmada = false;
      Evento::disparar("FURTO", "MPU-6050 sumiu do barramento - sensor cortado ou solto",
                       "sensor_falha", 3, "{\"sensor\":\"mpu6050\"}");
    }
    if (presente && !ok) {
      ok = true;
      Serial.println("[SISTEMA] MPU-6050 reconectado - recalibrando");
      calibrar();
    }
  }

  void eventos() {
    // Vibracao com a maquina parada. Substitui o antigo furto_movimento, que
    // dependia do HC-SR04: aqui nao da para afirmar deslocamento, so que
    // alguem esta mexendo na maquina.
    unsigned long agora = millis();
    if (!Estado::vibracaoConfirmada || Estado::motorLigado) return;
    if (agora - ultimoEvento <= TRAVA_EVENTO_MS) return;
    ultimoEvento = agora;
    char det[96];
    snprintf(det, sizeof(det), "{\"vibracao_g\":%.3f,\"limiar_ms2\":%.2f}",
             Estado::vibracaoG, (float)LIMIAR_VIBRACAO);
    Evento::disparar("FURTO", "vibracao detectada com a maquina desligada",
                     "furto_adulteracao", 4, det);
    Alarme::beep(3000, 400);   // 3000 Hz = furto
  }

  void imprimir() {
    if (!ok) { Serial.println("MPU-6050 indisponivel (falhou no setup ou sumiu)"); return; }
    sensors_event_t a, g, t;
    dev.getEvent(&a, &g, &t);
    Serial.printf("Acel (m/s2): X=%.2f Y=%.2f Z=%.2f\n",
                  a.acceleration.x, a.acceleration.y, a.acceleration.z);
    Serial.printf("Giro (rad/s): X=%.2f Y=%.2f Z=%.2f\n", g.gyro.x, g.gyro.y, g.gyro.z);
    // Linha usada para calibrar LIMIAR_VIBRACAO: parado o desvio fica perto de
    // 0; batendo na mesa ele sobe.
    Serial.printf("|a|=%.2f m/s2 (desvio %.2f, limiar %.2f | %.3f g)%s\n",
                  Estado::magnitudeAccel,
                  fabs(Estado::magnitudeAccel - Estado::baselineAccel),
                  (float)LIMIAR_VIBRACAO, Estado::vibracaoG,
                  Estado::vibracaoConfirmada ? "  <-- VIBRACAO" : "");
  }

  void telemetria(Json &j) { if (ok) j.add(",\"vibracao\":%.3f", Estado::vibracaoG); }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void saude() {}
  inline void eventos() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}

namespace Aht {
#if USAR_AHT
  Adafruit_AHTX0 dev;
  bool ok = false;

  void iniciar() {
    if (!dev.begin()) { Serial.println("ERRO: AHT10 nao encontrado! (0x38 no scanner?)"); return; }
    ok = true;
    Serial.println("AHT10 OK");
  }
  void ler() {
    if (!ok) return;
    sensors_event_t umid, temp;
    dev.getEvent(&umid, &temp);
    Estado::umidadeAr = umid.relative_humidity;
    Estado::tempAmbiente = temp.temperature;
  }
  void imprimir() {
    if (!ok) { Serial.println("AHT10 indisponivel (falhou no setup)"); return; }
    Serial.printf("Ambiente: %.1f C | %.1f %% UR\n", Estado::tempAmbiente, Estado::umidadeAr);
  }
  void telemetria(Json &j) {
    if (!ok) return;
    j.add(",\"temp_ambiente\":%.1f,\"umidade_ar\":%.1f", Estado::tempAmbiente, Estado::umidadeAr);
  }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}

namespace Gps {
#if USAR_GPS
  TinyGPSPlus dev;
  HardwareSerial porta(2);

  void iniciar() {
    porta.begin(GPS_BAUD, SERIAL_8N1, GPS_RX, GPS_TX);
    Serial.println("GPS - aguardando fix...");
  }
  void ler() { while (porta.available() > 0) dev.encode(porta.read()); }
  void imprimir() {
    if (dev.location.isValid())
      Serial.printf("GPS: Lat=%.6f Lon=%.6f\n", dev.location.lat(), dev.location.lng());
    else
      Serial.println("GPS: sem fix ainda");
  }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void imprimir() {}
#endif
}

namespace Rfid {
#if USAR_RFID
  MFRC522 dev(RFID_SS, RFID_RST);

  // UIDs autorizados (4 bytes). Preencha com o que o Serial imprimir ao
  // encostar a sua tag: "UID: A1 B2 C3 D4" -> {0xA1,0xB2,0xC3,0xD4}.
  // Com o valor de exemplo, TODA partida vira evento de furto.
  const byte AUTORIZADOS[][4] = {
    { 0x8B, 0xEE, 0xBC, 0x06 },   // tag do operador (lida na bancada)
  };

  bool autorizado() {
    if (dev.uid.size != 4) return false;   // so comparamos UIDs de 4 bytes
    for (size_t i = 0; i < sizeof(AUTORIZADOS) / 4; i++) {
      bool igual = true;
      for (byte b = 0; b < 4; b++)
        if (dev.uid.uidByte[b] != AUTORIZADOS[i][b]) { igual = false; break; }
      if (igual) return true;
    }
    return false;
  }

  void iniciar() { dev.PCD_Init(); Serial.println("RC522 OK"); }

  void ler() {
    if (!dev.PICC_IsNewCardPresent() || !dev.PICC_ReadCardSerial()) return;
    Serial.print("RFID detectado - UID:");
    for (byte i = 0; i < dev.uid.size; i++) {
      Serial.print(dev.uid.uidByte[i] < 0x10 ? " 0" : " ");
      Serial.print(dev.uid.uidByte[i], HEX);
    }
    if (autorizado()) { Estado::operadorAutorizado = true; Serial.println("  -> AUTORIZADO"); }
    else              { Serial.println("  -> nao autorizado"); }
    dev.PICC_HaltA();
  }
  void telemetria(Json &j) {
    j.add(",\"operador_autorizado\":%s", Estado::operadorAutorizado ? "true" : "false");
  }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void telemetria(Json&) {}
#endif
}

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
    if (dev.read() == STATUS_OK) { Estado::tempEscape = dev.getCelsius(); ok = true; }
    else                         { ok = false; }   // mantem o ultimo valor valido
  }

  void eventos() {
    bool critico = Estado::tempEscape >= TEMP_ESCAPE_CRITICO;
    bool atencao = Estado::tempEscape >= TEMP_ESCAPE_ATENCAO;
    char det[64];
    if (critico && !criticoAnterior) {
      snprintf(det, sizeof(det), "{\"limiar_c\":%.0f}", (float)TEMP_ESCAPE_CRITICO);
      Evento::disparar("INCENDIO", "temperatura do escape critica", "escape_critico", 4, det);
      Alarme::beep(2000, 500);
    } else if (atencao && !critico && !atencaoAnterior) {
      snprintf(det, sizeof(det), "{\"limiar_c\":%.0f}", (float)TEMP_ESCAPE_ATENCAO);
      Evento::disparar("INCENDIO", "temperatura do escape em atencao", "escape_atencao", 2, det);
    }
    criticoAnterior = critico;
    atencaoAnterior = atencao;
  }

  void imprimir() {
    if (ok) Serial.printf("Termopar: %.1f C\n", Estado::tempEscape);
    else    Serial.println("Termopar: erro de leitura (confira fiacao/CS)");
  }
  void telemetria(Json &j) { if (ok) j.add(",\"temp_escape\":%.1f", Estado::tempEscape); }
#else
  const bool ok = false;
  inline void iniciar() {}
  inline void ler() {}
  inline void eventos() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}

// Reed switches: modulos ativos com comparador (A0/G/+/D0), so o DO e usado -
// o DO ja vem "empurrado", entao nao leva pullup.
namespace Reed {
#if USAR_REED_CAPO || USAR_REED_TANQUE
  bool capoAnterior = false, tanqueAnterior = false;

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
#endif
#if USAR_REED_TANQUE
    Estado::tanqueAberto = digitalRead(REED_TANQUE) == HIGH;
#endif
  }
  void eventos() {
#if USAR_REED_CAPO
    if (Estado::capoAberto && !capoAnterior && !Estado::motorLigado)
      Evento::disparar("AVISO", "capo aberto com a maquina desligada",
                       "furto_capo", 2, "{\"sensor\":\"reed_capo\"}");
    capoAnterior = Estado::capoAberto;
#endif
#if USAR_REED_TANQUE
    if (Estado::tanqueAberto && !tanqueAnterior && !Estado::motorLigado)
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

namespace Chama {
#if USAR_CHAMA
  bool anterior = false;

  // INPUT_PULLUP: com o DO solto/desconectado o pino fica em HIGH (= sem chama),
  // em vez de flutuar e disparar alarme fantasma. O DO do KY-026 (saida do LM393)
  // puxa para LOW na chama e vence o pull-up interno.
  void iniciar() { pinMode(CHAMA_PIN, INPUT_PULLUP); }
  void ler() { Estado::chamaDetectada = digitalRead(CHAMA_PIN) == LOW; }  // KY-026: LOW = chama
  void eventos() {
    if (Estado::chamaDetectada && !anterior) {
      Evento::disparar("INCENDIO", "chama detectada", "chama_detectada", 5,
                       "{\"sensor\":\"ky026\"}");
      Alarme::beep(2000, 500);   // 2000 Hz = chama (diferente do furto)
    }
    anterior = Estado::chamaDetectada;
  }
  void imprimir() { if (Estado::chamaDetectada) Serial.println("!!! CHAMA DETECTADA !!!"); }
  void telemetria(Json &j) {
    j.add(",\"chama_detectada\":%s", Estado::chamaDetectada ? "true" : "false");
  }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void eventos() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}

// Potenciometro simula a ignicao que, no produto final, viria do veiculo.
namespace Motor {
#if USAR_POT
  bool anterior = false;

  void ler() {
    bool ligado = analogRead(POT_PIN) >= LIMIAR_POT_MOTOR_DESLIGADO;
    // Desligar encerra a sessao: o cracha tem de ser passado de novo na proxima
    // partida, senao uma autorizacao de ontem valeria para o ladrao de hoje.
    if (!ligado && Estado::motorLigado) Estado::operadorAutorizado = false;
    Estado::motorLigado = ligado;
  }
  void eventos() {
    if (Estado::motorLigado && !anterior && !Estado::operadorAutorizado)
      Evento::disparar("FURTO", "partida sem cracha autorizado - possivel roubo",
                       "operador_nao_autorizado", 3, "{\"origem\":\"rc522\"}");
    anterior = Estado::motorLigado;
  }
  void imprimir() {
    Serial.printf("Potenciometro (motor): %s | operador: %s\n",
                  Estado::motorLigado ? "ligado" : "DESLIGADO",
                  Estado::operadorAutorizado ? "autorizado" : "sem cracha");
  }
  void telemetria(Json &j) {
    j.add(",\"motor_ligado\":%s", Estado::motorLigado ? "true" : "false");
  }
#else
  inline void ler() {}
  inline void eventos() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}

// ---------------------------------------------------------------------------
// Decisao: severidade e nivel de risco (vai na coluna nivel_risco)
// ---------------------------------------------------------------------------
namespace Risco {
  void calcular() {
    int sev = 0;
    // Incendio: monitorado sempre, ligado ou desligado.
    if (Estado::chamaDetectada)                         sev = max(sev, 5);
    if (Estado::tempEscape >= TEMP_ESCAPE_CRITICO)      sev = max(sev, 4);
    else if (Estado::tempEscape >= TEMP_ESCAPE_ATENCAO) sev = max(sev, 2);

    if (!Estado::motorLigado) {
      // Parada = vigilancia. Qualquer coisa mexendo na maquina e suspeita.
      if (Estado::vibracaoConfirmada) sev = max(sev, 4);
      if (Estado::capoAberto)         sev = max(sev, 2);
      if (Estado::tanqueAberto)       sev = max(sev, 3);
    } else if (!Estado::operadorAutorizado) {
      sev = max(sev, 3);              // ligada sem cracha = roubo em andamento
    }

    Estado::severidade = sev;
    Estado::nivelRisco = (sev >= 4) ? "CRITICO" : (sev >= 2) ? "ATENCAO" : "SEGURO";
  }
}

// ---------------------------------------------------------------------------
// Rede: Wi-Fi, NTP e envio ao Supabase (tarefa propria - o loop nunca posta)
// ---------------------------------------------------------------------------
namespace Rede {
#if USAR_WIFI
  struct Payload {
    char tabela[12];
    char json[TAM_PAYLOAD];
  };
  QueueHandle_t filaEventos = NULL;
  QueueHandle_t caixaTelemetria = NULL;
  unsigned long ok = 0, falha = 0, perdidos = 0;
  unsigned long ultimaTentativa = 0;
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

  // Retorna false enquanto o NTP nao sincronizou - ai criado_em e omitido e o
  // default do banco (now()) assume, que e o melhor disponivel.
  bool carimboISO(char* txt, size_t n) {
    struct tm t;
    if (!getLocalTime(&t, 5)) return false;
    snprintf(txt, n, "%04d-%02d-%02dT%02d:%02d:%02d%+03d:00",
             t.tm_year + 1900, t.tm_mon + 1, t.tm_mday,
             t.tm_hour, t.tm_min, t.tm_sec, GMT_OFFSET_SEC / 3600);
    return true;
  }

  bool postar(const char* tabela, const char* json) {
    WiFiClientSecure cliente;
    // Autentica pelo CA raiz embutido. O firmware antigo usava setInsecure()
    // porque o simulador nao trazia o bundle de CAs; com internet real nao ha
    // motivo para aceitar qualquer certificado.
    cliente.setCACert(ROOT_CA);
    cliente.setTimeout(TIMEOUT_HTTP / 1000);

    char url[160];
    snprintf(url, sizeof(url), "%s/rest/v1/%s", SUPABASE_URL_CFG, tabela);

    HTTPClient http;
    if (!http.begin(cliente, url)) { Serial.println("[REDE] http.begin() falhou"); return false; }
    http.setTimeout(TIMEOUT_HTTP);
    http.addHeader("apikey", SUPABASE_CHAVE_CFG);
    http.addHeader("Authorization", "Bearer " SUPABASE_CHAVE_CFG);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Prefer", "return=minimal");   // sem eco do registro: poupa RAM

    int codigo = http.POST((uint8_t*)json, strlen(json));
    bool sucesso = (codigo >= 200 && codigo < 300);
    if (!sucesso) {
      // O corpo do erro do PostgREST diz exatamente o que esta errado (coluna
      // inexistente, RLS negando, JSON invalido). Sem isso a depuracao e cega.
      String corpo = (codigo > 0) ? http.getString() : String(http.errorToString(codigo));
      Serial.printf("[REDE] falha no envio - %s HTTP %d: %.80s\n", tabela, codigo, corpo.c_str());
    }
    http.end();
    return sucesso;
  }

  // Consumidora das duas filas. Roda no nucleo 0 (onde o Wi-Fi vive); o loop()
  // fica sozinho no nucleo 1 e nunca espera pela rede.
  void tarefa(void*) {
    Payload p;
    for (;;) {
      if (WiFi.status() != WL_CONNECTED) { vTaskDelay(pdMS_TO_TICKS(PAUSA_SEM_REDE)); continue; }

      // Evento tem prioridade: e o que nao pode se perder.
      if (xQueueReceive(filaEventos, &p, 0) == pdTRUE) {
        bool enviou = false;
        for (int t = 1; t <= MAX_TENTATIVAS_ENVIO && !enviou; t++) {
          enviou = postar(p.tabela, p.json);
          if (!enviou) vTaskDelay(pdMS_TO_TICKS(500 * t));   // recuo progressivo
        }
        if (enviou) { ok++; }
        else {
          falha++;
          // Volta para a FRENTE da fila para preservar a ordem cronologica - a
          // nao ser que ela esteja cheia, e ai o evento se perde de verdade.
          if (xQueueSendToFront(filaEventos, &p, 0) != pdTRUE) {
            perdidos++;
            Serial.println("[REDE] fila cheia - EVENTO PERDIDO");
          }
          vTaskDelay(pdMS_TO_TICKS(PAUSA_SEM_REDE));
        }
      } else if (xQueueReceive(caixaTelemetria, &p, 0) == pdTRUE) {
        // Telemetria nao volta para a fila: a proxima amostra ja e melhor.
        if (postar(p.tabela, p.json)) ok++; else falha++;
      } else {
        vTaskDelay(pdMS_TO_TICKS(PAUSA_ENVIO));
        continue;
      }
      vTaskDelay(pdMS_TO_TICKS(PAUSA_ENVIO));
    }
  }

  void iniciar() {
    // Filas antes do Wi-Fi: um evento pode nascer antes da rede subir.
    filaEventos = xQueueCreate(FILA_EVENTOS, sizeof(Payload));
    caixaTelemetria = xQueueCreate(1, sizeof(Payload));
    if (!filaEventos || !caixaTelemetria) {
      Serial.println("ERRO: sem RAM para as filas - envio desativado");
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

  void enfileirarEvento(Payload &p) {
    if (!filaEventos) return;
    if (xQueueSend(filaEventos, &p, 0) != pdTRUE) {
      perdidos++;
      Serial.println("[REDE] fila de eventos cheia - EVENTO PERDIDO");
    }
  }

  void imprimir() {
    Serial.printf("Rede: %s | envios ok=%lu falha=%lu | eventos perdidos=%lu\n",
                  WiFi.status() == WL_CONNECTED ? "conectado" : "SEM WI-FI", ok, falha, perdidos);
  }
#else
  inline void iniciar() {}
  inline void manter() {}
  inline void imprimir() {}
#endif
}

// ---------------------------------------------------------------------------
// Telemetria: uma amostra periodica com o retrato do estado
// ---------------------------------------------------------------------------
namespace Telemetria {
#if USAR_WIFI || DIAG_TELEMETRIA
  void montar(Json &j) {
    j.add("{\"dispositivo_id\":\"%s\"", DISPOSITIVO_ID);
#if USAR_WIFI
    char quando[40];
    if (Rede::carimboISO(quando, sizeof(quando))) j.add(",\"criado_em\":\"%s\"", quando);
#endif
    Termopar::telemetria(j);
    Aht::telemetria(j);
    Chama::telemetria(j);
    Mpu::telemetria(j);
    Motor::telemetria(j);
    Reed::telemetria(j);
    Rfid::telemetria(j);
    j.add(",\"nivel_risco\":\"%s\"}", Estado::nivelRisco);
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
      strncpy(p.tabela, "telemetria", sizeof(p.tabela) - 1);
      p.tabela[sizeof(p.tabela) - 1] = '\0';
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
    j.add("{\"dispositivo_id\":\"%s\"", DISPOSITIVO_ID);
    char quando[40];
    if (Rede::carimboISO(quando, sizeof(quando))) j.add(",\"criado_em\":\"%s\"", quando);
    j.add(",\"tipo\":\"%s\",\"severidade\":%d", tipo, sev);
    if (Termopar::ok) j.add(",\"temp_escape\":%.1f", Estado::tempEscape);
    j.add(",\"detalhes\":%s}", detalhes);

    Rede::Payload p;
    strncpy(p.tabela, "eventos", sizeof(p.tabela) - 1);
    p.tabela[sizeof(p.tabela) - 1] = '\0';
    memcpy(p.json, j.txt, j.n + 1);
    Rede::enfileirarEvento(p);
#else
    (void)tipo; (void)sev; (void)detalhes;
#endif
  }
}

// ---------------------------------------------------------------------------
// Diagnostico e Serial
// ---------------------------------------------------------------------------
namespace Painel {
#if DIAG_I2C
  // Esperado: 0x68 (MPU, AD0 no GND) e, do passo 2 em diante, 0x38 (AHT10).
  // Barramento vazio aponta fiacao/alimentacao, nao biblioteca.
  void escanearI2C() {
    Serial.println("Scanner I2C: procurando dispositivos...");
    byte achados = 0;
    for (byte addr = 0x08; addr < 0x78; addr++) {
      Wire.beginTransmission(addr);
      if (Wire.endTransmission() == 0) {
        Serial.printf("  I2C: dispositivo encontrado em 0x%02X\n", addr);
        achados++;
      }
    }
    if (!achados)
      Serial.println("  I2C: NENHUM. Confira 3.3V, GND, SDA=21, SCL=22 e AD0 no GND.");
  }
#else
  inline void escanearI2C() {}
#endif

  void imprimirEstado() {
    Mpu::imprimir();
    Aht::imprimir();
    Gps::imprimir();
    Termopar::imprimir();
    Reed::imprimir();
    Chama::imprimir();
    Motor::imprimir();
    if (!Estado::motorLigado && Estado::vibracaoConfirmada)
      Serial.println("!!! ALERTA: vibracao detectada com motor desligado !!!");
    Serial.printf("Risco: %s (severidade %d)\n", Estado::nivelRisco, Estado::severidade);
    Rede::imprimir();
    Serial.println("--------------------------------------");
  }
}

// ---------------------------------------------------------------------------
// setup / loop
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("=== Sistema Sompo - Inicializando sensores ===");

#if USAR_MPU || USAR_AHT || DIAG_I2C
  Wire.begin(I2C_SDA, I2C_SCL);
#endif
#if USAR_RFID || USAR_TERMOPAR
  SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI);   // barramento compartilhado
#endif

  Painel::escanearI2C();
  Mpu::iniciar();
  Aht::iniciar();
  Gps::iniciar();
  Rfid::iniciar();
  Termopar::iniciar();
  Reed::iniciar();
  Chama::iniciar();
  Alarme::iniciar();
  Alarme::autoteste();
  Rede::iniciar();

  Serial.println("=== Setup concluido ===\n");
}

// Agendamento por millis(), nunca delay(): os sensores rapidos (e o RFID, que
// precisa ser pesquisado a cada passagem, senao o cartao teria de ficar
// encostado dois segundos), os de conversao lenta, e o retrato no Serial.
void loop() {
  Rede::manter();
  unsigned long agora = millis();

  static unsigned long ciclo = 0, lento = 0, serial = 0, saude = 0, telemetria = 0;

  if (agora - ciclo >= INTERVALO_CICLO_MS) {
    ciclo = agora;
    Mpu::ler();
    Gps::ler();
    Rfid::ler();
    Reed::ler();
    Chama::ler();
    Motor::ler();

    Risco::calcular();

    Motor::eventos();
    Mpu::eventos();
    Reed::eventos();
    Chama::eventos();
    Termopar::eventos();
  }

  if (agora - lento >= INTERVALO_LENTO_MS) {
    lento = agora;
    Aht::ler();
    Termopar::ler();
  }

  if (agora - serial >= INTERVALO_SERIAL_MS) {
    serial = agora;
    Painel::imprimirEstado();
  }

  if (agora - saude >= INTERVALO_SAUDE_MPU_MS) {
    saude = agora;
    Mpu::saude();
  }

  if (agora - telemetria >= INTERVALO_TELEMETRIA_MS) {
    telemetria = agora;
    Telemetria::enviar();
  }
}
