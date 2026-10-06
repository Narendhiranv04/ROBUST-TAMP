/* ROBUST-TAMP project page: interactions. Data: static/js/data.js (window.RT_DATA). */
(function () {
  'use strict';
  const D = window.RT_DATA;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') e.className = v; else if (k === 'style') e.style.cssText = v;
      else if (k === 'html') e.innerHTML = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
    return e;
  };
  const M = D.methods, V = D.variants;
  const vIndex = id => V.findIndex(v => v.id === id);
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------------- reveal on scroll ---------------- */
  const revealObs = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add('in'); revealObs.unobserve(e.target); }
  }), { rootMargin: '0px 0px -8% 0px' });
  const observeReveal = root => $$('.reveal', root).forEach(el => revealObs.observe(el));

  /* ---------------- nav / toc active section ---------------- */
  const navLinks = $$('nav.top a.link, .toc a');
  const secObs = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    const id = e.target.id;
    navLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + id));
  }), { rootMargin: '-35% 0px -60% 0px' });
  $$('section.block').forEach(s => secObs.observe(s));

  /* ---------------- counters ---------------- */
  const countObs = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    countObs.unobserve(e.target);
    $$('[data-count]', e.target).forEach(n => {
      const to = +n.dataset.count, dec = +n.dataset.dec || 0, pre = n.dataset.prefix || '';
      const unit = n.querySelector('.unit'); const t0 = performance.now(), dur = reduced ? 1 : 1400;
      const step = now => {
        const p = Math.min(1, (now - t0) / dur), e3 = 1 - Math.pow(1 - p, 3);
        n.firstChild.nodeValue = pre + (to * e3).toFixed(dec);
        if (p < 1) requestAnimationFrame(step);
      };
      if (!n.firstChild || n.firstChild.nodeType !== 3) n.prepend(document.createTextNode(''));
      if (unit) n.append(unit);
      requestAnimationFrame(step);
    });
  }), { threshold: 0.4 });
  $$('.stats').forEach(s => countObs.observe(s));

  /* ---------------- embedded animations (same-origin iframes driven by the page clock) ---------------- */
  const EMBED_CSS = 'html,body{background:#fff!important}svg[data-om-exportable-video-with-duration-secs]{box-shadow:none!important}' +
    'div:has(> div > svg[data-om-exportable-video-with-duration-secs]){background:#fff!important}' +
    'div:has(> div > svg[data-om-exportable-video-with-duration-secs]) > :last-child{display:none!important}[data-om-unknown-cues]{display:none!important}';
  const anims = {};
  $$('.anim-box').forEach(box => {
    const W = +box.dataset.w, H = +box.dataset.h, TOP = +box.dataset.top || 0, CROP = +box.dataset.crop || 0;
    const visH = H + TOP - CROP;
    const scaler = $('.anim-scaler', box), bar = $('.anim-progress', box);
    scaler.style.width = W + 'px'; scaler.style.height = visH + 'px';
    const fit = () => { const s = box.clientWidth / W; scaler.style.transform = `scale(${s})`; box.style.height = (visH * s) + 'px'; };
    fit(); window.addEventListener('resize', fit);
    const A = { box, t: 0, dur: 0, svg: null, visible: false, playing: false, last: null, iframe: null };
    anims[box.dataset.anim] = A;
    const load = () => {
      if (A.iframe) return;
      const f = h('iframe', { src: box.dataset.src, title: box.dataset.anim + ' animation', loading: 'lazy',
        style: `top:${TOP}px;width:${W}px;height:${H}px` });
      scaler.append(f); A.iframe = f;
      const poll = setInterval(() => {
        let doc; try { doc = f.contentDocument; } catch (e) { clearInterval(poll); return; }   // cross-origin: own player
        const svg = doc && doc.querySelector('svg[data-om-exportable-video-with-duration-secs]');
        if (!svg) return;
        clearInterval(poll);
        if (!doc.getElementById('rt-embed-css')) { const st = doc.createElement('style'); st.id = 'rt-embed-css'; st.textContent = EMBED_CSS; doc.head.appendChild(st); }
        A.svg = svg; A.dur = +svg.getAttribute('data-om-exportable-video-with-duration-secs') || 0;
        A.t = 0; A.playing = A.visible; seek(A);
      }, 150);
    };
    new IntersectionObserver(es => es.forEach(e => {
      if (e.isIntersecting) load();
      A.visible = e.intersectionRatio > 0.35;
      if (A.svg) { if (A.visible && A.t < A.dur) A.playing = true; else A.playing = false; }
    }), { threshold: [0, 0.35], rootMargin: '300px 0px' }).observe(box);
  });
  function seek(A) {
    if (!A.svg) return;
    A.svg.dispatchEvent(new CustomEvent('data-om-seek-to-time-frame', { detail: { time: A.t, playing: A.playing } }));
    $('.anim-progress', A.box).style.width = (A.dur ? 100 * A.t / A.dur : 0) + '%';
  }
  const animLoop = now => {
    requestAnimationFrame(animLoop);
    for (const A of Object.values(anims)) {
      const dt = A.last == null ? 0 : Math.min(0.1, (now - A.last) / 1000); A.last = now;
      if (!A.svg || !A.playing) continue;
      A.t = Math.min(A.dur, A.t + dt);
      if (A.t >= A.dur) A.playing = false;
      seek(A);
    }
  };
  requestAnimationFrame(animLoop);
  $$('[data-replay]').forEach(b => b.addEventListener('click', () => {
    const A = anims[b.dataset.replay]; if (!A) return;
    if (A.svg) { A.t = 0; A.playing = true; seek(A); }
    else if (A.iframe) { A.iframe.src = A.iframe.src; }
  }));

  /* ---------------- speed tags in the teaser ---------------- */
  $$('.teaser .vid').forEach(v => {
    const src = $('video', v).getAttribute('src'); const vv = V.find(x => Object.values(x.out).some(o => o.src === src));
    if (vv) $('.speed-tag', v).textContent = '×' + vv.speed + ' speed';
  });

  /* ---------------- decision game ---------------- */
  const KOPTS = [
    { k: 'none', t: '<b>No correction.</b> Keep executing the current plan.' },
    { k: 'U', t: '<b>Correct now (urgent).</b> Insert the correction at the front of the remaining plan.' },
    { k: 'D', t: '<b>Correct later (deferred).</b> Insert it after a pending action or at the end.' }];
  const GOPTS = [
    { k: 'none', t: '<b>No correction.</b> The planned cooking cycle handles it.' },
    { k: 'U', t: '<b>Serve now (urgent).</b> Take it to the plate before the lid closes again.' },
    { k: 'D', t: '<b>Serve later (deferred).</b> Leave it for the scheduled cooking cycle, serve afterwards.' }];
  const G2OPTS = [
    { k: 'UU', t: '<b>Both now.</b> Serve both meats before the lid closes again.' },
    { k: 'UD', t: '<b>Cooked now, raw later.</b> Serve the cooked meat first; the raw one after the cycle.' },
    { k: 'DD', t: '<b>Both later.</b> Leave both for the scheduled cycle.' },
    { k: 'none', t: '<b>No correction.</b>' }];
  const GAME = [
    { id: 'K1', disc: 'The robot opens the box to put the mugs in. Inside lies a <b>phone</b>, right where the mugs will be placed.', opts: KOPTS, ans: 'U',
      why: 'The phone is not part of the task, but it occupies a placement area that pending actions need. <b>IF</b> triggers on the obstruction, and it must be cleared before the next mug enters the box: <b>urgent</b>.' },
    { id: 'K2', disc: 'The box opens to reveal a <b>phone</b> in its far half, away from where the mugs will be placed.', opts: KOPTS, ans: 'none',
      why: 'The phone is irrelevant to the task and blocks no pending placement, so <b>IF</b> finds nothing to correct and the planner is not called.' },
    { id: 'K3', disc: 'Opening the box reveals a <b>grocery</b> lying where the mugs will be placed.', opts: KOPTS, ans: 'U',
      why: 'The grocery belongs in the cupboard, so it needs actions; it also obstructs the mug placements, so it must leave the box first: <b>urgent</b>.' },
    { id: 'K4', disc: 'Opening the box reveals a <b>grocery</b> in its far half, clear of where the mugs will go.', opts: KOPTS, ans: 'D',
      why: 'The grocery still has to reach the cupboard, but nothing waits on it: the correction can be <b>deferred</b> and appended to the plan.' },
    { id: 'G1', disc: 'The robot opens the grill to cook the raw meat. Inside are <b>two already cooked meats</b>.', opts: GOPTS, ans: 'U',
      why: 'If they stay inside when the lid closes for the raw meat\'s cycle, they are cooked again. They must be served before the next close: <b>urgent</b>.' },
    { id: 'G2', disc: 'Opening the grill reveals <b>one cooked meat and one raw meat</b>.', opts: G2OPTS, ans: 'UD',
      why: 'The cooked meat must leave before the next close (<b>urgent</b>); the raw meat needs that cycle, so it is served only after the lid reopens (<b>deferred</b>).' },
    { id: 'G3', disc: 'Opening the grill reveals <b>two raw meats</b>.', opts: GOPTS, ans: 'D',
      why: 'They still need cooking, and the cycle already scheduled for the visible raw meat cooks them too. Serving them before it ends would serve them raw: <b>deferred</b>.' }];
  const game = { i: 0, score: 0, answered: [] };
  const gameRender = () => {
    const g = GAME[game.i], v = V[vIndex(g.id)];
    const sc = $('#game-scene'); sc.classList.remove('revealed');
    $('img.before', sc).src = v.first; $('img.after', sc).src = v.last; $('.vlabel', sc).textContent = v.id + ' · ' + (v.domain === 'kitchen' ? 'kitchen' : 'grill');
    $('#game-imgnote').textContent = 'Initial scene. Answering reveals the final state of ROBUST-TAMP\'s run.';
    $('#game-step').textContent = `Discovery ${game.i + 1} of ${GAME.length}`;
    $('#game-disc').innerHTML = g.disc;
    $('#game-ask').textContent = 'What should the planner do?';
    const box = $('#game-opts'); box.innerHTML = '';
    g.opts.forEach(o => box.append(h('button', { class: 'opt', html: o.t, onclick: () => gameAnswer(o.k) })));
    const fb = $('#game-fb'); fb.className = 'feedback'; fb.innerHTML = '';
    $('#game-next').disabled = true; $('#game-watch').disabled = true;
    $('#game-next').textContent = game.i === GAME.length - 1 ? 'START OVER' : 'NEXT';
    gameDots();
  };
  const gameDots = () => {
    const d = $('#game-dots'); d.innerHTML = '';
    GAME.forEach((_, j) => d.append(h('i', { class: j === game.i && game.answered[j] == null ? 'cur' : (game.answered[j] == null ? '' : (game.answered[j] ? 'ok' : 'bad')) })));
    $('#game-score').textContent = `Score ${game.score} / ${game.answered.filter(x => x != null).length}`;
  };
  const gameAnswer = k => {
    const g = GAME[game.i], v = V[vIndex(g.id)], ok = k === g.ans;
    if (game.answered[game.i] != null) return;
    game.answered[game.i] = ok; if (ok) game.score++;
    $$('#game-opts .opt').forEach((b, j) => {
      b.disabled = true; const key = g.opts[j].k;
      if (key === g.ans) b.classList.add('correct'); else if (key === k) b.classList.add('wrong');
    });
    $('#game-scene').classList.add('revealed');
    $('#game-imgnote').textContent = 'Final state of ROBUST-TAMP\'s best trial on ' + v.id + '.';
    const m = v.main;
    const fb = $('#game-fb');
    fb.style.setProperty('--c', ok ? 'var(--ok)' : 'var(--bad)');
    fb.innerHTML = `<b>${ok ? 'Correct.' : 'Not quite.'}</b> ${g.why}<div class="stats-line">ROBUST-TAMP on ${v.id}: ${m.sr.toFixed(1)}% success over 10 trials` +
      (m.urg != null ? `; ${m.urg.toFixed(1)}% of trigger objects given the right urgency on the first attempt (validation and re-queries recover the rest).` : '.') + '</div>';
    fb.classList.add('show');
    $('#game-next').disabled = false; $('#game-watch').disabled = false;
    if (game.i === GAME.length - 1) fb.innerHTML += `<div class="stats-line"><b>You matched ${game.score} of ${GAME.length} decisions.</b></div>`;
    gameDots();
  };
  $('#game-next').addEventListener('click', () => {
    if (game.i === GAME.length - 1) { game.i = 0; game.score = 0; game.answered = []; } else game.i++;
    gameRender();
  });
  $('#game-watch').addEventListener('click', () => { cmp.select(vIndex(GAME[game.i].id), true); $('#comparison').scrollIntoView(); });

  /* ---------------- variant catalogue ---------------- */
  const yn = b => b == null ? '–' : (b ? '✓' : '✗');
  const expTag = e => e === 'U' ? h('span', { class: 'tg u' }, 'urgent') : e === 'D' ? h('span', { class: 'tg d' }, 'deferred')
    : e === 'U/D' ? [h('span', { class: 'tg u' }, 'urgent'), h('span', { class: 'tg d' }, 'deferred')] : h('span', { class: 'tg n' }, 'no correction');
  const vcat = $('#vcat');
  [['kitchen', 'Kitchen', 'groceries to the cupboard, mugs into the lidded box · zero-shot prompts'],
   ['grill', 'Grill', 'cook raw meat, serve cooked meat on the plate · in-context examples']].forEach(([dom, name, sub]) => {
    vcat.append(h('div', { class: 'domain-hd' }, h('h3', {}, name), h('span', {}, sub)));
    const grid = h('div', { class: 'vgrid' });
    V.filter(v => v.domain === dom).forEach(v => grid.append(h('div', { class: 'vcard reveal', onclick: () => { cmp.select(vIndex(v.id), true); $('#comparison').scrollIntoView(); } },
      h('div', { class: 'img' }, h('img', { src: v.first, alt: v.id + ' initial scene', loading: 'lazy' }),
        h('img', { class: 'last', src: v.last, alt: v.id + ' final scene', loading: 'lazy' }), h('span', { class: 'hint' }, 'final state')),
      h('div', { class: 'body' }, h('div', {}, h('span', { class: 'vid' }, v.id), h('span', { class: 'grp' }, v.group)),
        h('div', { class: 'desc' }, v.desc),
        h('div', { class: 'tags' }, v.hidden === 'None' ? h('span', { class: 'tg n' }, 'nothing hidden')
          : [h('span', { class: 'tg' }, 'relevant ' + yn(v.rel)), h('span', { class: 'tg' }, 'overlap ' + yn(v.ovl)), expTag(v.exp)])))));
    vcat.append(grid);
  });

  /* ---------------- comparison player ---------------- */
  const cmp = (() => {
    const grid = $('#cmp-grid'), chipsBox = $('#vchips');
    const st = { i: 0, playing: false, inView: false, auto: true, rate: 1, ended: 0, timer: null, seen: new Set(), busy: false };
    const tiles = M.map(m => {
      const video = h('video', { muted: true, playsinline: true, preload: 'auto' }); video.muted = true;
      const reel = h('div', { class: 'reel' }, video);
      const okv = h('div', { class: 'verdict okv' }, 'Success');
      const badv = h('div', { class: 'verdict badv' }, h('b', {}, 'Failure'), h('span', {}, ''));
      const spd = h('span', { class: 'speed-tag' }, '');
      const screen = h('div', { class: 'screen' }, reel, h('div', { class: 'tint' }), okv, badv, spd);
      const el = h('div', { class: 'tile' }, h('div', { class: 'tname' }, h('i', { style: `background:${m.color}` }), m.name), screen);
      grid.append(el);
      const T = { m, el, video, reel, okv, badv, spd };
      video.addEventListener('ended', () => finish(T));
      return T;
    });
    const info = { k: h('span', {}, ''), cnt: h('span', {}, ''), v: h('div', { class: 'iv' }, ''), d: h('div', { class: 'idesc' }, ''),
      r: h('div', { class: 'ires' }), bar: h('div') };
    grid.append(h('div', { class: 'infocard' }, h('div', { class: 'ik' }, info.k, info.cnt), info.v, info.d, h('div', { class: 'progress' }, info.bar), info.r));
    // chips
    const chips = [];
    [['kitchen', 'Kitchen'], ['grill', 'Grill']].forEach(([dom, name], gi) => {
      if (gi) chipsBox.append(h('span', { class: 'sep' }));
      chipsBox.append(h('span', { class: 'grp-lab' }, name));
      V.forEach((v, i) => { if (v.domain !== dom) return;
        const mini = h('span', { class: 'mini' });
        const c = h('button', { class: 'vchip', title: v.desc, onclick: () => select(i, true) }, v.id, mini);
        chips[i] = { c, mini }; chipsBox.append(c); });
    });
    const markSeen = i => {
      if (st.seen.has(i)) return; st.seen.add(i);
      chips[i].mini.innerHTML = ''; M.forEach(m => chips[i].mini.append(h('i', { style: `background:${V[i].out[m.key].ok ? '#2e9e4f' : '#d64545'}` })));
    };
    const setPlayIcon = () => { $('#cmp-play').innerHTML = st.playing
      ? '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>'; };
    const fillInfo = v => {
      info.k.textContent = (v.domain === 'kitchen' ? 'Kitchen' : 'Grill') + ' variant';
      const dv = V.filter(x => x.domain === v.domain); info.cnt.textContent = (dv.indexOf(v) + 1) + ' / ' + dv.length;
      info.v.textContent = v.id; info.d.textContent = v.desc; info.r.innerHTML = ''; info.bar.style.width = '0';
    };
    function apply(i) {
      const v = V[i];
      tiles.forEach(T => {
        const o = v.out[T.m.key];
        T.el.classList.remove('done', 'ok', 'bad');
        T.video.src = o.src; T.video.poster = o.poster; T.video.playbackRate = st.rate; T.video.load();
        T.spd.textContent = '×' + v.speed + ' speed';
        T.badv.lastChild.textContent = (o.why || []).join('\n');
      });
      chips.forEach((c, j) => c && c.c.classList.toggle('on', j === i));
      $$('#scoreboard td.c').forEach(td => td.classList.toggle('cur', +td.dataset.v === i));
      fillInfo(v); st.ended = 0;
    }
    function select(i, user) {
      clearTimeout(st.timer);
      if (i === st.i && !user) return;
      const go = () => { st.i = i; apply(i); if (user) st.playing = true; setPlayIcon(); if (st.playing && st.inView) playAll(); };
      if (reduced || !tiles[0].video.src) { go(); return; }
      st.busy = true;
      tiles.forEach((T, k) => setTimeout(() => { T.reel.classList.remove('in'); T.reel.classList.add('out'); }, k * 70));
      setTimeout(() => {
        go();
        tiles.forEach((T, k) => setTimeout(() => { T.reel.classList.remove('out'); void T.reel.offsetWidth; T.reel.classList.add('in'); }, k * 70));
        st.busy = false;
      }, 450 + 4 * 70);
    }
    function playAll() {
      tiles.forEach(T => { T.video.playbackRate = st.rate; const p = T.video.play(); if (p) p.catch(() => {}); });
    }
    function pauseAll() { tiles.forEach(T => T.video.pause()); }
    function finish(T) {
      const o = V[st.i].out[T.m.key];
      T.el.classList.add('done', o.ok ? 'ok' : 'bad');
      st.ended++;
      if (st.ended === tiles.length) {
        const n = M.filter(m => V[st.i].out[m.key].ok).length;
        info.r.innerHTML = ''; info.r.append(h('i', { style: `background:${n ? '#1f7a35' : '#c62828'}` }), `${n} of ${M.length} methods succeeded`);
        markSeen(st.i);
        if (st.auto && st.inView && st.playing) st.timer = setTimeout(() => select((st.i + 1) % V.length, false), 3600);
      }
    }
    // progress bar
    (function tick() { requestAnimationFrame(tick); const v = tiles[0].video; if (v.duration) info.bar.style.width = (100 * v.currentTime / v.duration) + '%'; })();
    // keep the five clips in step
    tiles[0].video.addEventListener('timeupdate', () => {
      const t0 = tiles[0].video.currentTime;
      tiles.slice(1).forEach(T => { if (!T.video.ended && Math.abs(T.video.currentTime - t0) > 0.2) T.video.currentTime = t0; });
    });
    $('#cmp-play').addEventListener('click', () => {
      st.playing = !st.playing; setPlayIcon();
      if (st.playing) { if (st.ended === tiles.length) { replay(); return; } playAll(); } else { pauseAll(); clearTimeout(st.timer); }
    });
    const replay = () => { clearTimeout(st.timer); apply(st.i); st.playing = true; setPlayIcon(); playAll(); };
    $('#cmp-replay').addEventListener('click', replay);
    $('#cmp-prev').addEventListener('click', () => select((st.i - 1 + V.length) % V.length, true));
    $('#cmp-next').addEventListener('click', () => select((st.i + 1) % V.length, true));
    $('#cmp-speed').addEventListener('change', e => { st.rate = +e.target.value; tiles.forEach(T => T.video.playbackRate = st.rate); });
    $('#cmp-auto').addEventListener('change', e => { st.auto = e.target.checked; if (!st.auto) clearTimeout(st.timer);
      else if (st.ended === tiles.length && st.playing) st.timer = setTimeout(() => select((st.i + 1) % V.length, false), 1500); });
    new IntersectionObserver(es => es.forEach(e => {
      st.inView = e.isIntersecting;
      if (st.inView) { if (!st.started) { st.started = true; st.playing = true; setPlayIcon(); } if (st.playing && st.ended < tiles.length) playAll(); }
      else { pauseAll(); clearTimeout(st.timer); }
    }), { threshold: 0.25 }).observe(grid);
    apply(0); setPlayIcon();
    return { select };
  })();

  /* ---------------- scoreboard ---------------- */
  (function () {
    const t = $('#scoreboard');
    const nK = V.filter(v => v.domain === 'kitchen').length;
    const hr1 = h('tr', {}, h('th', {}), h('th', { class: 'grp', colspan: nK, style: '--c:#2e7d9a' }, 'Kitchen · zero-shot'), h('th', { class: 'gap' }),
      h('th', { class: 'grp', colspan: V.length - nK, style: '--c:#c8642b' }, 'Grill · ICL'), h('th', {}));
    const hr2 = h('tr', {}, h('th', {}), V.map((v, i) => [i === nK ? h('th', { class: 'gap' }) : null, h('th', {}, v.id)]), h('th', {}, 'Total'));
    t.append(h('thead', {}, hr1, hr2));
    const tb = h('tbody');
    M.forEach((m, mi) => {
      const n = V.filter(v => v.out[m.key].ok).length;
      tb.append(h('tr', { class: mi === 0 ? 'ours' : '' }, h('td', { class: 'm' }, h('i', { style: `background:${m.color}` }), m.name),
        V.map((v, i) => { const o = v.out[m.key];
          return [i === nK ? h('td', { class: 'gap' }) : null,
            h('td', { class: 'c ' + (o.ok ? 'ok' : 'bad') + (i === 0 ? ' cur' : ''), 'data-v': i, title: o.ok ? `${m.name} · ${v.id}: success` : `${m.name} · ${v.id}: ${o.why.join('; ')}`,
              onclick: () => { cmp.select(i, true); $('#comparison').scrollIntoView(); } }, o.ok ? '✓' : '✕')]; }),
        h('td', { class: 'tot' }, String(n), h('small', {}, ' / ' + V.length))));
    });
    t.append(tb);
  })();

  /* ---------------- results: tables ---------------- */
  const table = (el, head, rows) => {
    const t = $(el); t.innerHTML = '';
    t.append(h('thead', {}, head.map(r => h('tr', {}, r.map(c => typeof c === 'string' ? h('th', {}, c) : h('th', c.a || {}, c.t))))));
    t.append(h('tbody', {}, rows.map(r => h('tr', r.a || {}, r.c.map(c => typeof c === 'object' && c !== null && !c.nodeType ? h('td', c.a || {}, c.t) : h('td', {}, c == null ? '–' : String(c)))))));
  };
  const L = (t, extra = '') => ({ t, a: { class: 'l ' + extra } });
  const B = t => ({ t, a: { class: 'best' } });
  // baselines
  const BL = [['VLM-TAMP', 23.3, [6.0, 17.1, 71.4, 2.1, 77, 31.8, 176], [10.0, 18.6, 71.9, 2.1, 85, 35.9, 183]],
              ['OWL-TAMP', 17.8, [2.0, 12.1, 49.1, 6.3, 730, 115.3, 790], [8.0, 14.3, 53.3, 6.4, 740, 114.6, 803]],
              ['Inner Monologue', 64.4, [6.0, 43.6, 76.5, 14.4, 956, 62.3, 1114], [10.0, 45.0, 76.8, 15.0, 1047, 68.4, 1240]],
              ['EPoG†', 44.4, [0.0, 28.6, 48.9, 5.1, 159, 25.4, 216], [0.0, 28.6, 48.8, 5.1, 159, 25.5, 216]],
              ['ROBUST-TAMP (ours)', 94.4, [22.0, 68.6, 86.5, 5.1, 540, 103.4, 643], [88.0, 92.1, 97.8, 3.8, 355, 91.6, 449]]];
  const fmt = (x, i) => [1, 1, 1, 1, 0, 1, 0][i - 1] ? x.toFixed(1) : String(x);   // SR_G SR PGC Calls Plan. Lat. Time
  table('#tbl-baselines', [[{ t: '', a: { class: 'l' } }, { t: 'Success (%) ↑', a: { class: 'span', colspan: 4 } }, { t: 'Cost ↓', a: { class: 'span', colspan: 4 } }],
    [L('Method'), 'SR_K', 'SR_G', 'SR', 'PGC', 'Calls', 'Plan.', 'Lat.', 'Time']],
    BL.flatMap(([n, k, zs, icl], i) => { const ours = i === BL.length - 1;
      return [{ a: { class: ours ? 'ours' : '' }, c: [L(ours ? h('b', {}, n) : n), ours ? B(k.toFixed(1)) : k.toFixed(1), ...zs.map((x, j) => fmt(x, j + 1))] },
              { a: { class: 'sub' + (ours ? ' ours' : '') }, c: [L('+ ICL'), { t: '', a: {} }, ...icl.map((x, j) => ours && j < 3 ? B(fmt(x, j + 1)) : fmt(x, j + 1))] }]; }));
  $$('#tbl-baselines th').forEach(th => { th.innerHTML = th.innerHTML.replace('SR_K', 'SR<sub>K</sub>').replace('SR_G', 'SR<sub>G</sub>'); });
  // per-variant
  const GROUPS = [['A. Basic', ['K0', 'G0']], ['B. Core', ['K1', 'K2', 'K3', 'K4', 'G1', 'G2', 'G3']], ['C. Cardinality', ['K3-n2', 'K3-n3', 'G1-n1', 'K1-w1', 'K1-w2']]];
  const n1 = x => x == null ? '–' : x.toFixed(1), n0 = x => x == null ? '–' : String(x);
  const mainRows = [];
  GROUPS.forEach(([g, ids]) => {
    mainRows.push({ a: { class: 'grp' }, c: [{ t: g, a: { colspan: 13 } }] });
    ids.forEach(id => { const v = V[vIndex(id)], m = v.main;
      mainRows.push({ c: [L(h('b', {}, id)), L(v.hidden), yn(v.rel), yn(v.ovl), v.exp, '100.0', n1(m.sr), n1(m.pgc), n1(m.calls), n0(m.plan), n0(m.idle), n0(m.time), n1(m.urg)] }); });
  });
  [['Mean (kitchen)', [100.0, 94.4, 97.7, 4.5, 418, 144, 517, 49.0]], ['Mean (grill)', [100.0, 88.0, 98.1, 2.4, 242, 134, 329, 72.9]],
   ['Mean (all)', [100.0, 92.1, 97.8, 3.8, 355, 141, 449, 58.8]]].forEach(([n, r], k) =>
    mainRows.push({ a: { class: k === 0 ? 'mean' : '' }, c: [{ t: k === 2 ? h('b', {}, n) : n, a: { class: 'l', colspan: 5 } },
      ...r.map((x, j) => { const s = [3, 4, 5, 6].includes(j) && j !== 3 ? n0(x) : n1(x); return k === 2 ? B(j === 3 ? n1(x) : s) : (j === 3 ? n1(x) : s); })] }));
  table('#tbl-main', [[L('ID'), L('Hidden'), 'Rel.', 'Ovl.', 'Exp.', 'Ceil.', 'SR', 'PGC', 'Calls', 'Plan.', 'Idle', 'Time', 'Urg.']], mainRows);
  // ablations
  const AB = [['Full system', [95.0, 4.2, 118, 377, 457], [86.7, 2.7, 135, 281, 373]], ['−Memory', [85.0, 4.0, 131, 342, 420], [60.0, 2.6, 175, 343, 435]],
              ['−IF', [95.0, 5.5, 199, 441, 511], [76.7, 2.8, 171, 317, 408]], ['−WHERE', [75.0, 3.9, 76, 348, 434], [56.7, 4.5, 221, 546, 648]],
              ['Fixed front', [90.0, 4.0, 116, 394, 473], [30.0, 6.1, 185, 821, 916]], ['Fixed end', [52.5, 6.5, 438, 562, 609], [30.0, 2.5, 188, 320, 410]],
              ['−WHEN', [92.5, 4.5, 127, 399, 483], [66.7, 2.5, 147, 274, 375]], ['LLM planner', [87.5, 5.2, 65, 205, 286], [23.3, 9.2, 288, 375, 426]]];
  const abf = r => [r[0].toFixed(1), r[1].toFixed(1), String(r[2]), String(r[3]), String(r[4])];
  table('#tbl-abl', [[{ t: '', a: { class: 'l' } }, { t: 'Kitchen (K1–K4, zero-shot)', a: { class: 'span', colspan: 5 } }, { t: 'Grill (G1–G3, ICL)', a: { class: 'span', colspan: 5 } }],
    [L('Condition'), 'SR', 'Calls', 'Idle', 'Plan.', 'Time', 'SR', 'Calls', 'Idle', 'Plan.', 'Time']],
    AB.map(([n, k, g], i) => ({ a: { class: i === 0 ? 'ours' : '' }, c: [L(i === 0 ? h('b', {}, n) : n), ...abf(k).map((x, j) => i === 0 && j === 0 ? B(x) : x), ...abf(g).map((x, j) => i === 0 && j === 0 ? B(x) : x)] })));
  // planner tables
  const PA = [['4B', 'LLM', 'ZS', [14.4, 0.0, 9.3, 18.0, 41.5, 26.4, 242]], ['', '', 'ICL', [14.4, 14.0, 14.3, 18.0, 54.5, 31.1, 206]],
              ['', 'VLM', 'ZS', [53.3, 6.0, 36.4, 55.5, 43.8, 51.3, 736]], ['', '', 'ICL', [53.3, 70.0, 59.3, 55.5, 90.1, 67.9, 560]],
              ['8B', 'LLM', 'ZS', [81.1, 4.0, 53.6, 83.9, 40.3, 68.3, 327]], ['', '', 'ICL', [81.1, 34.0, 64.3, 83.9, 58.2, 74.7, 257]],
              ['', 'VLM', 'ZS', [94.4, 22.0, 68.6, 97.7, 66.3, 86.5, 540]], ['', '', 'ICL', [94.4, 88.0, 92.1, 97.7, 98.1, 97.8, 355]],
              ['32B', 'LLM', 'ZS', [91.1, 18.0, 65.0, 93.0, 69.4, 84.6, 390]], ['', '', 'ICL', [91.1, 66.0, 82.1, 93.0, 92.9, 93.0, 185]],
              ['', 'VLM', 'ZS', [91.1, 30.0, 69.3, 93.9, 76.4, 87.7, 1107]], ['', '', 'ICL', [91.1, 82.0, 87.9, 93.9, 96.0, 94.7, 603]]];
  table('#tbl-plannerA', [[{ t: '(a) Scale, modality, prompting', a: { class: 'l', colspan: 3 } }, { t: 'SR', a: { class: 'span', colspan: 3 } }, { t: 'PGC', a: { class: 'span', colspan: 3 } }, ''],
    [L('Scale'), L('Mod.'), L('Prompt'), 'K', 'G', 'All', 'K', 'G', 'All', 'Plan.']],
    PA.map(([s, mo, p, r], i) => ({ a: { class: i === 7 ? 'ours' : '' }, c: [L(h('b', {}, s)), L(mo), L(p), ...r.map((x, j) => {
      const txt = j === 6 ? String(x) : x.toFixed(1);
      if (p === 'ICL' && (j === 0 || j === 3)) return { t: txt, a: { class: 'gray' } };
      return i === 7 ? B(txt) : txt; })] })));
  const PB = [['VLM', '–', 'Qwen3-VL-8B-Instruct', [1.1, 2.0, 1.4, 2.9, 24.5, 10.6, 168]], ['', '', 'Ministral-3-8B-Instruct', [16.7, 2.0, 11.4, 54.2, 52.7, 53.7, 47]],
              ['', '', 'InternVL3.5-8B', [18.9, 0.0, 12.1, 28.1, 20.1, 25.2, 111]], ['', '✓', 'Qwen3-VL-8B-Thinking', [94.4, 22.0, 68.6, 97.7, 66.3, 86.5, 540]],
              ['', '', 'Ministral-3-8B-Reasoning', [48.9, 70.0, 56.4, 51.9, 89.1, 65.1, 468]], ['', '', 'Holo2-8B', [31.1, 2.0, 20.7, 41.7, 37.7, 40.2, 135]],
              ['LLM', '–', 'Qwen3-8B (no think)', [1.1, 6.0, 2.9, 4.6, 28.3, 13.1, 25]], ['', '', 'Llama-3.1-8B-Instruct', [6.7, 0.0, 4.3, 12.2, 18.7, 14.5, 124]],
              ['', '', 'Qwen2.5-7B-Instruct', [0.0, 0.0, 0.0, 2.8, 12.6, 6.3, 10]], ['', '✓', 'Qwen3-8B (think)', [81.1, 4.0, 53.6, 83.9, 40.3, 68.3, 327]],
              ['', '', 'R1-Distill-Llama-8B', [0.0, 0.0, 0.0, 1.9, 12.6, 5.7, 500]], ['', '', 'R1-Distill-Qwen-7B', [0.0, 0.0, 0.0, 2.5, 20.1, 8.8, 597]]];
  table('#tbl-plannerB', [[{ t: '(b) 8B-class models, zero-shot', a: { class: 'l', colspan: 3 } }, { t: 'SR', a: { class: 'span', colspan: 3 } }, { t: 'PGC', a: { class: 'span', colspan: 3 } }, ''],
    [L('Mod.'), L('Reas.'), L('Model'), 'K', 'G', 'All', 'K', 'G', 'All', 'Plan.']],
    PB.map(([mo, r, n, v], i) => ({ a: { class: i === 3 ? 'ours' : '' }, c: [L(h('b', {}, mo)), L(r), L(i === 3 ? h('b', {}, n) : n), ...v.map((x, j) => { const txt = j === 6 ? String(x) : x.toFixed(1); return i === 3 ? B(txt) : txt; })] })));

  /* ---------------- results: charts ---------------- */
  const SR = [['ROBUST-TAMP', 68.6, 92.1, '#2E7D9A'], ['Inner Monologue', 43.6, 45.0, '#C8642B'], ['EPoG', 28.6, 28.6, '#A07A2C'],
              ['VLM-TAMP', 17.1, 18.6, '#8E4F86'], ['OWL-TAMP', 12.1, 14.3, '#3F8A5C']];
  const srBox = $('#sr-bars');
  SR.forEach(([n, zs, icl, c]) => {
    const fill = h('div', { class: 'bar-fill', style: `background:${c}`, 'data-w': icl }, h('div', { class: 'zs', style: `width:${100 * zs / icl}%` }));
    srBox.append(h('div', { class: 'bar-row' }, h('div', { class: 'bl' }, h('i', { style: `background:${c}` }), n), h('div', { class: 'bar-track' }, fill),
      h('div', { class: 'bv' }, icl.toFixed(1) + '%')));
  });
  const FC = [['Plan check'], ['Pick without place', 74, 68], ['Inserted too late', 53, 47], ['Unreadable plan', 46, 43], ['Plan repeated', 6, 5],
              ['Execution'], ['Place / grasp failed', 54, 50], ['Lid blocked / closed', 16, 16], ['No motion plan', 8, 4]];
  const fb = $('#fail-bars');
  FC.forEach(r => {
    if (r.length === 1) { fb.append(h('div', { class: 'game-kicker', style: 'margin-top:6px' }, r[0])); return; }
    const [n, tot, comp] = r;
    const track = h('div', { class: 'bar-track', style: 'background:transparent' },
      h('div', { class: 'bar-fill', style: 'display:flex;background:transparent', 'data-w': 100 * tot / 74 },
        h('div', { style: `width:${100 * comp / tot}%;background:#2b78d4;border-radius:6px 0 0 6px` }), h('div', { style: `flex:1;background:#ef6a32;border-radius:0 6px 6px 0` })));
    fb.append(h('div', { class: 'bar-row' }, h('div', { class: 'bl', style: 'font-weight:500;font-size:14.5px;font-family:var(--font)' }, n), track, h('div', { class: 'bv' }, String(tot))));
  });
  const barObs = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return; barObs.unobserve(e.target);
    $$('.bar-fill', e.target).forEach((b, i) => setTimeout(() => { b.style.width = b.dataset.w + '%'; }, i * 90));
  }), { threshold: 0.3 });
  [srBox, fb].forEach(b => barObs.observe(b));

  // dumbbell: zero-shot -> ICL success per Qwen3 planner
  const FA = [['Qwen3-4B', 9.3, 14.3, '242 → 206 s'], ['Qwen3-VL-4B', 36.4, 59.3, '736 → 560 s'], ['Qwen3-8B', 53.6, 64.3, '327 → 257 s'],
              ['Qwen3-VL-8B', 68.6, 92.1, '540 → 355 s', 1], ['Qwen3-32B', 65.0, 82.1, '390 → 185 s'], ['Qwen3-VL-32B', 69.3, 87.9, '1107 → 603 s']];
  const svg = $('#dumbbell'), NS = 'http://www.w3.org/2000/svg';
  const s = (tag, a, txt) => { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (txt != null) e.textContent = txt; return e; };
  const X0 = 130, XW = 300, Y0 = 46, RS = 54, x = v => X0 + XW * v / 100;
  [0, 25, 50, 75, 100].forEach(v => { svg.append(s('line', { x1: x(v), x2: x(v), y1: 30, y2: Y0 + RS * 6 - 14, stroke: '#ededea' }));
    svg.append(s('text', { x: x(v), y: Y0 + RS * 6 + 6, 'text-anchor': 'middle', 'font-size': 12, fill: '#72757b' }, v)); });
  svg.append(s('text', { x: x(50), y: Y0 + RS * 6 + 28, 'text-anchor': 'middle', 'font-size': 12.5, fill: '#35373b' }, 'Task success (%), all 14 variants'));
  svg.append(s('text', { x: 548, y: 22, 'text-anchor': 'end', 'font-size': 12, fill: '#72757b' }, 'planning time'));
  const dbs = [];
  FA.forEach(([n, zs, icl, tm, hi], i) => {
    const y = Y0 + i * RS;
    if (hi) svg.append(s('rect', { x: 0, y: y - 22, width: 560, height: 44, fill: '#eef6f9', rx: 8 }));
    svg.append(s('text', { x: 10, y: y + 5, 'font-size': 14, 'font-weight': hi ? 700 : 500, fill: '#17181a' }, n));
    const line = s('line', { x1: x(zs), x2: x(zs), y1: y, y2: y, stroke: '#2e7d9a', 'stroke-width': 4, 'stroke-linecap': 'round' });
    const c0 = s('circle', { cx: x(zs), cy: y, r: 7, fill: '#fff', stroke: '#9a9992', 'stroke-width': 2.5 });
    const c1 = s('circle', { cx: x(zs), cy: y, r: 8, fill: '#2e7d9a', opacity: 0 });
    const d = s('text', { x: x(icl) + 14, y: y + 5, 'font-size': 13, 'font-weight': 700, fill: '#2e7d9a', opacity: 0 }, '+' + Math.round(icl - zs));
    const tt = s('text', { x: 548, y: y + 5, 'text-anchor': 'end', 'font-size': 12.5, fill: '#72757b', opacity: 0 }, tm);
    svg.append(line, c0, c1, d, tt); dbs.push({ zs, icl, line, c1, d, tt });
  });
  svg.append(s('circle', { cx: 140, cy: 14, r: 6, fill: '#fff', stroke: '#9a9992', 'stroke-width': 2.5 }), s('text', { x: 152, y: 18, 'font-size': 12.5, fill: '#35373b' }, 'zero-shot'),
    s('circle', { cx: 240, cy: 14, r: 6.5, fill: '#2e7d9a' }), s('text', { x: 252, y: 18, 'font-size': 12.5, fill: '#35373b' }, 'with in-context examples'));
  new IntersectionObserver((es, o) => es.forEach(e => {
    if (!e.isIntersecting) return; o.disconnect();
    dbs.forEach((b, i) => {
      const t0 = performance.now() + i * 160;
      const step = now => { const p = Math.max(0, Math.min(1, (now - t0) / 900)), q = 1 - Math.pow(1 - p, 3), xv = x(b.zs + (b.icl - b.zs) * q);
        b.line.setAttribute('x2', xv); b.c1.setAttribute('cx', xv); b.c1.setAttribute('opacity', p > 0 ? 1 : 0);
        b.d.setAttribute('opacity', Math.max(0, (p - .7) / .3)); b.tt.setAttribute('opacity', Math.max(0, (p - .5) / .5));
        if (p < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step);
    });
  }), { threshold: 0.35 }).observe(svg);

  // donut: 85 replanned & completed, 44 no failure, 11 not completed (of 140)
  (function () {
    const dn = $('#donut'), R = 100, C = 2 * Math.PI * R, segs = [[85, '#2b78d4'], [44, '#d9d7d1'], [11, '#ef6a32']];
    const arcs = []; let acc = 0;
    segs.forEach(([v, c]) => { const a = s('circle', { cx: 130, cy: 130, r: R, fill: 'none', stroke: c, 'stroke-width': 36,
      'stroke-dasharray': `0 ${C}`, transform: `rotate(${-90 + acc / 140 * 360} 130 130)` }); dn.append(a); arcs.push([a, v]); acc += v; });
    const pct = s('text', { x: 130, y: 136, 'text-anchor': 'middle', 'font-size': 44, 'font-weight': 700, fill: '#17181a', style: 'font-family:Montserrat,sans-serif' }, '0%');
    dn.append(pct, s('text', { x: 130, y: 160, 'text-anchor': 'middle', 'font-size': 14, fill: '#72757b' }, 'completed'));
    new IntersectionObserver((es, o) => es.forEach(e => {
      if (!e.isIntersecting) return; o.disconnect();
      const t0 = performance.now();
      const step = now => { const p = Math.min(1, (now - t0) / 1600), q = 1 - Math.pow(1 - p, 3), P = q * 140; let a = 0;
        arcs.forEach(([el, v]) => { const dr = Math.max(0, Math.min(v, P - a)); el.setAttribute('stroke-dasharray', `${Math.max(0, dr / 140 * C - (dr > 0 ? 2 : 0))} ${C}`); a += v; });
        pct.textContent = Math.round((Math.min(P, 85) + Math.max(0, Math.min(P - 85, 44))) / 140 * 100) + '%';
        if (p < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step);
    }), { threshold: 0.4 }).observe(dn);
  })();

  /* ---------------- real-world settings ---------------- */
  [['No discovery', 'ordinary completion'], ['Task-relevant · overlapping', 'discovered item blocks a placement'],
   ['Task-relevant · non-overlapping', 'discovered item needs actions, blocks nothing'], ['Task-irrelevant · overlapping', 'unrelated item blocks a placement'],
   ['Task-irrelevant · non-overlapping', 'unrelated item, no correction']].forEach(([t, d], i) =>
    $('#settings').append(h('div', { class: 'setting' }, h('div', { class: 'n' }, 'SETTING ' + (i + 1)), h('div', { class: 't' }, t), h('div', { class: 's' }, d))));

  /* ---------------- bibtex ---------------- */
  $('#bibcopy').addEventListener('click', () => {
    const txt = $('#bibtext').textContent;
    (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(() => { $('#bibcopy').textContent = 'COPIED'; setTimeout(() => $('#bibcopy').textContent = 'COPY', 1500); }).catch(() => {});
  });

  gameRender();
  observeReveal(document);
})();
