/* Calendario proprio do painel (um so, reaproveitado por todos os botoes de periodo e de data).
   Troca datas como texto AAAA-MM-DD (sem Date local no meio: nada de erro de fuso) e usa o dia de Brasilia.
   window.Calendario.abrir({ancora, modo: 'intervalo' | 'dia', inicio?, fim?, aoAplicar(inicio, fim)})
   window.Calendario.fechar()  .hoje()  .formatar('AAAA-MM-DD') -> 'dd/mm/aaaa' */
(function(){
  'use strict';
  const MESES = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];
  const MESES_CURTOS = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
  const ATALHOS = [['hoje','Hoje'],['ontem','Ontem'],['7','Últimos 7 dias'],['30','Últimos 30 dias'],
                   ['mes','Este mês'],['mespassado','Mês passado'],['90','Últimos 90 dias']];
  const DIA_MS = 864e5;

  // ---- datas como texto AAAA-MM-DD, calculadas em UTC (meia-noite) para nao sofrer com horario de verao ----
  const ms = s => { const [a, m, d] = s.split('-').map(Number); return Date.UTC(a, m - 1, d); };
  const iso = t => new Date(t).toISOString().slice(0, 10);
  const soma = (s, n) => iso(ms(s) + n * DIA_MS);
  const diaDaSemana = s => new Date(ms(s)).getUTCDay();
  const ultimoDiaDoMes = (a, m) => new Date(Date.UTC(a, m, 0)).getUTCDate();   // m = 1..12
  const mesDe = s => s.slice(0, 7);
  const primeiroDoMes = s => `${mesDe(s)}-01`;
  const somaMeses = (s, n) => {   // mesmo dia n meses depois, limitado ao ultimo dia do mes
    const [a, m, d] = s.split('-').map(Number), k = a * 12 + (m - 1) + n, ano = Math.floor(k / 12), mes = k % 12 + 1;
    return `${String(ano).padStart(4, '0')}-${String(mes).padStart(2, '0')}-${String(Math.min(d, ultimoDiaDoMes(ano, mes))).padStart(2, '0')}`;
  };
  const dias = (a, b) => Math.round((ms(b) - ms(a)) / DIA_MS) + 1;
  const formatar = s => `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
  const curto = s => `${Number(s.slice(8, 10))} ${MESES_CURTOS[Number(s.slice(5, 7)) - 1]}`;
  const hoje = () => new Intl.DateTimeFormat('sv-SE', {timeZone: 'America/Sao_Paulo'}).format(new Date());

  function atalho(chave){
    const h = hoje();
    switch(chave){
      case 'hoje': return [h, h];
      case 'ontem': return [soma(h, -1), soma(h, -1)];
      case '7': return [soma(h, -6), h];
      case '30': return [soma(h, -29), h];
      case '90': return [soma(h, -89), h];
      case 'mes': return [primeiroDoMes(h), h];
      case 'mespassado': { const fim = soma(primeiroDoMes(h), -1); return [primeiroDoMes(fim), fim]; }
    }
  }

  let el = null, est = null;

  function montar(){
    el = document.createElement('div');
    el.id = 'calendario';
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-label', 'Escolher período');
    el.hidden = true;
    el.innerHTML = `
      <div class="cal-corpo">
        <div class="cal-atalhos" id="calAtalhos"></div>
        <div class="cal-mes">
          <div class="cal-cab">
            <div class="cal-titulo" id="calTitulo" aria-live="polite"></div>
            <div class="cal-nav">
              <button type="button" data-nav="-12" aria-label="Ano anterior" title="Ano anterior"><span class="material-symbols-outlined">keyboard_double_arrow_left</span></button>
              <button type="button" data-nav="-1" aria-label="Mês anterior" title="Mês anterior"><span class="material-symbols-outlined">chevron_left</span></button>
              <button type="button" data-nav="1" aria-label="Próximo mês" title="Próximo mês"><span class="material-symbols-outlined">chevron_right</span></button>
              <button type="button" data-nav="12" aria-label="Próximo ano" title="Próximo ano"><span class="material-symbols-outlined">keyboard_double_arrow_right</span></button>
            </div>
          </div>
          <div class="cal-grade" id="calGrade" role="grid"></div>
        </div>
      </div>
      <div class="cal-rod">
        <div class="cal-resumo" id="calResumo" aria-live="polite"></div>
        <div class="cal-acoes">
          <button type="button" class="cal-link" id="calLimpar">Limpar</button>
          <button type="button" class="cal-prim" id="calAplicar">Aplicar</button>
        </div>
      </div>`;
    document.body.appendChild(el);
    el.addEventListener('click', aoClicar);
    el.addEventListener('mouseover', aoPassar);
    el.addEventListener('keydown', aoTeclar);
    document.addEventListener('mousedown', e => {
      if(est && !el.contains(e.target) && !est.ancora.contains(e.target)) fechar(false);
    });
    document.addEventListener('keydown', e => {
      if(est && e.key === 'Escape'){ e.preventDefault(); fechar(true); }
    });
    addEventListener('resize', () => { if(est) posicionar(); });
  }

  function faixa(){
    let a = est.ini, b = est.fim || (est.ini && est.hover);
    if(a && b && b < a) [a, b] = [b, a];
    return [a, b];
  }

  function desenhar(manterFoco){
    const tinhaFoco = manterFoco && el.contains(document.activeElement) && document.activeElement.dataset.dia;
    const [a, b] = faixa(), h = hoje(), mes = est.vista;
    const [ano, m] = mes.split('-').map(Number);
    $t('calTitulo').textContent = `${MESES[m - 1]} de ${ano}`;
    let html = ['D','S','T','Q','Q','S','S'].map(s => `<div class="cal-sem" role="columnheader">${s}</div>`).join('');
    const primeiro = `${mes}-01`, inicio = soma(primeiro, -diaDaSemana(primeiro));
    for(let i = 0; i < 42; i++){
      const d = soma(inicio, i), c = ['dia'];
      if(mesDe(d) !== mes) c.push('fora');
      if(d === h) c.push('hoje');
      const futuro = d > h;
      if(futuro) c.push('futuro');
      if(a && b && d >= a && d <= b){
        if(d === a) c.push('ini');
        if(d === b) c.push('fim');
        if(d !== a && d !== b) c.push('meio');
      } else if(a && !b && d === a) c.push('ini', 'fim');
      html += `<button type="button" class="${c.join(' ')}" data-dia="${d}" tabindex="${d === est.foco ? 0 : -1}"${futuro ? ' disabled' : ''}`
            + ` aria-label="${Number(d.slice(8))} de ${MESES[Number(d.slice(5, 7)) - 1]} de ${d.slice(0, 4)}"${a && b && d >= a && d <= b ? ' aria-pressed="true"' : ''}><span>${Number(d.slice(8))}</span></button>`;
    }
    const grade = $t('calGrade');
    grade.innerHTML = html;
    grade.dataset.mes = mes;
    if(est.modo === 'intervalo'){
      $t('calAtalhos').innerHTML = ATALHOS.map(([k, nome]) => {
        const [x, y] = atalho(k);
        return `<button type="button" data-atalho="${k}" aria-pressed="${x === est.ini && y === est.fim}">${nome}</button>`;
      }).join('');
    }
    $t('calResumo').textContent = '';
    $t('calResumo').innerHTML = est.modo === 'dia' ? 'Escolha o dia'
      : !a ? 'Escolha a data inicial'
      : !b ? `<b>${curto(a)}</b> até ...`
      : `<b>${curto(a)}</b> até <b>${curto(b)}</b> · ${dias(a, b)} ${dias(a, b) > 1 ? 'dias' : 'dia'}`;
    $t('calAplicar').disabled = !a;
    if(tinhaFoco) irParaFoco();
  }
  const $t = id => document.getElementById(id);

  function irParaFoco(){
    const alvo = el.querySelector(`[data-dia="${est.foco}"]`);
    if(alvo) alvo.focus();
  }

  function posicionar(){
    const r = est.ancora.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight;
    const x = Math.min(Math.max(12, r.left), Math.max(12, innerWidth - w - 12));
    let y = r.bottom + 6;
    if(y + h > innerHeight - 12 && r.top > h + 12) y = r.top - h - 6;
    el.style.left = `${x}px`;
    el.style.top = `${Math.max(12, y)}px`;
  }

  function abrir({ancora, modo = 'intervalo', inicio = null, fim = null, aoAplicar}){
    if(!el) montar();
    if(est && est.ancora === ancora){ fechar(true); return; }   // clicar de novo no botao fecha
    if(est) fechar(false);
    const h = hoje();
    const ini = inicio && inicio <= h ? inicio : null;
    const fi = modo === 'dia' ? ini : (fim && fim <= h ? fim : null);
    const referencia = fi || ini || h;
    est = {ancora, modo, ini, fim: fi, hover: null, vista: mesDe(referencia), foco: referencia > h ? h : referencia, aoAplicar};
    el.classList.toggle('unico', modo === 'dia');
    el.setAttribute('aria-label', modo === 'dia' ? 'Escolher o dia' : 'Escolher período');
    ancora.setAttribute('aria-expanded', 'true');
    el.hidden = false;
    desenhar(false);
    posicionar();
    requestAnimationFrame(() => el.classList.add('vis'));
    irParaFoco();
  }

  function fechar(devolverFoco){
    if(!est) return;
    const ancora = est.ancora;
    est = null;
    ancora.setAttribute('aria-expanded', 'false');
    el.classList.remove('vis');
    el.hidden = true;
    if(devolverFoco) ancora.focus();
  }

  function escolher(d){
    if(d > hoje()) return;
    est.foco = d;
    if(est.modo === 'dia'){
      const cb = est.aoAplicar;
      fechar(true);
      if(cb) cb(d, d);
      return;
    }
    if(!est.ini || est.fim){ est.ini = d; est.fim = null; }
    else { est.fim = d; if(est.fim < est.ini) [est.ini, est.fim] = [est.fim, est.ini]; }
    est.hover = null;
    if(mesDe(d) !== est.vista) est.vista = mesDe(d);
    desenhar(true);
  }

  function aoClicar(e){
    const dia = e.target.closest('[data-dia]'), nav = e.target.closest('[data-nav]'), at = e.target.closest('[data-atalho]');
    if(dia && !dia.disabled) escolher(dia.dataset.dia);
    else if(nav){ est.vista = mesDe(somaMeses(`${est.vista}-01`, Number(nav.dataset.nav))); est.foco = ajustarFoco(somaMeses(est.foco, Number(nav.dataset.nav))); desenhar(false); }
    else if(at){
      [est.ini, est.fim] = atalho(at.dataset.atalho);
      est.hover = null; est.foco = est.fim; est.vista = mesDe(est.fim);
      desenhar(false);
    }
    else if(e.target.closest('#calLimpar')){ est.ini = est.fim = est.hover = null; desenhar(false); }
    else if(e.target.closest('#calAplicar')){
      const [a, b] = faixa();
      if(!a) return;
      const cb = est.aoAplicar;
      fechar(true);
      if(cb) cb(a, b || a);
    }
  }

  function aoPassar(e){
    const dia = e.target.closest('[data-dia]');
    if(!dia || dia.disabled || !est.ini || est.fim || est.modo !== 'intervalo') return;
    if(est.hover === dia.dataset.dia) return;
    est.hover = dia.dataset.dia;
    desenhar(true);
  }

  const ajustarFoco = d => { const h = hoje(); return d > h ? h : d; };

  function aoTeclar(e){
    const dia = e.target.closest && e.target.closest('[data-dia]');
    if(!dia) return;
    let d = est.foco;
    switch(e.key){
      case 'ArrowLeft': d = soma(d, -1); break;
      case 'ArrowRight': d = soma(d, 1); break;
      case 'ArrowUp': d = soma(d, -7); break;
      case 'ArrowDown': d = soma(d, 7); break;
      case 'Home': d = soma(d, -diaDaSemana(d)); break;
      case 'End': d = soma(d, 6 - diaDaSemana(d)); break;
      case 'PageUp': d = somaMeses(d, e.shiftKey ? -12 : -1); break;
      case 'PageDown': d = somaMeses(d, e.shiftKey ? 12 : 1); break;
      default: return;
    }
    e.preventDefault();
    est.foco = ajustarFoco(d);
    if(mesDe(est.foco) !== est.vista) est.vista = mesDe(est.foco);
    desenhar(false);
    irParaFoco();
  }

  window.Calendario = {abrir, fechar: () => fechar(false), hoje, formatar};
})();
