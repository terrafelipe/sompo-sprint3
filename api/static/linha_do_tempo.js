/* Linha do tempo do Painel da maquina (Issue #5): resumo, um grafico so e a lista de eventos.
   Sem rede: o index.html busca /telemetria/linha-do-tempo e chama
   window.LinhaDoTempo.montar(container, dados, {titulos, animar}) -> {destruir(), selecionar(id|null)}
   window.LinhaDoTempo.grupos(eventos) -> [{id, tipo, itens}]  (alarmes repetidos viram um grupo)
   Tudo que vem da API entra por esc() ou textContent. Cores so pelas variaveis do painel (temas). */
(function(){
  'use strict';
  const MIN = 60000;
  const FUSO = 'America/Sao_Paulo';
  const F_HORA = new Intl.DateTimeFormat('pt-BR', {hour:'2-digit', minute:'2-digit', timeZone:FUSO});
  const F_DIA = new Intl.DateTimeFormat('pt-BR', {day:'2-digit', month:'2-digit', timeZone:FUSO});
  const hora = t => F_HORA.format(t), dia = t => F_DIA.format(t);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dur = min => { min = Math.round(min || 0); return min >= 60 ? `${Math.floor(min / 60)} h${min % 60 ? ' ' + String(min % 60).padStart(2, '0') : ''}` : `${min} min`; };
  const ms = iso => { const t = Date.parse(iso); return isNaN(t) ? null : t; };
  const LACUNA_MIN = 15;   // igual ao backend (linha_do_tempo.LACUNA_MIN)

  // Faixas vazias seguidas entre leituras, grandes o bastante: placa sem enviar.
  function lacunas(faixas, minutos){
    const cheias = faixas.map((f, i) => f.leituras ? i : -1).filter(i => i >= 0), out = [];
    for(let k = 1; k < cheias.length; k++){
      const n = cheias[k] - cheias[k - 1] - 1;
      if(n >= 2 && n * minutos >= LACUNA_MIN) out.push([cheias[k - 1] + 1, cheias[k]]);
    }
    return out;
  }

  function grupos(eventos){
    const out = [];
    for(const e of eventos){
      const g = out[out.length - 1], ult = g && g.itens[g.itens.length - 1], t = ms(e.em);
      if(g && e.eixo !== 'rotina' && g.tipo === e.tipo && t - ms(ult.em) <= 30 * MIN && dia(t) === dia(ms(g.itens[0].em))) g.itens.push(e);
      else out.push({id: 'g' + e.id, tipo: e.tipo, itens: [e]});
    }
    return out;
  }

  function montar(cont, dados, op = {}){
    const ini = ms(dados.janela.inicio), fim = ms(dados.janela.fim), minutos = dados.janela.minutos, passo = minutos * MIN;
    const faixas = dados.faixas || [], eventos = dados.eventos || [], sessoes = dados.sessoes || [];
    const lim = dados.limites || {atencao: 450, critico: 550};
    const titulos = op.titulos || {};
    const estado = {filtro: 'tudo', sel: null};
    const sessaoEm = t => sessoes.find(s => { const a = ms(s.inicio) ?? ini, b = ms(s.fim) ?? fim; return t >= a && t <= b; });
    let geo = null;

    cont.innerHTML = `
      <div class="lt-resumo" id="ltResumo" aria-label="Resumo do período"></div>
      <div class="lt-legenda" aria-hidden="true">
        <span><i class="lt-l-temp"></i>Temperatura do escape</span><span><i class="lt-l-motor"></i>Motor ligado</span>
        <span><i class="lt-l-cracha"></i>Crachá</span><span><i class="lt-l-lacuna"></i>Placa sem enviar</span>
      </div>
      <div class="lt-grafico" id="ltGrafico"></div>
      <div class="lt-leitura" id="ltLeitura" aria-live="polite"></div>`;
    const $ = id => cont.querySelector('#' + id);

    function resumo(){
      const r = dados.resumo || {};
      const chip = (cls, ico, txt, f) => `<button type="button" class="lt-chip ${cls}" ${f ? `data-filtro="${f}" aria-pressed="${estado.filtro === f}"` : 'disabled'}><span class="material-symbols-outlined">${ico}</span><span class="t">${txt}</span></button>`;
      const n = (k, um, varios) => `<b>${r[k] || 0}</b> ${r[k] === 1 ? um : varios}`;
      $('ltResumo').innerHTML =
        chip('incendio', 'local_fire_department', n('incendio', 'alarme de incêndio', 'alarmes de incêndio'), 'incendio') +
        chip('furto', 'shield', n('furto', 'alarme de furto', 'alarmes de furto'), 'furto') +
        chip('neutro', 'power_settings_new', `<b>${dur(r.motor_min)}</b> de motor ligado`) +
        (r.sem_envio_min ? chip('neutro', 'wifi_off', `<b>${dur(r.sem_envio_min)}</b> sem enviar`) : '');
    }

    const passaFiltro = e => estado.filtro === 'tudo' || (estado.filtro === 'alarmes' ? e.eixo !== 'rotina' : e.eixo === estado.filtro);

    function grafico(){
      const box = $('ltGrafico'), W = Math.max(300, Math.round(box.clientWidth) || 900), ML = 40, MR = 6, iw = W - ML - MR;
      const Y0 = 18, Y1 = 128, YM = 138, YC = 152, AB = 9, HT = 184;
      const X = t => ML + (t - ini) / (fim - ini) * iw;
      const temps = faixas.map(f => f.temp_max).filter(v => v != null);
      const tmaxD = temps.length ? Math.max(...temps) : null, tminD = temps.length ? Math.min(...temps) : null;
      const cabe = v => tmaxD != null && v <= 1.5 * tmaxD;
      const noEixo = [['atencao', lim.atencao], ['critico', lim.critico]].filter(([, v]) => v != null && cabe(v));
      const hi = Math.max(tmaxD ?? 40, ...noEixo.map(([, v]) => v)), lo = Math.min(tminD ?? 20, hi - 10);
      const pad = (hi - lo) * 0.1, TMIN = lo - pad, TMAX = hi + pad;
      const Yt = v => Y1 - (v - TMIN) / (TMAX - TMIN) * (Y1 - Y0);
      geo = {ML, iw, W, X};
      let g = '';
      for(const [k, v] of noEixo){
        const cor = k === 'critico' ? 'var(--s-incendio)' : 'var(--lt-atencao)';
        g += `<line class="lt-limite" x1="${ML}" x2="${W - MR}" y1="${Yt(v).toFixed(1)}" y2="${Yt(v).toFixed(1)}" style="stroke:${cor}" stroke-dasharray="3 4" stroke-opacity=".75"/>`;
        g += `<text x="${ML - 6}" y="${(Yt(v) + 3.5).toFixed(1)}" text-anchor="end" font-size="10" style="fill:${cor}">${Math.round(v)} °C</text>`;
      }
      g += `<line x1="${ML}" x2="${W - MR}" y1="${Y1}" y2="${Y1}" style="stroke:var(--v-borda)"/>`;
      for(const [a, b] of lacunas(faixas, minutos)){
        const x0 = X(ms(faixas[a].inicio)), x1 = X(ms(faixas[b].inicio));
        g += `<rect class="lt-lacuna" x="${x0.toFixed(1)}" y="${Y0 - 6}" width="${(x1 - x0).toFixed(1)}" height="${YC + AB - Y0 + 6}" fill="url(#ltHach)"/>`;
      }
      // temperatura: maxima de cada faixa no meio dela; faixa sem leitura quebra a linha
      let d = '', area = '', aberto = false, ultX = 0;
      faixas.forEach(f => {
        const x = X(ms(f.inicio) + passo / 2);
        if(f.temp_max == null){ if(aberto) area += `L${ultX.toFixed(1)},${Y1}Z`; aberto = false; return; }
        const p = `${x.toFixed(1)},${Yt(f.temp_max).toFixed(1)}`;
        if(!aberto){ d += `M${p}`; area += `M${x.toFixed(1)},${Y1}L${p}`; aberto = true; } else { d += `L${p}`; area += `L${p}`; }
        ultX = x;
      });
      if(aberto) area += `L${ultX.toFixed(1)},${Y1}Z`;
      if(area) g += `<path d="${area}" style="fill:var(--v-texto-sec)" fill-opacity=".07"/>`;
      if(d) g += `<path class="lt-temp${op.animar ? ' lt-desenha' : ''}" d="${d}" fill="none" style="stroke:var(--v-texto-sec)" stroke-width="1.6" stroke-linejoin="round" pathLength="1000"/>`;
      g += `<text x="${ML - 6}" y="${YM + 7.5}" text-anchor="end" font-size="10" style="fill:var(--v-texto2)">Motor</text>`;
      g += `<text x="${ML - 6}" y="${YC + 7.5}" text-anchor="end" font-size="10" style="fill:var(--v-texto2)">Crachá</text>`;
      g += `<rect x="${ML}" y="${YM}" width="${iw}" height="${AB}" rx="2" style="fill:var(--v-hover)"/><rect x="${ML}" y="${YC}" width="${iw}" height="${AB}" rx="2" style="fill:var(--v-hover)"/>`;
      // motor: trechos seguidos de faixas com o motor ligado
      for(let i = 0; i < faixas.length; i++){
        if(!faixas[i].motor_ligado) continue;
        let j = i; while(j + 1 < faixas.length && faixas[j + 1].motor_ligado) j++;
        const x0 = X(ms(faixas[i].inicio)), x1 = X(ms(faixas[j].inicio) + passo);
        g += `<rect class="lt-motor" x="${x0.toFixed(1)}" y="${YM}" width="${Math.max(2, x1 - x0).toFixed(1)}" height="${AB}" rx="2" style="fill:var(--lt-ok)"/>`;
        i = j;
      }
      for(const s of sessoes){
        const a = Math.max(ms(s.inicio) ?? ini, ini), b = Math.min(ms(s.fim) ?? fim, fim);
        if(b < ini || a > fim || b < a) continue;
        g += `<rect class="lt-cracha" x="${X(a).toFixed(1)}" y="${YC}" width="${Math.max(2, X(b) - X(a)).toFixed(1)}" height="${AB}" rx="2" style="fill:var(--s-furto)" fill-opacity=".55"/>`;
      }
      // eixo do tempo: 5 marcas ate 2 dias; um rotulo por dia ate 8 dias; senao 6 marcas com a data
      const totalH = (fim - ini) / 3600000, porDia = totalH > 48 && totalH <= 192;
      const n = porDia ? Math.round(totalH / 24) : 4;
      for(let k = 0; k <= n; k++){
        const t = ini + (fim - ini) * k / n, x = X(t), anc = k === 0 ? 'start' : k === n ? 'end' : 'middle';
        g += `<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${Y0 - 6}" y2="${YC + AB}" style="stroke:var(--v-borda)" stroke-opacity=".7"/>`;
        g += `<text x="${x.toFixed(1)}" y="${HT - 4}" text-anchor="${anc}" font-size="10" style="fill:var(--v-texto2)">${totalH <= 48 ? hora(t) : dia(t)}</text>`;
      }
      // alarmes: um marcador por grupo
      let marc = '';
      for(const gr of grupos(eventos.filter(e => e.eixo !== 'rotina' && passaFiltro(e)))){
        const e = gr.itens[0], x = X(ms(e.em)).toFixed(1), cor = e.eixo === 'incendio' ? 'var(--s-incendio)' : 'var(--s-furto)';
        const sel = gr.id === estado.sel || gr.itens.some(i => 'g' + i.id === estado.sel);
        marc += `<g class="lt-marca${sel ? ' sel' : ''}" data-lt-marca="${esc(gr.id)}" role="button" tabindex="0" aria-label="${esc(titulos[e.tipo] || e.tipo)} às ${hora(ms(e.em))}">
          <line x1="${x}" x2="${x}" y1="12" y2="${YC + AB}" style="stroke:${cor}" stroke-opacity="${sel ? .9 : .35}" stroke-width="${sel ? 1.5 : 1}"/>
          ${sel ? `<circle class="lt-anel" cx="${x}" cy="8" r="5" fill="none" style="stroke:${cor}" stroke-width="2"/>` : ''}
          <circle cx="${x}" cy="8" r="${e.sev === 'critico' ? 5 : 4}" style="fill:${cor};stroke:var(--v-card)" stroke-width="2"/>
          ${gr.itens.length > 1 ? `<text x="${(+x + 7).toFixed(1)}" y="11" font-size="9.5" font-weight="600" style="fill:${cor}">×${gr.itens.length}</text>` : ''}
          <rect class="lt-alvo" x="${(+x - 12).toFixed(1)}" y="-4" width="24" height="${YC + AB + 4}" fill="transparent"/></g>`;
      }
      const fora = [['atencao', 'atenção'], ['critico', 'crítico']].filter(([k]) => lim[k] != null && !noEixo.some(([j]) => j === k))
        .map(([k, nome]) => `${nome}: ${Math.round(lim[k])} °C`);
      box.innerHTML = (fora.length ? `<div class="lt-fora">Limites acima do gráfico: ${fora.join(' · ')}</div>` : '') +
        `<svg viewBox="0 -6 ${W} ${HT + 6}" role="img" aria-label="Temperatura do escape, motor, crachá e alarmes no período" data-ml="${ML}" data-iw="${iw}" data-ini="${ini}" data-fim="${fim}">
        <defs><pattern id="ltHach" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" style="fill:var(--v-card)"/><line x1="0" y1="0" x2="0" y2="6" style="stroke:var(--v-borda-forte)" stroke-width="2"/></pattern></defs>
        ${g}<line class="lt-cursor" x1="0" x2="0" y1="${Y0 - 6}" y2="${YC + AB}" style="stroke:var(--v-texto)" stroke-width="1" opacity="0"/>${marc}</svg>`;
      const svg = box.querySelector('svg');
      const mover = ev => {
        const r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) / r.width * W;
        if(x < ML || x > ML + iw) return;
        lerHorario(ini + (x - ML) / iw * (fim - ini));
      };
      svg.addEventListener('pointermove', mover);
      svg.addEventListener('pointerdown', mover);
      svg.addEventListener('pointerleave', () => { if(!estado.sel) lerPadrao(); });
    }

    function lerPadrao(){
      const c = cont.querySelector('.lt-cursor'); if(c) c.setAttribute('opacity', 0);
      $('ltLeitura').innerHTML = '<span class="p"><span class="material-symbols-outlined">touch_app</span>Toque ou arraste no gráfico para ler um horário; toque num ponto para ver o alarme.</span>';
    }
    function lerHorario(t, titulo){
      const c = cont.querySelector('.lt-cursor');
      if(c && geo){ const x = geo.X(t).toFixed(1); c.setAttribute('x1', x); c.setAttribute('x2', x); c.setAttribute('opacity', .55); }
      const f = faixas[Math.min(faixas.length - 1, Math.max(0, Math.floor((t - ini) / passo)))];
      const s = sessaoEm(t), vazio = !f || !f.leituras;
      $('ltLeitura').innerHTML = `<strong>${dia(t)} ${hora(t)}</strong>`
        + (titulo ? `<span class="p lt-tit">${esc(titulo)}</span>` : '')
        + (vazio ? '<span class="p"><i style="background:var(--v-borda-forte)"></i>Sem leituras</span>'
          : (f.temp_max != null ? `<span class="p">Escape <strong>${Math.round(f.temp_max)} °C</strong></span>` : '')
            + `<span class="p"><i style="background:${f.motor_ligado ? 'var(--lt-ok)' : 'var(--v-texto3)'}"></i>Motor ${f.motor_ligado ? 'ligado' : 'parado'}</span>`)
        + (s ? `<span class="p"><i style="background:var(--s-furto)"></i>${esc(s.operador_nome || 'Sessão de crachá')}</span>` : (vazio ? '' : '<span class="p">Sem crachá</span>'));
    }

    function desenhar(){ resumo(); grafico(); lerPadrao(); }
    desenhar();
    return {
      destruir(){ cont.innerHTML = ''; },
      selecionar(id){ estado.sel = id; desenhar(); },
    };
  }

  window.LinhaDoTempo = {montar, grupos};
})();
