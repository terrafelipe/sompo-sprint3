/* Linha do tempo do Painel da maquina (Issue #5): resumo, um grafico so e a lista de eventos.
   Sem rede: o index.html busca /telemetria/linha-do-tempo e chama
   window.LinhaDoTempo.montar(container, dados, {titulos, animar, estado?}) -> {destruir(), selecionar(idEvento|null), estado}
   (passar o `estado` da vista anterior mantem filtro, selecao e grupos abertos no redesenho)
   window.LinhaDoTempo.grupos(eventos) -> [{id, tipo, itens}]  (alarmes repetidos viram um grupo)
   Tudo que vem da API entra por esc() ou textContent. Cores so pelas variaveis do painel (temas). */
(function(){
  'use strict';
  const MIN = 60000;
  const FUSO = 'America/Sao_Paulo';
  const F_HORA = new Intl.DateTimeFormat('pt-BR', {hour:'2-digit', minute:'2-digit', timeZone:FUSO});
  const F_DIA = new Intl.DateTimeFormat('pt-BR', {day:'2-digit', month:'2-digit', timeZone:FUSO});
  const F_DIA_LONGO = new Intl.DateTimeFormat('pt-BR', {weekday:'long', day:'numeric', month:'long', timeZone:FUSO});
  const hora = t => F_HORA.format(t), dia = t => F_DIA.format(t);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dur = min => { min = Math.round(min || 0); return min >= 60 ? `${Math.floor(min / 60)} h${min % 60 ? ' ' + String(min % 60).padStart(2, '0') : ''}` : `${min} min`; };
  const ms = iso => { const t = Date.parse(iso); return isNaN(t) ? null : t; };
  const graus = v => `${Math.round(v)} °C`;
  const reduzido = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const LACUNA_MIN = 15;   // igual ao backend (linha_do_tempo.LACUNA_MIN)

  const ROTINA = {cracha_inicio:'Crachá aceito', cracha_fim:'Sessão encerrada', cracha_negado:'Crachá recusado',
    motor_ligou:'Motor ligou', motor_parou:'Motor parou', temp_normal:'Temperatura voltou ao normal',
    envio_parou:'Placa parou de enviar', envio_voltou:'Placa voltou a enviar'};
  const ICONE = {chama_detectada:'local_fire_department', escape_critico:'device_thermostat', escape_atencao:'device_thermostat',
    furto_capo:'car_repair', furto_tanque:'local_gas_station', furto_movimento:'directions_run', furto_adulteracao:'vibration',
    operador_nao_autorizado:'no_accounts', sensor_falha:'sensors_off', cracha_negado:'badge', cracha_inicio:'badge',
    cracha_fim:'logout', motor_ligou:'power_settings_new', motor_parou:'power_off', temp_normal:'thermostat',
    envio_parou:'wifi_off', envio_voltou:'wifi'};
  const SENSOR = {furto_capo:'Sensor do capô', furto_tanque:'Sensor do tanque', furto_movimento:'Vibração fora do normal',
    furto_adulteracao:'Vibração fora do normal', operador_nao_autorizado:'Motor ligado sem sessão de crachá',
    sensor_falha:'Sensor de adulteração sem resposta', chama_detectada:'Sensor de chama'};
  const FILTROS = [['tudo', 'Tudo'], ['alarmes', 'Só alarmes'], ['incendio', 'Incêndio'], ['furto', 'Furto'], ['rotina', 'Rotina']];

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

  function detalhe(e){
    switch(e.tipo){
      case 'escape_atencao': case 'escape_critico': return e.temp != null ? graus(e.temp) : 'Temperatura do escape';
      case 'cracha_inicio': return e.operador_nome || 'Operador não identificado';
      case 'cracha_fim': return [e.operador_nome, e.duracao_min != null ? `${dur(e.duracao_min)} de uso` : ''].filter(Boolean).join(' · ');
      case 'cracha_negado': return e.uid ? `Cartão ${String(e.uid).match(/.{1,2}/g).join(':')} não cadastrado` : 'Cartão não cadastrado';
      case 'motor_ligou': return e.com_cracha === true ? 'Partida com crachá' : e.com_cracha === false ? 'Sem sessão de crachá aberta' : '';
      case 'motor_parou': return `Ficou ${dur(e.duracao_min)} ligado`;
      case 'temp_normal': return `${graus(e.temp)} · calculado das leituras`;
      case 'envio_parou': return `Sem leituras por ${dur(e.duracao_min)}`;
      case 'envio_voltou': return 'Leituras normais de novo';
      default: return SENSOR[e.tipo] || '';
    }
  }

  function montar(cont, dados, op = {}){
    const ini = ms(dados.janela.inicio), fim = ms(dados.janela.fim), minutos = dados.janela.minutos, passo = minutos * MIN;
    const faixas = dados.faixas || [], eventos = dados.eventos || [], sessoes = dados.sessoes || [];
    const lim = dados.limites || {atencao: 450, critico: 550};
    const titulos = op.titulos || {};
    const titulo = e => titulos[e.tipo] || ROTINA[e.tipo] || e.tipo;
    const antes = op.estado || {};
    const estado = {filtro: antes.filtro || 'tudo', sel: antes.sel ?? null, abertos: new Set(antes.abertos || []),
                    animar: !!op.animar, recemAberto: null};
    const sessaoEm = t => sessoes.find(s => { const a = ms(s.inicio) ?? ini, b = ms(s.fim) ?? fim; return t >= a && t <= b; });
    const doId = id => eventos.find(e => String(e.id) === String(id));
    let geo = null;

    cont.innerHTML = `
      <div class="lt-resumo" id="ltResumo" aria-label="Resumo do período"></div>
      <div class="lt-legenda" aria-hidden="true">
        <span><i class="lt-l-temp"></i>Temperatura do escape</span><span><i class="lt-l-motor"></i>Motor ligado</span>
        <span><i class="lt-l-cracha"></i>Crachá</span><span><i class="lt-l-lacuna"></i>Placa sem enviar</span>
      </div>
      <div class="lt-grafico" id="ltGrafico"></div>
      <div class="lt-leitura" id="ltLeitura" aria-live="polite"></div>
      <div class="lt-barra">
        <div class="seg" role="group" aria-label="Filtrar eventos" id="ltFiltros">${FILTROS.map(([f, nome]) =>
          `<button type="button" data-f="${f}" aria-pressed="${f === 'tudo'}">${nome}</button>`).join('')}</div>
        <span class="lt-cont" id="ltCont"></span>
      </div>
      <div class="lt-lista" id="ltLista"></div>`;
    const $ = id => cont.querySelector('#' + id);
    const passaFiltro = e => estado.filtro === 'tudo' || (estado.filtro === 'alarmes' ? e.eixo !== 'rotina' : e.eixo === estado.filtro);

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
      geo = {X};
      let g = '';
      for(const [k, v] of noEixo){
        const cor = k === 'critico' ? 'var(--s-incendio)' : 'var(--lt-atencao)';
        g += `<line class="lt-limite" x1="${ML}" x2="${W - MR}" y1="${Yt(v).toFixed(1)}" y2="${Yt(v).toFixed(1)}" style="stroke:${cor}" stroke-dasharray="3 4" stroke-opacity=".75"/>`;
        g += `<text x="${ML - 6}" y="${(Yt(v) + 3.5).toFixed(1)}" text-anchor="end" font-size="10" style="fill:${cor}">${graus(v)}</text>`;
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
      if(d) g += `<path class="lt-temp${estado.animar ? ' lt-desenha' : ''}" d="${d}" fill="none" style="stroke:var(--v-texto-sec)" stroke-width="1.6" stroke-linejoin="round" pathLength="1000"/>`;
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
      // eixo do tempo: 5 marcas ate 2 dias; um rotulo por dia ate 8 dias; senao 5 marcas com a data
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
        const sel = gr.itens.some(i => String(i.id) === String(estado.sel));
        marc += `<g class="lt-marca${sel ? ' sel' : ''}" data-lt-marca="${esc(gr.id)}" data-ev="${esc(e.id)}" role="button" tabindex="0" aria-label="${esc(titulo(e))} às ${hora(ms(e.em))}">
          <line x1="${x}" x2="${x}" y1="12" y2="${YC + AB}" style="stroke:${cor}" stroke-opacity="${sel ? .9 : .35}" stroke-width="${sel ? 1.5 : 1}"/>
          ${sel ? `<circle class="lt-anel" cx="${x}" cy="8" r="5" fill="none" style="stroke:${cor}" stroke-width="2"/>` : ''}
          <circle cx="${x}" cy="8" r="${e.sev === 'critico' ? 5 : 4}" style="fill:${cor};stroke:var(--v-card)" stroke-width="2"/>
          ${gr.itens.length > 1 ? `<text x="${(+x + 7).toFixed(1)}" y="11" font-size="9.5" font-weight="600" style="fill:${cor}">×${gr.itens.length}</text>` : ''}
          <rect class="lt-alvo" x="${(+x - 12).toFixed(1)}" y="-4" width="24" height="${YC + AB + 4}" fill="transparent"/></g>`;
      }
      const fora = [['atencao', 'atenção'], ['critico', 'crítico']].filter(([k]) => lim[k] != null && !noEixo.some(([j]) => j === k))
        .map(([k, nome]) => `${nome}: ${graus(lim[k])}`);
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
      svg.addEventListener('pointerleave', () => lerSelecao());
      svg.querySelectorAll('.lt-marca').forEach(m => {
        const ir = () => selecionar(m.dataset.ev, true);
        m.addEventListener('click', ir);
        m.addEventListener('keydown', ev => { if(ev.key === 'Enter' || ev.key === ' '){ ev.preventDefault(); ir(); } });
      });
    }

    function lerPadrao(){
      const c = cont.querySelector('.lt-cursor'); if(c) c.setAttribute('opacity', 0);
      $('ltLeitura').innerHTML = eventos.length
        ? '<span class="p"><span class="material-symbols-outlined">touch_app</span>Toque ou arraste no gráfico para ler um horário; toque num ponto para ver o alarme.</span>'
        : '<span class="p">A máquina ficou parada e sem alarmes neste período.</span>';
    }
    function lerSelecao(){
      const e = estado.sel != null ? doId(estado.sel) : null;
      if(e) lerHorario(ms(e.em), titulo(e)); else lerPadrao();
    }
    function lerHorario(t, tit){
      const c = cont.querySelector('.lt-cursor');
      if(c && geo){ const x = geo.X(t).toFixed(1); c.setAttribute('x1', x); c.setAttribute('x2', x); c.setAttribute('opacity', .55); }
      const f = faixas[Math.min(faixas.length - 1, Math.max(0, Math.floor((t - ini) / passo)))];
      const s = sessaoEm(t), vazio = !f || !f.leituras;
      $('ltLeitura').innerHTML = `<strong>${dia(t)} ${hora(t)}</strong>`
        + (tit ? `<span class="p lt-tit">${esc(tit)}</span>` : '')
        + (vazio ? '<span class="p"><i style="background:var(--v-borda-forte)"></i>Sem leituras</span>'
          : (f.temp_max != null ? `<span class="p">Escape <strong>${graus(f.temp_max)}</strong></span>` : '')
            + `<span class="p"><i style="background:${f.motor_ligado ? 'var(--lt-ok)' : 'var(--v-texto3)'}"></i>Motor ${f.motor_ligado ? 'ligado' : 'parado'}</span>`)
        + (s ? `<span class="p"><i style="background:var(--s-furto)"></i>${esc(s.operador_nome || 'Sessão de crachá')}</span>` : (vazio ? '' : '<span class="p">Sem crachá</span>'));
    }

    function lista(){
      const vis = eventos.filter(passaFiltro), L = $('ltLista');
      const nAl = vis.filter(e => e.eixo !== 'rotina').length;
      $('ltCont').textContent = vis.length ? `${vis.length} ${vis.length === 1 ? 'evento' : 'eventos'}${estado.filtro === 'tudo' ? ` · ${nAl} ${nAl === 1 ? 'alarme' : 'alarmes'}` : ''}` : '';
      const aviso = dados.omitidos ? `<p class="lt-omitidos">${Number(dados.omitidos).toLocaleString('pt-BR')} eventos de rotina mais antigos não aparecem; escolha um período menor.</p>` : '';
      if(!vis.length){
        L.innerHTML = (eventos.length
          ? `<div class="lt-vazio"><span class="material-symbols-outlined">filter_alt_off</span><strong>Nenhum evento com este filtro</strong><span>Troque o filtro para ver os outros eventos.</span><button type="button" class="lt-btn" data-ver-tudo>Ver tudo</button></div>`
          : `<div class="lt-vazio"><span class="material-symbols-outlined">event_available</span><strong>Nenhum evento neste período</strong><span>Sem alarmes, partidas ou crachás entre ${dia(ini)} ${hora(ini)} e ${dia(fim)} ${hora(fim)}.</span></div>`) + aviso;
        return;
      }
      // dias: mais recente primeiro; dentro do dia, em ordem de hora (conta a historia)
      const porDia = new Map();
      for(const e of vis){ const k = dia(ms(e.em)); if(!porDia.has(k)) porDia.set(k, []); porDia.get(k).push(e); }
      let html = '', i = 0;
      for(const [k, evs] of [...porDia.entries()].reverse()){
        const n = evs.filter(e => e.eixo !== 'rotina').length;
        html += `<div data-dia="${k}"><div class="lt-dia" style="--i:${i++}"><span>${F_DIA_LONGO.format(ms(evs[0].em))}</span><em>${n ? `${n} ${n === 1 ? 'alarme' : 'alarmes'}` : 'sem alarmes'}</em></div>`;
        for(const g of grupos(evs)){
          const e = g.itens[0], qtd = g.itens.length, ult = g.itens[qtd - 1];
          const sel = g.itens.some(x => String(x.id) === String(estado.sel)), aberto = estado.abertos.has(g.id);
          const pill = e.sev === 'critico' ? '<span class="lt-pill critico"><span class="material-symbols-outlined">priority_high</span>Crítico</span>'
            : e.sev === 'atencao' ? '<span class="lt-pill atencao">Atenção</span>' : '<span class="lt-pill rotina">Rotina</span>';
          const temps = g.itens.map(x => x.temp).filter(v => v != null);
          const det = qtd > 1 ? `${qtd} vezes entre ${hora(ms(e.em))} e ${hora(ms(ult.em))}${temps.length ? ` · até ${graus(Math.max(...temps))}` : ''}` : detalhe(e);
          html += `<button type="button" class="lt-ev ${e.eixo}${qtd > 1 ? ' grupo' : ''}${sel ? ' sel' : ''}" style="--i:${i++}" data-lt-alvo="${esc(g.id)}" data-ev="${esc(e.id)}"${qtd > 1 ? ` aria-expanded="${aberto}"` : ''}>
            <span class="h">${hora(ms(e.em))}</span><span class="ico"><span class="material-symbols-outlined">${ICONE[e.tipo] || 'error'}</span></span>
            <span class="txt"><span class="tit">${esc(titulo(e))}${qtd > 1 ? ' <span class="material-symbols-outlined seta">expand_more</span>' : ''}</span><span class="det${e.tipo === 'temp_normal' ? ' calc' : ''}">${esc(det)}</span></span>${pill}</button>`;
          if(qtd > 1 && aberto) html += `<div class="lt-filhos${g.id === estado.recemAberto ? '' : ' aberto'}" data-de="${esc(g.id)}"><div>${g.itens.map(x =>
            `<div class="lt-filho"><span>${hora(ms(x.em))}</span><span></span><span><b>${esc(titulo(x))}</b> · ${esc(detalhe(x))}</span></div>`).join('')}</div></div>`;
        }
        html += '</div>';
      }
      L.innerHTML = html + aviso;
      if(estado.recemAberto){   // o grupo que acabou de abrir anima a altura (0fr -> 1fr)
        const f = L.querySelector(`.lt-filhos[data-de="${CSS.escape(estado.recemAberto)}"]`);
        estado.recemAberto = null;
        if(f){ f.getBoundingClientRect(); f.classList.add('aberto'); }
      }
      if(estado.animar && !reduzido()) L.classList.add('lt-anim'); else L.classList.remove('lt-anim');
    }

    function desenhar(){
      resumo(); grafico(); lista(); lerSelecao();
      cont.querySelectorAll('#ltFiltros [data-f]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.f === estado.filtro)));
      estado.animar = false;
    }
    function filtrar(f){ estado.filtro = f; desenhar(); }
    function selecionar(id, rolar){
      estado.sel = id != null && String(id) === String(estado.sel) && !rolar ? null : id;
      desenhar();
      if(rolar && estado.sel != null){
        const linha = [...$('ltLista').querySelectorAll('.lt-ev')].find(b => b.classList.contains('sel'));
        if(linha) linha.scrollIntoView({behavior: reduzido() ? 'auto' : 'smooth', block: 'center'});
      }
    }

    cont.onclick = ev => {   // um so por container: montar de novo substitui o anterior
      const chip = ev.target.closest('[data-filtro]');
      if(chip){ filtrar(estado.filtro === chip.dataset.filtro ? 'tudo' : chip.dataset.filtro); return; }
      const f = ev.target.closest('#ltFiltros [data-f]');
      if(f){ filtrar(f.dataset.f); return; }
      if(ev.target.closest('[data-ver-tudo]')){ filtrar('tudo'); return; }
      const linha = ev.target.closest('.lt-ev');
      if(linha){
        if(linha.classList.contains('grupo')){
          const id = linha.dataset.ltAlvo;
          if(estado.abertos.has(id)) estado.abertos.delete(id); else { estado.abertos.add(id); estado.recemAberto = id; }
        }
        const y = window.scrollY;
        selecionar(linha.dataset.ev, false);
        window.scrollTo(window.scrollX, y);
      }
    };

    desenhar();
    return {
      destruir(){ cont.onclick = null; cont.innerHTML = ''; },
      selecionar(id){ selecionar(id, false); },
      estado,
    };
  }

  window.LinhaDoTempo = {montar, grupos};
})();
