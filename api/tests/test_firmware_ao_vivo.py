"""Contrato do modo ao vivo entre firmware e banco (le o .ino e o .sql como texto)."""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INO = RAIZ / 'firmware' / 'sompo_hardware_final' / 'sompo_hardware_final.ino'
SQL = RAIZ / 'firmware' / 'sql' / 'ao_vivo.sql'

pytestmark = pytest.mark.skipif(not INO.exists(), reason='firmware/ ausente (imagem Docker)')


def _ino():
    """O sketch inteiro: o .ino mais os .h da pasta (o firmware foi dividido em arquivos)."""
    arquivos = [INO] + sorted(p for p in INO.parent.glob('*.h') if not p.name.startswith('segredos'))
    return '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in arquivos)


def _define(nome):
    m = re.search(rf'#define\s+{nome}\s+(\d+)', _ino())
    assert m, f'#define {nome} ausente'
    return int(m.group(1))


def _funcao(assinatura):
    texto = _ino()
    assert assinatura in texto, f'{assinatura} ausente'
    abre = texto.index('{', texto.index(assinatura))
    nivel, j = 0, abre
    while True:
        nivel += {'{': 1, '}': -1}.get(texto[j], 0)
        if nivel == 0:
            return texto[abre:j + 1]
        j += 1


def test_intervalos_do_firmware_batem_com_o_banco():
    assert _define('INTERVALO_TELEMETRIA_MS') == 10000
    assert _define('INTERVALO_TELEMETRIA_AO_VIVO_MS') == 2000
    assert SQL.read_text(encoding='utf-8').count('then 2000 else 10000 end') == 2   # os dois return


def test_so_aceita_os_dois_valores_conhecidos():
    corpo = _funcao('uint32_t intervaloDaResposta(')
    assert '"\\"telemetria_ms\\""' in corpo
    # Qualquer coisa que nao seja exatamente o valor do ao vivo volta ao normal.
    assert re.search(r'==\s*INTERVALO_TELEMETRIA_AO_VIVO_MS\s*\?\s*INTERVALO_TELEMETRIA_AO_VIVO_MS\s*:\s*INTERVALO_TELEMETRIA_MS', corpo)


def test_envio_bem_sucedido_le_o_intervalo_da_resposta():
    corpo = _funcao('Envio postarRpc(')
    assert re.search(r'if\s*\(\s*resultado\s*==\s*ENVIADO\s*\)', corpo)
    assert 'intervaloDaResposta(' in corpo


def test_loop_usa_o_intervalo_variavel():
    corpo = _funcao('void loop()')
    assert 'agora - telemetria >= intervaloTelemetria' in corpo
    assert 'INTERVALO_TELEMETRIA_MS' not in corpo


def test_intervalo_compartilhado_entre_nucleos_e_volatile():
    assert re.search(r'volatile\s+uint32_t\s+intervaloTelemetria\s*=\s*INTERVALO_TELEMETRIA_MS\s*;', _ino())
