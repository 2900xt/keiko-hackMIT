(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const feed = createFeed();

  // map
  const map = L.map('map').setView([feed.buoy.lat, feed.buoy.lon], 15);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
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
  spec.fillStyle = '#fff'; spec.fillRect(0, 0, SW, SH);

  function drawSpec(b) {
    const col = 1; // 600 px wide, 20 fps → 30 s of history
    spec.drawImage($('spec'), -col, 0);
    const cell = SH / b.length;
    for (let i = 0; i < b.length; i++) {
      const v = 255 - Math.round(Math.min(1, b[i]) * 255); // grayscale, loud = dark
      spec.fillStyle = 'rgb(' + v + ',' + v + ',' + v + ')';
      spec.fillRect(SW - col, SH - (i + 1) * cell, Math.ceil(col), Math.ceil(cell));
    }
  }
  feed.on('audio', (a) => { drawSpec(a.bins); $('spec-note').textContent = 'Level: ' + a.level_db + ' dB'; });

  feed.start();
})();
