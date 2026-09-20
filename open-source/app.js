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

  feed.start();
})();
