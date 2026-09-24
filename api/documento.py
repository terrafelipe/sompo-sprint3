from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from relatorios import TIPOS_LEGIVEIS, legivel

# Brasília é UTC-3 fixo (o Brasil não tem horário de verão desde 2019), então um
# offset fixo é exato e evita depender do banco de fusos (tzdata) no Windows.
FUSO_BRASILIA = timezone(timedelta(hours=-3))

VERMELHO = (183, 1, 0)
TINTA = (24, 24, 27)
SUAVE = (113, 113, 122)
LINHA = (228, 228, 231)
FUNDO = (244, 244, 245)

_CLASSIF = {
    'ALTO': ('Alto', (186, 26, 26)),
    'MEDIO': ('Médio', (180, 83, 9)),
    'BAIXO': ('Baixo', (21, 128, 61)),
}

# Mesma escala do painel: severidade 1..5 vale 5/10/20/40/70 pontos.
_GRAVIDADE = {1: 'Baixa', 2: 'Moderada', 3: 'Média', 4: 'Alta', 5: 'Crítica'}
_PONTOS_MINIMOS = [(70, 5), (40, 4), (20, 3), (10, 2), (0, 1)]

_ORIGEM_TEXTO = {
    'llm': 'Análise escrita por IA (Google Gemini) sobre scores calculados pelo sistema.',
    'prompt_apenas': 'Análise por template (sem chave de IA configurada).',
    'fallback': 'Análise por template (provedor de IA indisponível no momento).',
}

# A Helvetica embutida no PDF só cobre latin-1: pontuação tipográfica vira o
# equivalente simples e o que sobrar (emoji, por exemplo) é descartado.
_TROCAS = str.maketrans({'—': '-', '–': '-', '“': '"', '”': '"', '‘': "'", '’': "'",
                         '…': '...', '•': '-', '≥': '>=', '≤': '<=', '→': '->'})


def para_brasilia(iso_utc: str | None) -> str:
    """Converte um timestamp ISO em UTC para 'DD/MM/AAAA HH:MM' no horário de Brasília."""
    if not iso_utc:
        return '—'
    try:
        dt = datetime.fromisoformat(str(iso_utc).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(FUSO_BRASILIA).strftime('%d/%m/%Y %H:%M')
    except (ValueError, TypeError):
        return str(iso_utc)


def _latin1(texto: Any) -> str:
    return str(texto).translate(_TROCAS).encode('latin-1', 'ignore').decode('latin-1')


def _nome_tipo(tipo: Any) -> str:
    nome = TIPOS_LEGIVEIS.get(str(tipo)) or legivel(str(tipo))
    return nome[:1].upper() + nome[1:]


def _gravidade_media(pontos: int, quantidade: int) -> str:
    media = pontos / quantidade if quantidade else 0
    return next(_GRAVIDADE[g] for minimo, g in _PONTOS_MINIMOS if media >= minimo)


def _severidade(valor: Any) -> str:
    try:
        return f'{int(valor)} · {_GRAVIDADE[int(valor)]}'
    except (KeyError, TypeError, ValueError):
        return str(valor if valor is not None else '-')


class RelatorioPDF(FPDF):
    def __init__(self):
        super().__init__(format='A4')
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(True, margin=18)
        self.rodape = ''

    def footer(self):
        self.set_y(-12)
        self.set_font('Helvetica', size=8)
        self.set_text_color(*SUAVE)
        self.cell(0, 5, self.rodape)
        self.set_x(self.l_margin)
        self.cell(0, 5, f'Página {self.page_no()} de {{nb}}', align='R')


def _secao(pdf: FPDF, titulo: str) -> None:
    pdf.ln(5)
    if pdf.will_page_break(24):
        pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*TINTA)
    pdf.cell(0, 7, _latin1(titulo), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*LINHA)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)


