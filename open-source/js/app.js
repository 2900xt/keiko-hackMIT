/* Keiko Whale Network — UI wiring. Reads events from a buoy stream and draws them. */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const DETECTION_TTL_MS = 30 * 60 * 1000; // markers fade out over 30 min
  const MAX_FEED = 60;

  const stream = window.KeikoSynthetic.createSyntheticBuoyStream();
  const buoy = stream.buoy;

  // --- map ---------------------------------------------------------------
  const map = L.map('map', { zoomControl: true, attributionControl: true })
    .setView([buoy.lat, buoy.lon], 11);
  // Esri Ocean basemap: bathymetry, no API key. Darkened via CSS (.leaflet-tile-pane) to match the theme.
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 13,
    attribution: 'Tiles &copy; Esri &mdash; GEBCO, NOAA, National Geographic, DeLorme, HERE, Geonames.org, and others',
  }).addTo(map);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 13, opacity: 0.8, pane: 'overlayPane',
  }).addTo(map);

  const rangeCircle = L.circle([buoy.lat, buoy.lon], {
    radius: buoy.range_km * 1000, color: '#3fc1c9', weight: 1.5, dashArray: '6 6', fillColor: '#3fc1c9', fillOpacity: 0.05,
  }).addTo(map);

  const buoyMarker = L.marker([buoy.lat, buoy.lon], {
    icon: L.divIcon({ className: '', html: '<div class="buoy-marker"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
    zIndexOffset: 1000,
  }).addTo(map).bindPopup(`<strong>${buoy.id}</strong><br>${buoy.name}<br>${buoy.hydrophone} · ${buoy.sample_rate_hz} Hz`);

  const detectionLayer = L.layerGroup().addTo(map);
  const markers = []; // { marker, ts }

  function addDetectionMarker(d) {
    const m = L.circleMarker([d.lat, d.lon], {
      radius: 6 + d.confidence * 4, color: '#f6a821', weight: 1.5, fillColor: '#f6a821', fillOpacity: 0.85,
    }).bindPopup(
      `<strong>${d.common_name}</strong><br>` +
      `confidence ${(d.confidence * 100).toFixed(0)}% · ${d.range_km} km @ ${d.bearing_deg}°<br>` +
      `peak ${d.peak_hz} Hz · ${d.duration_s}s<br>` +
      `<span style="color:#8ea2bb">${new Date(d.ts).toLocaleTimeString()}</span>`
    );
    detectionLayer.addLayer(m);
    markers.push({ marker: m, ts: new Date(d.ts).getTime() });
  }

  function fadeMarkers() {
    const now = Date.now();
    for (let i = markers.length - 1; i >= 0; i--) {
      const age = now - markers[i].ts;
      if (age > DETECTION_TTL_MS) { detectionLayer.removeLayer(markers[i].marker); markers.splice(i, 1); continue; }
      const k = 1 - age / DETECTION_TTL_MS;
      markers[i].marker.setStyle({ fillOpacity: 0.15 + 0.7 * k, opacity: 0.3 + 0.7 * k });
    }
  }

  // --- spectrogram -------------------------------------------------------
  const canvas = $('spectrogram');
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.fillStyle = '#050c14'; ctx.fillRect(0, 0, W, H);

  function heat(v) {
    // dark navy → teal → yellow → white
    const stops = [[5, 12, 20], [16, 70, 110], [63, 193, 201], [246, 168, 33], [255, 245, 220]];
    const x = Math.max(0, Math.min(0.999, v)) * (stops.length - 1);
    const i = Math.floor(x), f = x - i;
    const a = stops[i], b = stops[i + 1];
    return `rgb(${a[0] + (b[0] - a[0]) * f | 0},${a[1] + (b[1] - a[1]) * f | 0},${a[2] + (b[2] - a[2]) * f | 0})`;
  }

  function drawColumn(bins) {
    const colW = 2;
    const img = ctx.getImageData(colW, 0, W - colW, H);
    ctx.putImageData(img, 0, 0);
    const n = bins.length, cellH = H / n;
    for (let i = 0; i < n; i++) {
      ctx.fillStyle = heat(bins[i]);
      ctx.fillRect(W - colW, H - (i + 1) * cellH, colW, Math.ceil(cellH));
    }
  }

  // --- sidebar -----------------------------------------------------------
  const speciesCounts = new Map();
  const recent = []; // detections within the last hour

  function fmtUptime(s) {
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    return d ? `${d}d ${h}h ${m}m` : `${h}h ${m}m`;
  }

  let lastHeartbeat = 0;
  function renderTelemetry(t) {
    lastHeartbeat = Date.now();
    $('buoy-pos').textContent = `${t.lat.toFixed(4)}, ${t.lon.toFixed(4)}`;
    $('buoy-batt').textContent = `${t.battery_pct}%`;
    $('buoy-batt').style.color = t.battery_pct < 20 ? 'var(--bad)' : t.battery_pct < 40 ? 'var(--warn)' : '';
    $('buoy-temp').textContent = `${t.water_temp_c.toFixed(1)} °C`;
    $('buoy-rssi').textContent = `${t.rssi_dbm} dBm`;
    $('buoy-noise').textContent = `${t.noise_floor_db} dB`;
    $('buoy-uptime').textContent = fmtUptime(t.uptime_s);
    $('buoy-heartbeat').textContent = new Date(t.ts).toLocaleTimeString();
    buoyMarker.setLatLng([t.lat, t.lon]);
    rangeCircle.setLatLng([t.lat, t.lon]);
  }

  function renderStatus() {
    const el = $('buoy-status');
    const age = Date.now() - lastHeartbeat;
    if (!lastHeartbeat) { el.textContent = 'connecting'; el.className = 'status stale'; return; }
    if (age > 30000) { el.textContent = 'offline'; el.className = 'status offline'; }
    else if (age > 8000) { el.textContent = 'stale'; el.className = 'status stale'; }
    else { el.textContent = 'online'; el.className = 'status'; }
  }

  function renderSpeciesBars() {
    const cutoff = Date.now() - 3600 * 1000;
    while (recent.length && new Date(recent[0].ts).getTime() < cutoff) recent.shift();
    speciesCounts.clear();
    for (const d of recent) speciesCounts.set(d.common_name, (speciesCounts.get(d.common_name) || 0) + 1);
    const rows = [...speciesCounts.entries()].sort((a, b) => b[1] - a[1]);
    const max = rows.length ? rows[0][1] : 1;
    $('hour-total').textContent = `${recent.length} detection${recent.length === 1 ? '' : 's'}`;
    $('species-bars').innerHTML = rows.map(([name, n]) =>
      `<li><span>${name}</span><span class="bar"><i style="width:${(n / max * 100).toFixed(0)}%"></i></span><span class="n">${n}</span></li>`
    ).join('') || '<li class="muted">No detections yet</li>';
  }

  function renderFeedItem(d) {
    const li = document.createElement('li');
    li.innerHTML =
      `<span class="title">${d.common_name}</span>` +
      `<span class="time">${new Date(d.ts).toLocaleTimeString()}</span>` +
      `<span class="detail"><span class="conf">${(d.confidence * 100).toFixed(0)}%</span> · ${d.range_km} km @ ${d.bearing_deg}° · ${d.peak_hz} Hz · ${d.duration_s}s</span>`;
    const feed = $('feed');
    feed.prepend(li);
    while (feed.children.length > MAX_FEED) feed.lastChild.remove();
  }

  function handleDetection(d, { silent = false } = {}) {
    recent.push(d);
    recent.sort((a, b) => a.ts.localeCompare(b.ts));
    addDetectionMarker(d);
    if (!silent) renderFeedItem(d);
    renderSpeciesBars();
  }

  // --- stream wiring -----------------------------------------------------
  stream
    .on('hello', ({ buoy: b }) => {
      $('buoy-id').textContent = b.id;
      $('buoy-name').textContent = `${b.name} · ${b.hydrophone}`;
      $('spec-label').textContent = `0–${b.sample_rate_hz / 2 / 1000} kHz · 10 fps`;
    })
    .on('telemetry', renderTelemetry)
    .on('audio', ({ bins }) => drawColumn(bins))
    .on('detection', (d) => handleDetection(d));

  // backfilled history: markers + stats, and the feed, oldest first so newest ends on top
  for (const d of stream.backfill(10)) { handleDetection(d); }
  fadeMarkers();

  stream.start();

  // --- housekeeping ------------------------------------------------------
  setInterval(() => {
    $('clock').textContent = new Date().toLocaleTimeString();
    renderStatus();
    fadeMarkers();
    renderSpeciesBars();
  }, 1000);

  let paused = false;
  $('pause-btn').addEventListener('click', () => {
    paused = !paused;
    stream.pause(paused);
    $('pause-btn').textContent = paused ? 'Resume' : 'Pause';
    $('pause-btn').setAttribute('aria-pressed', String(paused));
    $('stream-pill').classList.toggle('paused', paused);
    $('stream-pill').lastChild.textContent = paused ? ' Paused' : ' Synthetic stream';
  });
})();
