// Sensor MPU-6050 (vibracao).
#pragma once
#include "bibliotecas.h"
#include "estado.h"
#include "evento.h"

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
    Estado.baselineAccel = soma / AMOSTRAS_BASELINE;
    Estado.magnitudeAccel = Estado.baselineAccel;
    Serial.printf("MPU-6050 baseline de repouso: %.2f m/s2 (limiar: %.2f)\n",
                  Estado.baselineAccel, (float)LIMIAR_VIBRACAO);
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
    Estado.magnitudeAccel = sqrt(a.acceleration.x * a.acceleration.x +
                                  a.acceleration.y * a.acceleration.y +
                                  a.acceleration.z * a.acceleration.z);
    float desvio = fabs(Estado.magnitudeAccel - Estado.baselineAccel);

    // A coluna 'vibracao' guarda g - o historico foi gravado assim. Sem esta
    // conversao a media do resumo_diario misturaria m/s2 com g.
    Estado.vibracaoG = desvio / GRAVIDADE;

    // Uma leitura isolada acima do limiar e ruido; N seguidas e vibracao.
    if (desvio > LIMIAR_VIBRACAO) { if (amostrasAcima < AMOSTRAS_VIBRACAO) amostrasAcima++; }
    else                          { amostrasAcima = 0; }
    Estado.vibracaoConfirmada = (amostrasAcima >= AMOSTRAS_VIBRACAO);
  }

  // Parada a maquina, o MPU e o unico sensor de adulteracao. Se ele sumir, a
  // deteccao morre CALADA - arrancar o fio seria a forma mais barata de burlar
  // o sistema. Perder o sensor e, ele mesmo, um evento de furto.
  void saude() {
    Wire.beginTransmission(0x68);
    bool presente = (Wire.endTransmission() == 0);
    if (!presente && ok) {
      ok = false;
      Estado.vibracaoG = 0.0;
      amostrasAcima = 0;
      Estado.vibracaoConfirmada = false;
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
    // Desarmado (cracha passado) = operador legitimo mexendo: nao e furto.
    if (!Estado.vibracaoConfirmada || Estado.motorLigado || Estado.operadorAutorizado) return;
    if (agora - ultimoEvento <= TRAVA_EVENTO_MS) return;
    ultimoEvento = agora;
    char det[96];
    snprintf(det, sizeof(det), "{\"vibracao_g\":%.3f,\"limiar_ms2\":%.2f}",
             Estado.vibracaoG, (float)LIMIAR_VIBRACAO);
    Evento::disparar("FURTO", "vibracao detectada com a maquina desligada",
                     "furto_adulteracao", 4, det);
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
                  Estado.magnitudeAccel,
                  fabs(Estado.magnitudeAccel - Estado.baselineAccel),
                  (float)LIMIAR_VIBRACAO, Estado.vibracaoG,
                  Estado.vibracaoConfirmada ? "  <-- VIBRACAO" : "");
  }

  void telemetria(Json &j) { if (ok) j.add(",\"vibracao\":%.3f", Estado.vibracaoG); }
#else
  inline void iniciar() {}
  inline void ler() {}
  inline void saude() {}
  inline void eventos() {}
  inline void imprimir() {}
  inline void telemetria(Json&) {}
#endif
}