def _paragrafo(pdf: FPDF, texto: str, tamanho: float = 10, cor=TINTA, estilo: str = '') -> None:
    pdf.set_font('Helvetica', estilo, tamanho)
    pdf.set_text_color(*cor)
    pdf.multi_cell(0, tamanho * 0.5, _latin1(texto), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _tabela(pdf: FPDF, cabecalho: List[str], linhas: List[List[str]], larguras, alinhamento) -> None:
    pdf.set_font('Helvetica', size=9)
    pdf.set_text_color(*TINTA)
    pdf.set_draw_color(*LINHA)
    pdf.set_fill_color(255, 255, 255)
    estilo = FontFace(emphasis='BOLD', color=SUAVE, fill_color=FUNDO)
    with pdf.table(col_widths=larguras, text_align=alinhamento, line_height=5,
                   borders_layout='HORIZONTAL_LINES', headings_style=estilo, padding=(1.5, 2)) as tabela:
        for valores in [cabecalho, *linhas]:
            linha = tabela.row()
            for valor in valores:
                linha.cell(_latin1(valor))


def _identificacao(pdf: FPDF, relatorio: Dict[str, Any]) -> None:
    equipamento = relatorio.get('equipamento') or {}
    fazenda = relatorio.get('fazenda') or {}
    dias = relatorio.get('periodo_dias')
    campos = [
        ('Máquina', f"{equipamento.get('nome', '-')} (ID {equipamento.get('id_equipamento', '-')})" if equipamento else '-'),
        ('Fazenda', fazenda.get('nome') or 'Cadastro pendente'),
        ('Dispositivo', relatorio.get('dispositivo') or '-'),
        ('Período', 'Último dia' if dias == 1 else f'Últimos {dias} dias'),
        ('Análise gerada em', f"{para_brasilia(relatorio['gerado_em'])} (Brasília)" if relatorio.get('gerado_em') else '-'),
        ('Documento emitido em', f"{datetime.now(FUSO_BRASILIA).strftime('%d/%m/%Y %H:%M')} (Brasília)"),
    ]
    for rotulo, valor in campos:
        pdf.set_font('Helvetica', size=9)
        pdf.set_text_color(*SUAVE)
        pdf.cell(42, 5.5, _latin1(rotulo))
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*TINTA)
        pdf.multi_cell(0, 5.5, _latin1(valor), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _eixo(pdf: FPDF, titulo: str, eixo: str, relatorio: Dict[str, Any]) -> None:
    _secao(pdf, titulo)
    classif = str(relatorio.get(f'classificacao_{eixo}') or '').upper()
    nome_classif, cor_classif = _CLASSIF.get(classif, (classif.title() or '-', TINTA))
    score = str(relatorio.get(f'score_{eixo}', '-'))

    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_text_color(*TINTA)
    pdf.cell(pdf.get_string_width(score) + 1, 10, score)
    pdf.set_font('Helvetica', size=10)
    pdf.set_text_color(*SUAVE)
    pdf.cell(pdf.get_string_width('/100') + 5, 10, '/100')
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(*cor_classif)
    pdf.cell(pdf.get_string_width(nome_classif) + 6, 10, _latin1(nome_classif))
    acumulado = (relatorio.get('pontos_acumulados') or {}).get(eixo)
    if acumulado is not None:
        pdf.set_font('Helvetica', size=9)
        pdf.set_text_color(*SUAVE)
        pdf.cell(0, 10, f'{acumulado} pontos somados no período (o score vai até 100)')
    pdf.ln(12)

    justificativa = relatorio.get(f'justificativa_{eixo}')
    if justificativa:
        _paragrafo(pdf, legivel(str(justificativa)))

    itens = sorted(((t, v) for t, v in (relatorio.get('detalhamento') or {}).items() if v.get('eixo') == eixo),
                   key=lambda item: -item[1].get('pontos', 0))
    pdf.ln(2)
    if not itens:
        _paragrafo(pdf, 'Nenhum evento deste tipo no período.', 9, SUAVE, 'I')
        return
    _tabela(pdf, ['De onde vem o score', 'Ocorrências', 'Gravidade', 'Pontos'],
            [[_nome_tipo(t), v.get('quantidade', 0), _gravidade_media(v.get('pontos', 0), v.get('quantidade', 0)),
              v.get('pontos', 0)] for t, v in itens],
            (70, 25, 30, 25), ('LEFT', 'RIGHT', 'LEFT', 'RIGHT'))


def montar_pdf(relatorio: Dict[str, Any], eventos: List[Dict[str, Any]]) -> bytes:
    """Monta o relatório de risco em PDF (A4) e devolve os bytes."""
    equipamento = relatorio.get('equipamento') or {}
    maquina = equipamento.get('nome') or relatorio.get('dispositivo') or '-'

    pdf = RelatorioPDF()
    pdf.set_title(_latin1(f'Relatório de risco - {maquina}'))
    pdf.set_author('SOMPO')
    pdf.rodape = _latin1(f'Relatório de risco · {maquina}')
    pdf.add_page()

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(*VERMELHO)
    pdf.cell(0, 5, 'SOMPO · Monitoramento de máquinas agrícolas', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.set_font('Helvetica', 'B', 20)
    pdf.set_text_color(*TINTA)
    pdf.cell(0, 10, 'Relatório de risco', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    _identificacao(pdf, relatorio)

    origem = relatorio.get('origem_da_analise', '')
    pdf.ln(2)
    _paragrafo(pdf, _ORIGEM_TEXTO.get(origem, f'Origem da análise: {origem}'), 8.5, SUAVE, 'I')

    _eixo(pdf, 'Furto', 'furto', relatorio)
    _eixo(pdf, 'Incêndio', 'incendio', relatorio)

    recomendacoes = relatorio.get('recomendacoes') or []
    if recomendacoes:
        _secao(pdf, 'Recomendações')
        for item in recomendacoes:
            pdf.set_fill_color(*VERMELHO)
            pdf.rect(pdf.l_margin + 1, pdf.get_y() + 2, 1.3, 1.3, style='F')
            pdf.set_x(pdf.l_margin + 5)
            pdf.set_font('Helvetica', size=10)
            pdf.set_text_color(*TINTA)
            pdf.multi_cell(0, 5, _latin1(legivel(str(item))), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

    limitacoes = relatorio.get('limitacoes')
    if limitacoes:
        _secao(pdf, 'Limitações')
        _paragrafo(pdf, legivel(str(limitacoes)))

    _secao(pdf, f'Eventos no período ({len(eventos)})')
    if not eventos:
        _paragrafo(pdf, 'Nenhum evento registrado no período.', 9, SUAVE, 'I')
    else:
        _paragrafo(pdf, 'Horários de Brasília.', 8.5, SUAVE)
        pdf.ln(1)
        linhas = []
        for ev in eventos:
            ocorrido = ev.get('ocorrido_em') if ev.get('registro_id') else ev.get('criado_em')
            linhas.append([para_brasilia(ocorrido) if ocorrido else 'Horário desconhecido',
                           _nome_tipo(ev.get('tipo', '-')), _severidade(ev.get('severidade')),
                           ev.get('operador_nome') or 'Não identificado', ev.get('sessao_id') or '-'])
        _tabela(pdf, ['Data e hora', 'Tipo', 'Gravidade', 'Operador', 'Sessão'], linhas,
                (33, 44, 25, 40, 28), ('LEFT', 'LEFT', 'LEFT', 'LEFT', 'LEFT'))

    return bytes(pdf.output())
