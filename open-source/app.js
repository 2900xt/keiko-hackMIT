(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const feed = createFeed();
  const DATA_BASE = 'data/'; // the GitHub database, relative to this page
  const RANGE_M = 300;       // nominal hydrophone detection range for the ring
  const DAY = 86400000;
  const detections = []; // { d, t, live, tr, marker }
  let filter = 'all', sortKey = 'ts', sortDir = -1;

  // ---------- map ----------------------------------------------------------
  const map = L.map('map', { zoomControl: false }).setView([feed.buoy.lat, feed.buoy.lon], 15);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.control.scale({ position: 'bottomright', imperial: false }).addTo(map);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19, attribution: 'Tiles &copy; Esri &mdash; Maxar, Earthstar Geographics, and the GIS User Community',
  }).addTo(map);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19, pane: 'overlayPane',
  }).addTo(map);
  const range = L.circle([feed.buoy.lat, feed.buoy.lon], { radius: RANGE_M, color: '#fff', weight: 1.5, dashArray: '5 5', fillColor: '#fff', fillOpacity: 0.06, interactive: false }).addTo(map);
  const sightings = L.layerGroup().addTo(map);
  const marker = L.marker([feed.buoy.lat, feed.buoy.lon], {
    icon: L.divIcon({ className: '', html: '<div class="buoy"></div>', iconSize: [16, 16], iconAnchor: [8, 8] }), zIndexOffset: 1000,
  }).addTo(map).bindTooltip(feed.buoy.id, { permanent: true, direction: 'right', offset: [12, 0], className: 'buoy-label' });

  // ---------- buoy status --------------------------------------------------
  let last = 0;
  feed.on('telemetry', (t) => {
    last = Date.now();
    $('s-id').textContent = t.id;
    $('s-lat').textContent = t.lat.toFixed(5);
    $('s-lon').textContent = t.lon.toFixed(5);
    marker.setLatLng([t.lat, t.lon]); range.setLatLng([t.lat, t.lon]);
  });
  fetch(DATA_BASE + 'buoys.csv').then((r) => r.ok ? r.text() : Promise.reject(r.status)).then((txt) => {
    const [head, ...rows] = txt.trim().split('\n').map((l) => l.split(','));
    const row = rows.find((r) => r[head.indexOf('buoy_id')] === feed.buoy.id);
    if (!row) return;
    $('s-hydro').textContent = row[head.indexOf('hydrophone')] + ' · ' + (+row[head.indexOf('sample_rate_hz')] / 1000) + ' kHz';
    $('s-deployed').textContent = new Date(row[head.indexOf('deployed_utc')]).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  }).catch(() => { $('s-hydro').textContent = '—'; $('s-deployed').textContent = '—'; });

  const ago = (ms) => ms < 1500 ? 'just now' : ms < 60000 ? Math.round(ms / 1000) + ' s ago' : ms < 3600000 ? Math.round(ms / 60000) + ' min ago' : ms < DAY ? Math.round(ms / 3600000) + ' h ago' : Math.round(ms / DAY) + ' d ago';
  function tick() {
    const now = Date.now();
    $('clock').textContent = new Date(now).toLocaleTimeString();
    const age = now - last;
    const k = !last ? '' : age > 10000 ? 'off' : age > 5000 ? 'stale' : 'on';
    const word = !last ? 'connecting' : k === 'off' ? 'offline' : k === 'stale' ? 'stale' : 'online';
    $('s-state').textContent = word; $('s-state').className = 'state ' + k;
    $('live').className = 'live ' + k; $('live-text').textContent = k === 'on' ? 'Live' : word[0].toUpperCase() + word.slice(1);
    $('s-age').textContent = last ? 'updated ' + ago(age) : '';
    // last call
    const latest = detections.length ? Math.max(...detections.map((x) => x.t)) : 0;
    if (latest) {
      const d = now - latest;
      const [n, u] = d < 60000 ? [Math.round(d / 1000), 's ago'] : d < 3600000 ? [Math.round(d / 60000), 'min ago'] : d < DAY ? [Math.round(d / 3600000), 'h ago'] : [Math.round(d / DAY), 'd ago'];
      $('st-last').textContent = n; $('st-last-unit').textContent = u;
    }
    const midnight = new Date(now); midnight.setHours(0, 0, 0, 0);
    $('st-today').textContent = detections.filter((x) => x.t >= midnight.getTime()).length;
  }
  setInterval(tick, 1000);

  // ---------- spectrogram --------------------------------------------------
  const canvas = $('spec'), spec = canvas.getContext('2d');
  const SW = canvas.width, SH = canvas.height;
  spec.fillStyle = '#000004'; spec.fillRect(0, 0, SW, SH);
  const MAGMA = [[0,0,4],[28,16,68],[79,18,123],[129,37,129],[181,54,122],[229,80,100],[251,135,97],[254,194,135],[252,253,191]];
  function magma(v) {
    const x = Math.max(0, Math.min(0.999, v)) * (MAGMA.length - 1), i = Math.floor(x), f = x - i, a = MAGMA[i], b = MAGMA[i + 1];
    return 'rgb(' + (a[0] + (b[0] - a[0]) * f | 0) + ',' + (a[1] + (b[1] - a[1]) * f | 0) + ',' + (a[2] + (b[2] - a[2]) * f | 0) + ')';
  }
  const melOf = (hz) => 2595 * Math.log10(1 + hz / 700), melMax = melOf(1000), melInv = (m) => 700 * (Math.pow(10, m / 2595) - 1);
  const yPct = (hz) => ((1 - melOf(hz) / melMax) * 100).toFixed(2) + '%';
  [1000, 500, 250, 100, 0].forEach((hz, i) => { document.querySelectorAll('.spec-y span')[i].style.top = yPct(hz); });
  [500, 250, 100].forEach((hz, i) => { document.querySelectorAll('.spec-grid i')[i].style.top = yPct(hz); });
  function drawSpec(b) {
    spec.drawImage(canvas, -1, 0);
    const n = b.length;
    for (let i = 0; i < n; i++) {
      const y0 = SH - melOf((i + 1) / n * 1000) / melMax * SH, y1 = SH - melOf(i / n * 1000) / melMax * SH;
      spec.fillStyle = magma(b[i]); spec.fillRect(SW - 1, y0, 1, Math.ceil(y1 - y0));
    }
  }
  let smooth = -60;
  feed.on('audio', (a) => {
    drawSpec(a.bins);
    smooth += (a.level_db - smooth) * 0.2;
    $('level-fill').style.width = Math.max(0, Math.min(100, (smooth + 60) / 60 * 100)) + '%';
    $('level-val').textContent = smooth.toFixed(1) + ' dB';
    $('st-level').textContent = smooth.toFixed(0);
  });

  // ---------- tabs ---------------------------------------------------------
  function showView(name) {
    document.querySelectorAll('.tab').forEach((b) => b.classList.toggle('on', b.dataset.view === name));
    document.querySelectorAll('.view').forEach((v) => v.classList.toggle('hidden', v.id !== 'view-' + name));
    if (name === 'live') map.invalidateSize(); else drawChart();
  }
  document.querySelectorAll('.tab').forEach((btn) => btn.addEventListener('click', () => { location.hash = btn.dataset.view; }));
  window.addEventListener('hashchange', () => showView(location.hash === '#db' ? 'db' : 'live'));
  showView(location.hash === '#db' ? 'db' : 'live');

  // ---------- database -----------------------------------------------------

  function hash(str) { let h = 2166136261; for (const ch of str) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
  function mulberry(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function thumb(d) { // spectrogram of a live call, drawn from its parameters
    const c = document.createElement('canvas'); c.width = 144; c.height = 48; c.className = 'thumb';
    const g = c.getContext('2d'), W = c.width, H = c.height, span = d.duration_s + 1, noise = mulberry(hash(d.id));
    for (let x = 0; x < W; x++) {
      const ph = (x / W * span - 0.5) / d.duration_s, env = ph > 0 && ph < 1 ? Math.sin(ph * Math.PI) * 0.85 : 0, f = d.f0 + d.sweep * ph;
      for (let y = 0; y < H; y++) {
        const hz = melInv((1 - (y + 0.5) / H) * melMax);
        let v = (0.22 * (1 - hz / 1000) + 0.06) * (0.5 + noise());
        if (env) v += env * Math.exp(-Math.pow((hz - f) / 22, 2));
        g.fillStyle = magma(v); g.fillRect(x, y, 1, 1);
      }
    }
    return c;
  }
  function wav(d) { // 8 kHz WAV of a live call
    const sr = 8000, n = Math.round(sr * (d.duration_s + 0.6)), out = new Int16Array(n), noise = mulberry(hash(d.id) ^ 7);
    let phase = 0;
    for (let i = 0; i < n; i++) {
      const t = i / sr - 0.3, ph = t / d.duration_s, env = ph > 0 && ph < 1 ? Math.sin(ph * Math.PI) * 0.7 : 0;
      phase += 2 * Math.PI * (d.f0 + d.sweep * Math.max(0, Math.min(1, ph))) / sr;
      out[i] = Math.max(-1, Math.min(1, (noise() - 0.5) * 0.12 + env * Math.sin(phase))) * 32767;
    }
    const buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf), str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    str(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); str(8, 'WAVE'); str(12, 'fmt '); v.setUint32(16, 16, true);
    v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, n * 2, true);
    new Int16Array(buf, 44).set(out);
    return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
  }

  // one shared player; a button shows its own state
  const player = new Audio(); let playingBtn = null;
  const ICON_PLAY = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>', ICON_STOP = '<svg viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>';
  function stopPlayback() { if (playingBtn) { playingBtn.classList.remove('playing'); playingBtn.querySelector('.ic').innerHTML = ICON_PLAY; playingBtn = null; } player.pause(); }
  player.addEventListener('ended', stopPlayback);
  function playButton(src, seconds) {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'play';
    b.innerHTML = '<span class="ic">' + ICON_PLAY + '</span><span>' + seconds.toFixed(1) + ' s</span>';
    b.setAttribute('aria-label', 'Play clip, ' + seconds.toFixed(1) + ' seconds');
    b.addEventListener('click', () => {
      if (playingBtn === b) return stopPlayback();
      stopPlayback(); player.src = src; player.play(); playingBtn = b; b.classList.add('playing'); b.querySelector('.ic').innerHTML = ICON_STOP;
    });
    return b;
  }

  function ageOpacity(t) { const days = (Date.now() - t) / DAY; return days < 1 ? 1 : Math.max(0.35, 1 - days / 14 * 0.65); }

  function addDetection(d, live) {
    const t = new Date(d.ts).getTime(), when = new Date(t);
    const tr = document.createElement('tr'); if (live) tr.className = 'new';
    const tag = live ? '<span class="tag tag-live">live</span>' : '<span class="tag tag-archive">' + (d.source || 'archive') + '</span>';
    tr.innerHTML =
      '<td>' + when.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }) + tag + '<span class="sub">' + when.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) + '</span></td>' +
      '<td>' + d.lat.toFixed(5) + ', ' + d.lon.toFixed(5) + '<span class="sub">' + Math.round(d.f0) + ' Hz · ' + d.duration_s + ' s</span></td>' +
      '<td><span class="conf"><span class="conf-bar"><i style="width:' + Math.round(d.confidence * 100) + '%"></i></span>' + Math.round(d.confidence * 100) + '%</span></td>' +
      '<td class="td-thumb"></td><td class="td-audio"></td>';
    if (d.spectrogram) { const img = new Image(); img.className = 'thumb'; img.src = d.spectrogram; img.alt = 'spectrogram'; img.loading = 'lazy'; tr.querySelector('.td-thumb').appendChild(img); }
    else tr.querySelector('.td-thumb').appendChild(thumb(d));
    tr.querySelector('.td-audio').appendChild(playButton(d.clip || wav(d), +d.duration_s));
    const mk = L.marker([d.lat, d.lon], { icon: L.divIcon({ className: '', html: '<div class="sighting' + (live ? ' hot' : '') + '"></div>', iconSize: [10, 10], iconAnchor: [5, 5] }), opacity: ageOpacity(t) })
      .bindTooltip(Math.round(d.confidence * 100) + '% · ' + when.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }), { direction: 'top', offset: [0, -6], className: 'sight-tip' })
      .addTo(sightings);
    tr.addEventListener('mouseenter', () => mk.openTooltip()); tr.addEventListener('mouseleave', () => mk.closeTooltip());
    detections.push({ d, t, live, tr, marker: mk });
    renderTable(); renderSummary(); if (!$('view-db').classList.contains('hidden')) drawChart();
  }

  function renderTable() {
    const rows = detections.filter((x) => filter === 'all' || (filter === 'live') === x.live)
      .sort((a, b) => (sortKey === 'ts' ? a.t - b.t : a.d.confidence - b.d.confidence) * sortDir);
    const body = $('db-rows'); body.innerHTML = ''; rows.forEach((x) => body.appendChild(x.tr));
    $('db-empty').classList.toggle('hidden', rows.length > 0);
    const archived = detections.filter((x) => !x.live).length, live = detections.length - archived;
    $('db-count').textContent = $('db-total').textContent = detections.length;
    $('db-meta').textContent = archived + ' archived in data/detections.csv · ' + live + ' live this session, not yet archived';
    $('table-meta').textContent = rows.length + ' of ' + detections.length + ' shown';
    document.querySelectorAll('.sort').forEach((b) => { b.classList.toggle('on', b.dataset.sort === sortKey); b.querySelector('.arrow').textContent = b.dataset.sort === sortKey ? (sortDir < 0 ? '↓' : '↑') : ''; });
  }
  document.querySelectorAll('.chip').forEach((c) => c.addEventListener('click', () => { filter = c.dataset.filter; document.querySelectorAll('.chip').forEach((x) => x.classList.toggle('on', x === c)); renderTable(); }));
  document.querySelectorAll('.sort').forEach((b) => b.addEventListener('click', () => { if (sortKey === b.dataset.sort) sortDir = -sortDir; else { sortKey = b.dataset.sort; sortDir = -1; } renderTable(); }));

  function renderSummary() {
    const now = Date.now();
    $('sm-24h').textContent = detections.filter((x) => now - x.t < DAY).length;
    $('sm-7d').textContent = detections.filter((x) => now - x.t < 7 * DAY).length;
    const c = detections.map((x) => x.d.confidence).sort((a, b) => a - b);
    $('sm-conf').textContent = c.length ? Math.round((c.length % 2 ? c[(c.length - 1) / 2] : (c[c.length / 2 - 1] + c[c.length / 2]) / 2) * 100) + '%' : '—';
    $('sm-buoys').textContent = new Set(detections.map((x) => x.d.buoy_id || feed.buoy.id)).size;
  }

  // detections per day, last 14 days: one series, thin bars anchored to the baseline, hover tooltip, one direct label on the max
  function drawChart() {
    const el = $('chart'), W = el.clientWidth || 800, H = el.clientHeight || 140, padL = 28, padB = 22, padT = 16;
    const days = []; const today = new Date(); today.setHours(0, 0, 0, 0);
    for (let i = 13; i >= 0; i--) { const d0 = today.getTime() - i * DAY; days.push({ t: d0, n: detections.filter((x) => x.t >= d0 && x.t < d0 + DAY).length }); }
    const max = Math.max(1, ...days.map((d) => d.n)), yMax = Math.ceil(max / 2) * 2;
    const x = (i) => padL + i * (W - padL) / 14, bw = Math.min(28, Math.max(6, (W - padL) / 14 - 8)), y = (n) => padT + (H - padT - padB) * (1 - n / yMax);
    let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">';
    [0, yMax / 2, yMax].forEach((v) => { s += '<line class="grid" x1="' + padL + '" x2="' + W + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text x="' + (padL - 8) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + v + '</text>'; });
    s += '<line class="base" x1="' + padL + '" x2="' + W + '" y1="' + y(0) + '" y2="' + y(0) + '"/>';
    days.forEach((d, i) => {
      const cx = x(i) + ((W - padL) / 14 - bw) / 2, top = y(d.n), h = Math.max(0, y(0) - top);
      s += '<rect class="hit" x="' + x(i) + '" y="' + padT + '" width="' + (W - padL) / 14 + '" height="' + (H - padT - padB) + '" data-i="' + i + '"/>';
      if (d.n) s += '<rect class="bar" x="' + cx + '" y="' + top + '" width="' + bw + '" height="' + h + '" rx="2"/>';
      if (d.n === max && d.n > 0) s += '<text class="dl" x="' + (cx + bw / 2) + '" y="' + (top - 5) + '" text-anchor="middle">' + d.n + '</text>';
      if (i % 2 === 1 || i === 13) s += '<text x="' + (cx + bw / 2) + '" y="' + (H - 6) + '" text-anchor="middle">' + new Date(d.t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + '</text>';
    });
    el.innerHTML = s + '</svg>';
    const tip = $('tip');
    el.querySelectorAll('.hit').forEach((r) => {
      r.addEventListener('mouseenter', () => { const d = days[+r.dataset.i]; tip.textContent = new Date(d.t).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' }) + ' · ' + d.n + (d.n === 1 ? ' detection' : ' detections'); tip.classList.remove('hidden'); const b = r.getBoundingClientRect(), p = el.getBoundingClientRect(); tip.style.left = (b.left - p.left + b.width / 2) + 'px'; tip.style.top = (y(d.n) - 8) + 'px'; });
      r.addEventListener('mouseleave', () => tip.classList.add('hidden'));
    });
  }
  window.addEventListener('resize', () => { if (!$('view-db').classList.contains('hidden')) drawChart(); });

  fetch(DATA_BASE + 'detections.json')
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((db) => {
      db.detections.slice().sort((a, b) => a.timestamp_utc.localeCompare(b.timestamp_utc)).forEach((r) => addDetection({
        id: r.id, buoy_id: r.buoy_id, ts: r.timestamp_utc, lat: r.latitude, lon: r.longitude, confidence: r.confidence,
        f0: r.peak_hz || 0, sweep: 0, duration_s: r.duration_s, source: r.source,
        spectrogram: DATA_BASE + r.spectrogram_path, clip: DATA_BASE + r.clip_path,
      }, false));
      if (!db.detections.length) $('db-meta').textContent = 'Archive is empty';
    })
    .catch((e) => { $('db-meta').textContent = 'Archive unavailable (' + e.message + '); showing synthetic rows only'; feed.backfill(8).forEach((d) => addDetection(d, false)); });
  feed.on('detection', (d) => addDetection(d, true));

  feed.start(); tick();
})();
