// Decisao: severidade e nivel de risco (coluna nivel_risco).
#pragma once
#include "estado.h"

// ---------------------------------------------------------------------------
// Decisao: severidade e nivel de risco (vai na coluna nivel_risco)
// ---------------------------------------------------------------------------
namespace Risco {
  void calcular() {
    int sev = 0;
    // Incendio: monitorado sempre, ligado ou desligado.
    if (Estado.chamaDetectada)                         sev = max(sev, 5);
    if (Estado.tempEscape >= TEMP_ESCAPE_CRITICO)      sev = max(sev, 4);
    else if (Estado.tempEscape >= TEMP_ESCAPE_ATENCAO) sev = max(sev, 2);

    // Furto so conta com o sistema ARMADO (sem cracha). Desarmado = operador
    // legitimo presente, entao capo/tanque/vibracao/partida nao sobem o risco.
    if (!Estado.operadorAutorizado) {
      if (!Estado.motorLigado) {
        // Parada = vigilancia. Qualquer coisa mexendo na maquina e suspeita.
        if (Estado.vibracaoConfirmada) sev = max(sev, 4);
        if (Estado.capoAberto)         sev = max(sev, 2);
        if (Estado.tanqueAberto)       sev = max(sev, 3);
      } else {
        sev = max(sev, 3);              // ligada sem cracha = roubo em andamento
      }
    }

    Estado.severidade = sev;
    Estado.nivelRisco = (sev >= 4) ? "CRITICO" : (sev >= 2) ? "ATENCAO" : "SEGURO";
  }
}
