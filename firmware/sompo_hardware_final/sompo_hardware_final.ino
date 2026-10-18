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
 *   Reed capo / tanque  32 / 33     KY-026 chama  A0=35 (D0 queimou; A0 e ADC1, aguenta o Wi-Fi)
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
 *
 * ARQUIVOS (todos nesta pasta; o Arduino IDE mostra cada um numa aba):
 *   config.h        flags USAR_* (ligue um sensor por vez), pinos e parametros da bancada
 *   bibliotecas.h   #include das bibliotecas de cada sensor
 *   estado.h        Estado (leituras compartilhadas) e Json
 *   frota.h         identidade da maquina, cracha RFID, fila duravel (LittleFS)
 *   evento.h        declaracao de Evento::disparar (definicao em registro.h)
 *   alarme.h        buzzer
 *   mpu.h aht.h gps.h rfid.h termopar.h reed.h chama.h motor.h   um arquivo por sensor
 *   risco.h         severidade e nivel de risco
 *   rede.h          Wi-Fi, NTP e envio ao Supabase
 *   registro.h      telemetria periodica e eventos (o que vai para a fila)
 *   painel.h        scanner I2C e retrato no Serial
 *   segredos.h      credenciais (so na sua maquina; modelo em segredos.exemplo.h)
 */

#include "config.h"
#include "bibliotecas.h"
#include "estado.h"
#include "frota.h"
#include "evento.h"
#include "alarme.h"
#include "mpu.h"
#include "aht.h"
#include "gps.h"
#include "rfid.h"
#include "termopar.h"
#include "reed.h"
#include "chama.h"
#include "motor.h"
#include "risco.h"
#include "rede.h"
#include "registro.h"
#include "painel.h"

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
  Frota::iniciar();
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

    Alarme::atualizar();   // buzzer continuo enquanto a ameaca estiver presente
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

  if (agora - telemetria >= intervaloTelemetria) {
    telemetria = agora;
    Telemetria::enviar();
  }
}
