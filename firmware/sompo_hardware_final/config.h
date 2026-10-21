// Flags dos sensores, pinos e parametros ajustaveis na bancada.
#pragma once

// ---------- Ligue um sensor por vez ----------
#define USAR_MPU          1
#define USAR_AHT          1
#define USAR_BUZZER       1
#define USAR_RFID         1
#define USAR_TERMOPAR     1
#define USAR_CHAMA        1   // KY-026 lido pelo A0 (analogico): o D0 queimou (ver docs)
#define USAR_REED_CAPO    1
#define USAR_POT          1   // pot montado no GPIO34 (simula a ignicao)
#define USAR_GPS          1   // montado (sem fix indoor: Serial mostra "sem fix")
#define USAR_REED_TANQUE  1
#define USAR_WIFI         1   // ULTIMO PASSO: envio ao Supabase (exige segredos.h)

#define DIAG_I2C          1   // scanner I2C no setup (ajuda nos passos 1 e 2)
#define DIAG_TELEMETRIA   0   // imprime o JSON no Serial; funciona com USAR_WIFI 0

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
#define CHAMA_PIN   35   // A0 do KY-026 (analogico). O D0 queimou; A0 no GPIO35 = ADC1
                         // e so-entrada, sobrevive ao Wi-Fi (o antigo D0/25 era ADC2 e morreria).
#define POT_PIN     34   // pot montado: ADC1 (a chama saiu do 34 pro 35, sem conflito)
#define BUZZER_PIN  26

// ---------- Parametros ajustaveis na bancada ----------
#define INTERVALO_CICLO_MS      100    // amostragem dos sensores rapidos
#define INTERVALO_SERIAL_MS     2000   // retrato periodico no Monitor Serial
#define INTERVALO_LENTO_MS      2000   // AHT10 e MAX6675 (conversao lenta)
#define INTERVALO_TELEMETRIA_MS 10000  // amostra gravada no Supabase (10s: casa com o refresh de 5s
                                       // do painel; gera ~3x mais linhas na tabela telemetria - ok p/ demo)
#define INTERVALO_TELEMETRIA_AO_VIVO_MS 2000  // modo ao vivo, ligado pelo painel (resposta do registrar_dispositivo)
#define INTERVALO_SAUDE_MPU_MS  5000   // reconferencia do MPU no barramento

#define LIMIAR_POT_MOTOR_DESLIGADO 2000  // pot (0-4095) abaixo disso = desligado
#define LIMIAR_CHAMA        2000         // A0 do KY-026 (raw 0-4095) abaixo disso = chama. CALIBRAR
#define LIMIAR_VIBRACAO     2.0          // desvio em m/s2 do repouso = vibracao
#define AMOSTRAS_BASELINE   50           // amostras que calibram o repouso
#define AMOSTRAS_VIBRACAO   3            // leituras seguidas p/ confirmar
#define TEMP_ESCAPE_ATENCAO 450.0        // C - termopar tipo K
#define TEMP_ESCAPE_CRITICO 550.0        // C
#define TRAVA_EVENTO_MS     5000         // anti-spam dos eventos continuos
#define GRAVIDADE           9.80665      // m/s2 por g

// Tom do alarme (buzzer continuo). Passivo? o volume e maximo perto da frequencia
// de RESSONANCIA do buzzer (varia por modelo, tipico 2000-4000 Hz) - ajuste por ouvido.
#define BUZZER_FREQ_CHAMA   2000         // Hz - alarme de incendio (fogo/temperatura)
#define BUZZER_FREQ_FURTO   3000         // Hz - alarme de furto (vibracao/capo/tanque/partida)

#define DISPOSITIVO_ID "ESP-3036EN"     // TEM de ser o ID cadastrado na maquina (painel > Frota)
#define TAM_PAYLOAD    1024              // registro com identidade, sessao e dados do sensor

#if USAR_WIFI
  #define LIMITE_FILA_DURAVEL  (512 * 1024) // LittleFS reservado a eventos/transicoes
  #define MAX_OPERADORES_CACHE     32
  #define INTERVALO_SINCRONIA_MS   60000
  #define TIMEOUT_HTTP             8000  // ms - POST inteiro, com handshake TLS
  #define MAX_TENTATIVAS_ENVIO     3     // reenvios antes de devolver a fila
  #define PAUSA_ENVIO              250   // ms entre POSTs (nao afoga a fila)
  #define PAUSA_SEM_REDE           2000  // ms de espera sem Wi-Fi
  #define INTERVALO_TENTATIVA_WIFI 10000 // ms entre tentativas de reconexao
  #define GMT_OFFSET_SEC      (-3 * 3600)   // Brasil UTC-3, sem horario de verao
  #define DAYLIGHT_OFFSET_SEC 0
  #define NTP_SERVER          "pool.ntp.org"
#endif
