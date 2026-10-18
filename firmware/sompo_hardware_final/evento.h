// Declaracao antecipada de Evento::disparar (a definicao esta em registro.h).
#pragma once

// Duas unicas declaracoes antecipadas: os sensores usam as duas, e elas
// dependem de coisas definidas mais abaixo.
namespace Evento {
  void disparar(const char* ctx, const char* msg, const char* tipo,
                int sev, const char* detalhes);
}
