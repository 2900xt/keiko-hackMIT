(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const feed = createFeed();

  // ---- map ---------------------------------------------------------------
  const map = L.map('map', { zoomControl: false }).setView([feed.buoy.lat, feed.buoy.lon], 15);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19, attribution: 'Tiles &copy; Esri &mdash; Maxar, Earthstar Geographics, and the GIS User Community',
  }).addTo(map);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19, pane: 'overlayPane',
  }).addTo(map);
  const marker = L.marker([feed.buoy.lat, feed.buoy.lon], {
    icon: L.divIcon({ className: '', html: '<div class="buoy"></div>', iconSize: [16, 16], iconAnchor: [8, 8] }),
  }).addTo(map).bindTooltip(feed.buoy.id, { permanent: true, direction: 'right', offset: [12, 0], className: 'buoy-label' });

  // ---- status ------------------------------------------------------------
  let last = 0;
  feed.on('telemetry', (t) => {
    last = Date.now();
    $('s-id').textContent = t.id;
    $('s-lat').textContent = t.lat.toFixed(5);
    $('s-lon').textContent = t.lon.toFixed(5);
    $('s-time').textContent = new Date(t.ts).toLocaleTimeString();
    marker.setLatLng([t.lat, t.lon]);
  });
  function tick() {
    $('clock').textContent = new Date().toLocaleTimeString();
    const age = Date.now() - last;
    const k = !last ? '' : age > 10000 ? 'off' : age > 5000 ? 'stale' : 'on';
    const word = !last ? 'connecting' : k === 'off' ? 'offline' : k === 'stale' ? 'stale' : 'online';
    $('s-state').textContent = word; $('s-state').className = 'state ' + k;
    $('live').className = 'live ' + k; $('live-text').textContent = k === 'on' ? 'Live' : word[0].toUpperCase() + word.slice(1);
  }
  setInterval(tick, 1000); tick();

  // ---- spectrogram -------------------------------------------------------
  const canvas = $('spec'), spec = canvas.getContext('2d');
  const SW = canvas.width, SH = canvas.height;
  spec.fillStyle = '#000004'; spec.fillRect(0, 0, SW, SH);
  const MAGMA = [[0,0,4],[28,16,68],[79,18,123],[129,37,129],[181,54,122],[229,80,100],[251,135,97],[254,194,135],[252,253,191]];
  function magma(v) {
    const x = Math.max(0, Math.min(0.999, v)) * (MAGMA.length - 1), i = Math.floor(x), f = x - i;
    const a = MAGMA[i], b = MAGMA[i + 1];
    return 'rgb(' + (a[0] + (b[0] - a[0]) * f | 0) + ',' + (a[1] + (b[1] - a[1]) * f | 0) + ',' + (a[2] + (b[2] - a[2]) * f | 0) + ')';
  }
  const melOf = (hz) => 2595 * Math.log10(1 + hz / 700), melMax = melOf(1000);
  function drawSpec(b) {
    spec.drawImage(canvas, -1, 0); // 600 px wide at 20 fps = 30 s of history
    const n = b.length;
    for (let i = 0; i < n; i++) {
      const y0 = SH - melOf((i + 1) / n * 1000) / melMax * SH, y1 = SH - melOf(i / n * 1000) / melMax * SH;
      spec.fillStyle = magma(b[i]);
      spec.fillRect(SW - 1, y0, 1, Math.ceil(y1 - y0));
    }
  }
  // y-axis labels are placed by mel position so they line up with the drawing
  const ticks = [1000, 500, 250, 100, 0], yEl = document.querySelector('.spec-y');
  yEl.style.justifyContent = 'flex-start'; yEl.style.position = 'relative';
  [...yEl.children].forEach((el, i) => {
    el.style.position = 'absolute'; el.style.right = '0';
    el.style.top = 'calc(' + ((1 - melOf(ticks[i]) / melMax) * 100).toFixed(1) + '% - 7px)';
  });

  let smooth = -60;
  feed.on('audio', (a) => {
    drawSpec(a.bins);
    smooth += (a.level_db - smooth) * 0.2;
    const pct = Math.max(0, Math.min(100, (smooth + 60) / 60 * 100)); // −60..0 dB
    $('level-fill').style.width = pct + '%';
    $('level-val').textContent = smooth.toFixed(1) + ' dB';
  });

  // ---- tabs (deep-linkable: #live / #db) ---------------------------------
  function showView(name) {
    document.querySelectorAll('.tab').forEach((b) => b.classList.toggle('on', b.dataset.view === name));
    document.querySelectorAll('.view').forEach((v) => v.classList.toggle('hidden', v.id !== 'view-' + name));
    if (name === 'live') map.invalidateSize();
  }
  document.querySelectorAll('.tab').forEach((btn) => btn.addEventListener('click', () => { location.hash = btn.dataset.view; }));
  window.addEventListener('hashchange', () => showView(location.hash === '#db' ? 'db' : 'live'));
  showView(location.hash === '#db' ? 'db' : 'live');

  // ---- database ----------------------------------------------------------
  const detections = [];
  const sightings = L.layerGroup().addTo(map);

  // Small spectrogram of one call, drawn from its parameters (same look as the live panel).
  function thumb(d) {
    const c = document.createElement('canvas'); c.width = 144; c.height = 48; c.className = 'thumb';
    const g = c.getContext('2d'), W = c.width, H = c.height, cols = W, span = d.duration_s + 1.0; // 0.5 s pad each side
    const noise = mulberry(hash(d.id));
    for (let x = 0; x < cols; x++) {
      const t = x / cols * span - 0.5, ph = t / d.duration_s;
      const env = ph > 0 && ph < 1 ? Math.sin(ph * Math.PI) * 0.85 : 0, f = d.f0 + d.sweep * ph;
      for (let y = 0; y < H; y++) {
        const hz = melInv((1 - (y + 0.5) / H) * melMax);
        let v = (0.22 * (1 - hz / 1000) + 0.06) * (0.5 + noise());
        if (env) v += env * Math.exp(-Math.pow((hz - f) / 22, 2));
        g.fillStyle = magma(v); g.fillRect(x, y, 1, 1);
      }
    }
    return c;
  }
  const melInv = (m) => 700 * (Math.pow(10, m / 2595) - 1);
  function hash(str) { let h = 2166136261; for (const ch of str) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
  function mulberry(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

  // 8 kHz mono WAV of the same call: noise floor + frequency sweep with a sine envelope.
  function wav(d) {
    const sr = 8000, n = Math.round(sr * (d.duration_s + 0.6)), out = new Int16Array(n), noise = mulberry(hash(d.id) ^ 7);
    let phase = 0;
    for (let i = 0; i < n; i++) {
      const t = i / sr - 0.3, ph = t / d.duration_s;
      const env = ph > 0 && ph < 1 ? Math.sin(ph * Math.PI) * 0.7 : 0;
      phase += 2 * Math.PI * (d.f0 + d.sweep * Math.max(0, Math.min(1, ph))) / sr;
      out[i] = Math.max(-1, Math.min(1, (noise() - 0.5) * 0.12 + env * Math.sin(phase))) * 32767;
    }
    const buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
    const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    str(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); str(8, 'WAVE'); str(12, 'fmt '); v.setUint32(16, 16, true);
    v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, n * 2, true);
    new Int16Array(buf, 44).set(out);
    return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
  }

  function addDetection(d, live) {
    detections.push(d);
    const when = new Date(d.ts);
    const tr = document.createElement('tr');
    if (live) tr.className = 'new';
    tr.innerHTML =
      '<td>' + when.toLocaleTimeString() + '<span class="sub">' + when.toLocaleDateString() + '</span></td>' +
      '<td>' + d.lat.toFixed(5) + ', ' + d.lon.toFixed(5) + '<span class="sub">' + d.f0 + ' Hz · ' + d.duration_s + ' s</span></td>' +
      '<td><span class="conf"><span class="conf-bar"><i style="width:' + Math.round(d.confidence * 100) + '%"></i></span>' + Math.round(d.confidence * 100) + '%</span></td>' +
      '<td class="td-thumb"></td>' +
      '<td><audio controls preload="none" src="' + wav(d) + '"></audio></td>';
    tr.querySelector('.td-thumb').appendChild(thumb(d));
    $('db-rows').prepend(tr);
    $('db-count').textContent = $('db-total').textContent = detections.length;
    $('db-empty').classList.add('hidden');
    L.marker([d.lat, d.lon], { icon: L.divIcon({ className: '', html: '<div class="sighting"></div>', iconSize: [10, 10], iconAnchor: [5, 5] }) })
      .bindTooltip(Math.round(d.confidence * 100) + '% · ' + when.toLocaleTimeString(), { direction: 'top', offset: [0, -6] })
      .addTo(sightings);
  }
  feed.backfill(8).forEach((d) => addDetection(d, false));
  feed.on('detection', (d) => addDetection(d, true));

  feed.start();
})();
