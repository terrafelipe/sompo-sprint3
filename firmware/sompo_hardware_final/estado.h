// Estado compartilhado entre sensores, risco, telemetria e Serial; e o montador de JSON.
#pragma once
#include "config.h"

#include <stdarg.h>

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
