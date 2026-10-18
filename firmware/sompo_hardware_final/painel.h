// Diagnostico I2C e retrato periodico no Serial.
#pragma once
#include "config.h"
#include "bibliotecas.h"
#include "estado.h"
#include "rede.h"
#include "mpu.h"
#include "aht.h"
#include "gps.h"
#include "termopar.h"
#include "reed.h"
#include "chama.h"
#include "motor.h"

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
