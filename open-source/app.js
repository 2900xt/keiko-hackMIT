(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const feed = createFeed();

  // map
  const map = L.map('map').setView([feed.buoy.lat, feed.buoy.lon], 15);
  // Esri satellite imagery with a light label overlay. No API key.
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19, attribution: 'Tiles &copy; Esri &mdash; Maxar, Earthstar Geographics, and the GIS User Community',
  }).addTo(map);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19, pane: 'overlayPane',
  }).addTo(map);
  const marker = L.marker([feed.buoy.lat, feed.buoy.lon], {
    icon: L.divIcon({ className: '', html: '<div class="buoy-icon"></div>', iconSize: [14, 14], iconAnchor: [7, 7] }),
  }).addTo(map).bindPopup(feed.buoy.id);

  // status
  let last = 0;
  feed.on('telemetry', (t) => {
    last = Date.now();
    $('s-id').textContent = t.id;
    $('s-pos').textContent = t.lat.toFixed(5) + ', ' + t.lon.toFixed(5);
    $('s-time').textContent = new Date(t.ts).toLocaleTimeString();
    marker.setLatLng([t.lat, t.lon]);
  });
  setInterval(() => {
    const age = Date.now() - last;
    const el = $('s-state');
    el.textContent = !last ? 'connecting' : age > 10000 ? 'offline' : 'online';
    el.className = last && age <= 10000 ? 'on' : '';
  }, 1000);

  // hydrophone
  const spec = $('spec').getContext('2d');
  const SW = $('spec').width, SH = $('spec').height;
  spec.fillStyle = '#000004'; spec.fillRect(0, 0, SW, SH);

  // magma colormap, the usual look of a librosa mel-spectrogram
  const MAGMA = [[0,0,4],[28,16,68],[79,18,123],[129,37,129],[181,54,122],[229,80,100],[251,135,97],[254,194,135],[252,253,191]];
  function magma(v) {
    const x = Math.max(0, Math.min(0.999, v)) * (MAGMA.length - 1), i = Math.floor(x), f = x - i;
    const a = MAGMA[i], b = MAGMA[i + 1];
    return 'rgb(' + (a[0] + (b[0] - a[0]) * f | 0) + ',' + (a[1] + (b[1] - a[1]) * f | 0) + ',' + (a[2] + (b[2] - a[2]) * f | 0) + ')';
  }
  // mel scale: y position of each linear bin, so low frequencies get more room
  const melOf = (hz) => 2595 * Math.log10(1 + hz / 700);
  function drawSpec(b) {
    const col = 1; // 600 px wide, 20 fps → 30 s of history
    spec.drawImage($('spec'), -col, 0);
    const n = b.length, melMax = melOf(1000);
    for (let i = 0; i < n; i++) {
      const y0 = SH - melOf((i + 1) / n * 1000) / melMax * SH;
      const y1 = SH - melOf(i / n * 1000) / melMax * SH;
      spec.fillStyle = magma(b[i]);
      spec.fillRect(SW - col, y0, col, Math.ceil(y1 - y0));
    }
  }
  feed.on('audio', (a) => { drawSpec(a.bins); $('spec-note').textContent = 'Level: ' + a.level_db + ' dB'; });

  feed.start();
})();
