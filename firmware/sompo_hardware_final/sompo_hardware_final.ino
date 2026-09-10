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
 *
 * Logica de alerta (demo): o potenciometro simula o sinal de ignicao que, no
 * produto final, viria do proprio veiculo. Se o "motor" estiver desligado E o
 * MPU-6050 detectar vibracao fora do normal, dispara alerta (indicio de veiculo
 * sendo mexido enquanto deveria estar parado).
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
 */

// ---------- Teste incremental: ligue um sensor por vez ----------
// Ordem: MPU -> AHT -> BUZZER -> RFID/TERMOPAR/CHAMA/REED/POT
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
#define DIAG_I2C          1   // scanner I2C no setup (ajuda nos passos 1 e 2)

#include <Wire.h>

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

// Potenciometro - simula motor ligado/desligado
#define POT_PIN 34

// Buzzer
#define BUZZER_PIN 26

// ---------- Parametros ajustaveis na bancada ----------
#define INTERVALO_LEITURA_MS 2000
#define LIMIAR_POT_MOTOR_DESLIGADO 2000  // leitura do pot (0-4095) abaixo disso = "motor desligado"
#define LIMIAR_VIBRACAO 2.0              // desvio em m/s2 do repouso = "vibracao"
#define AMOSTRAS_BASELINE 50             // amostras para calibrar o repouso do MPU

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
#endif

#if USAR_TERMOPAR
// Lib RobTillaart: construtor software SPI e (select, miso, clock) - CS primeiro
MAX6675 termopar(TERMOPAR_CS, SPI_MISO, SPI_SCK);
#endif

// Magnitude do vetor de aceleracao: a lida por ultimo e a de repouso (calibrada no
// setup quando o MPU esta ligado). Ficam fora do #if USAR_MPU porque a logica de
// alerta tambem as usa - com USAR_MPU 0 as duas ficam iguais, entao o alerta de
// vibracao nunca dispara falso.
float baselineAccel = 9.8;
float ultimaMagnitudeAccel = 9.8;

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

  Serial.println("=== Setup concluido ===\n");
}

void loop() {
  // TODO (quando chegar o passo do RC522): trocar este delay por agendamento com
  // millis() - o RFID precisa ser pesquisado a cada iteracao, senao so le se o
  // cartao ficar encostado os 2 s inteiros. O resto continua a cada 2 s.
#if USAR_MPU
  lerMPU();
#endif
#if USAR_AHT
  lerAHT();
#endif
#if USAR_GPS
  lerGPS();
#endif
#if USAR_RFID
  lerRFID();
#endif
#if USAR_TERMOPAR
  lerTermopar();
#endif
#if USAR_REED_CAPO || USAR_REED_TANQUE
  lerReedSwitches();
#endif
#if USAR_CHAMA
  lerChama();
#endif
#if USAR_POT
  lerMotorEAlerta();
#endif

  Serial.println("--------------------------------------");
  delay(INTERVALO_LEITURA_MS);
}

// ---------- Funcoes de leitura ----------

#if USAR_MPU
void lerMPU() {
  if (!mpuOk) {
    Serial.println("MPU-6050 indisponivel (falhou no setup)");
    return;
  }

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);
  Serial.printf("Acel (m/s2): X=%.2f Y=%.2f Z=%.2f\n", a.acceleration.x, a.acceleration.y, a.acceleration.z);
  Serial.printf("Giro (rad/s): X=%.2f Y=%.2f Z=%.2f\n", g.gyro.x, g.gyro.y, g.gyro.z);

  // magnitude total do vetor de aceleracao (parado, fica perto do baseline)
  ultimaMagnitudeAccel = sqrt(a.acceleration.x * a.acceleration.x +
                              a.acceleration.y * a.acceleration.y +
                              a.acceleration.z * a.acceleration.z);

  // Esta linha e a que usamos para calibrar LIMIAR_VIBRACAO na bancada:
  // parado o desvio fica perto de 0; batendo na mesa ele sobe.
  float desvio = fabs(ultimaMagnitudeAccel - baselineAccel);
  Serial.printf("|a|=%.2f m/s2 (desvio %.2f, limiar %.2f)%s\n",
                ultimaMagnitudeAccel, desvio, (float)LIMIAR_VIBRACAO,
                desvio > LIMIAR_VIBRACAO ? "  <-- VIBRACAO" : "");
}
#endif

#if USAR_AHT
void lerAHT() {
  if (!ahtOk) {
    Serial.println("AHT10 indisponivel (falhou no setup)");
    return;
  }
  sensors_event_t humidity, temp;
  aht.getEvent(&humidity, &temp);
  Serial.printf("Ambiente: %.1f C | %.1f %% UR\n", temp.temperature, humidity.relative_humidity);
}
#endif

#if USAR_GPS
void lerGPS() {
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }
  if (gps.location.isUpdated()) {
    Serial.printf("GPS: Lat=%.6f Lon=%.6f\n", gps.location.lat(), gps.location.lng());
  } else {
    Serial.println("GPS: sem fix ainda");
  }
}
#endif

#if USAR_RFID
void lerRFID() {
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    Serial.print("RFID detectado - UID:");
    for (byte i = 0; i < rfid.uid.size; i++) {
      Serial.print(rfid.uid.uidByte[i] < 0x10 ? " 0" : " ");
      Serial.print(rfid.uid.uidByte[i], HEX);
    }
    Serial.println();
    rfid.PICC_HaltA();
  }
}
#endif

#if USAR_TERMOPAR
void lerTermopar() {
  uint8_t status = termopar.read();
  if (status == STATUS_OK) {
    Serial.printf("Termopar: %.1f C\n", termopar.getCelsius());
  } else {
    Serial.println("Termopar: erro de leitura (confira fiacao/CS)");
  }
}
#endif

#if USAR_REED_CAPO || USAR_REED_TANQUE
void lerReedSwitches() {
#if USAR_REED_CAPO
  bool capoAberto = digitalRead(REED_CAPO) == HIGH;   // HIGH = contato aberto = capo aberto
  Serial.printf("Capo: %s\n", capoAberto ? "ABERTO" : "fechado");
#endif
#if USAR_REED_TANQUE
  bool tanqueAberto = digitalRead(REED_TANQUE) == HIGH;
  Serial.printf("Tanque: %s\n", tanqueAberto ? "ABERTO" : "fechado");
#endif
}
#endif

#if USAR_CHAMA
void lerChama() {
  bool chamaDetectada = digitalRead(CHAMA_PIN) == LOW;  // KY-026: LOW = chama detectada
  if (chamaDetectada) {
    Serial.println("!!! CHAMA DETECTADA !!!");
    beep(2000, 500);   // 2000 Hz = chama
  }
}
#endif

#if USAR_POT
void lerMotorEAlerta() {
  int leituraPot = analogRead(POT_PIN);
  bool motorDesligado = leituraPot < LIMIAR_POT_MOTOR_DESLIGADO;
  bool vibracaoDetectada = fabs(ultimaMagnitudeAccel - baselineAccel) > LIMIAR_VIBRACAO;

  Serial.printf("Potenciometro (motor): %d -> %s\n", leituraPot, motorDesligado ? "DESLIGADO" : "ligado");

  if (motorDesligado && vibracaoDetectada) {
    Serial.println("!!! ALERTA: vibracao detectada com motor desligado !!!");
    beep(3000, 400);   // 3000 Hz = furto (frequencia diferente da chama)
  }
}
#endif
