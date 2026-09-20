/**
 * Synthetic buoy stream.
 *
 * Emits the same event shapes a real Keiko buoy will send over a WebSocket,
 * so the UI in app.js never has to know it is fake. To go live, replace
 * `createSyntheticBuoyStream()` with something that parses socket messages
 * and calls the same `emit(type, payload)`.
 *
 * Event contract (all timestamps are ISO-8601 UTC strings):
 *
 *   "hello"      { buoy }                    once, buoy metadata
 *   "telemetry"  { buoy_id, ts, lat, lon, battery_pct, water_temp_c,
 *                  rssi_dbm, noise_floor_db, uptime_s }
 *   "audio"      { buoy_id, ts, bins: Float32Array }   spectrogram column, 0..1
 *   "detection"  { id, buoy_id, ts, species, common_name, confidence,
 *                  bearing_deg, range_km, lat, lon, peak_hz, duration_s }
 */
(function (global) {
  'use strict';

  const SPECIES = [
    { key: 'humpback',    common_name: 'Humpback whale',        weight: 0.42, band: [120, 900],  calls: 3, dur: [4, 14] },
    { key: 'fin',         common_name: 'Fin whale',             weight: 0.25, band: [15, 40],    calls: 6, dur: [1, 2] },
    { key: 'right_whale', common_name: 'North Atlantic right whale', weight: 0.18, band: [80, 250], calls: 2, dur: [1, 3] },
    { key: 'minke',       common_name: 'Minke whale',           weight: 0.15, band: [50, 300],   calls: 4, dur: [2, 5] },
  ];

  const DEFAULT_BUOY = {
    id: 'KEIKO-01',
    name: 'Stellwagen Bank test buoy',
    lat: 42.3950,
    lon: -70.3450,
    range_km: 8,
    hydrophone: 'Aquarian H2a',
    sample_rate_hz: 2000,
  };

  // --- helpers -----------------------------------------------------------
  const rand = (a, b) => a + Math.random() * (b - a);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
  const nowIso = () => new Date().toISOString();

  function weightedSpecies() {
    let r = Math.random();
    for (const s of SPECIES) { r -= s.weight; if (r <= 0) return s; }
    return SPECIES[0];
  }

  // Offset a lat/lon by bearing (deg, clockwise from north) and range (km).
  function offset(lat, lon, bearingDeg, rangeKm) {
    const R = 6371;
    const br = bearingDeg * Math.PI / 180;
    const la1 = lat * Math.PI / 180, lo1 = lon * Math.PI / 180;
    const d = rangeKm / R;
    const la2 = Math.asin(Math.sin(la1) * Math.cos(d) + Math.cos(la1) * Math.sin(d) * Math.cos(br));
    const lo2 = lo1 + Math.atan2(Math.sin(br) * Math.sin(d) * Math.cos(la1), Math.cos(d) - Math.sin(la1) * Math.sin(la2));
    return { lat: la2 * 180 / Math.PI, lon: lo2 * 180 / Math.PI };
  }

  // --- virtual whales -----------------------------------------------------
  // A few animals wander around the buoy in polar coordinates. Detections
  // sample from them with noise so the map shows plausible tracks instead of
  // uniform confetti.
  function makeWhale(buoy) {
    const s = weightedSpecies();
    return {
      species: s,
      bearing: rand(0, 360),
      range: rand(0.8, buoy.range_km * 0.8),
      driftBearing: rand(-4, 4),     // deg per detection
      driftRange: rand(-0.35, 0.35), // km per detection
      remaining: Math.floor(rand(3, 12)), // detections before it leaves
    };
  }

  function createSyntheticBuoyStream(opts = {}) {
    const buoy = Object.assign({}, DEFAULT_BUOY, opts.buoy || {});
    const listeners = {};
    const state = {
      battery: rand(78, 96),
      temp: rand(11, 14.5),
      uptime: Math.floor(rand(3600 * 6, 3600 * 40)),
      noise: rand(-96, -90),
      startedAt: Date.now(),
      paused: false,
      whales: [],
      activeCall: null, // { species, endsAt, harmonics[] }
      detectionSeq: 0,
    };
    const timers = [];
    const NBINS = 96;
    const bins = new Float32Array(NBINS);

    function on(type, fn) { (listeners[type] ||= []).push(fn); return api; }
    function emit(type, payload) { (listeners[type] || []).forEach((fn) => fn(payload)); }

    // --- telemetry, every 2 s ---
    function tickTelemetry() {
      if (state.paused) return;
      state.battery = clamp(state.battery - rand(0.002, 0.01), 5, 100);
      state.temp = clamp(state.temp + rand(-0.03, 0.03), 4, 22);
      state.noise = clamp(state.noise + rand(-0.6, 0.6), -105, -80);
      state.uptime += 2;
      emit('telemetry', {
        buoy_id: buoy.id,
        ts: nowIso(),
        lat: buoy.lat + rand(-0.00005, 0.00005), // mooring sway
        lon: buoy.lon + rand(-0.00005, 0.00005),
        battery_pct: +state.battery.toFixed(1),
        water_temp_c: +state.temp.toFixed(2),
        rssi_dbm: Math.round(rand(-78, -62)),
        noise_floor_db: +state.noise.toFixed(1),
        uptime_s: state.uptime,
      });
    }

    // --- audio spectrogram column, 10 fps ---
    function tickAudio() {
      if (state.paused) return;
      const t = Date.now();
      for (let i = 0; i < NBINS; i++) {
        // pink-ish background: louder at low freq, plus flicker
        const base = 0.22 * (1 - i / NBINS) + 0.05;
        bins[i] = base * rand(0.6, 1.4);
      }
      // occasional boat / broadband transient
      if (Math.random() < 0.015) for (let i = 0; i < NBINS; i++) bins[i] += rand(0.15, 0.35);
      // active whale call: sweeping harmonic stack
      const call = state.activeCall;
      if (call) {
        if (t > call.endsAt) {
          state.activeCall = null;
        } else {
          const phase = (t - call.startsAt) / (call.endsAt - call.startsAt); // 0..1
          call.harmonics.forEach((h, k) => {
            const hz = h.f0 + h.sweep * Math.sin(phase * Math.PI * h.wobble);
            const bin = clamp(Math.round(hz / 1000 * NBINS), 0, NBINS - 1);
            const amp = h.amp * (1 - k * 0.22) * Math.sin(phase * Math.PI); // fade in/out
            bins[bin] = Math.min(1, bins[bin] + amp);
            if (bin > 0) bins[bin - 1] = Math.min(1, bins[bin - 1] + amp * 0.45);
            if (bin < NBINS - 1) bins[bin + 1] = Math.min(1, bins[bin + 1] + amp * 0.45);
          });
        }
      }
      emit('audio', { buoy_id: buoy.id, ts: nowIso(), bins });
    }

    function startCall(species, durationS) {
      const [lo, hi] = species.band;
      const f0 = rand(lo, hi);
      const harmonics = [];
      for (let k = 1; k <= species.calls; k++) {
        harmonics.push({ f0: f0 * k, sweep: rand(10, 80) * k, wobble: rand(1, 3), amp: rand(0.55, 0.9) });
      }
      const now = Date.now();
      state.activeCall = { species, startsAt: now, endsAt: now + durationS * 1000, harmonics };
    }

    // --- detections, random 5–18 s apart ---
    function scheduleDetection() {
      const delay = rand(5000, 18000);
      timers.push(setTimeout(() => { tickDetection(); scheduleDetection(); }, delay));
    }

    function tickDetection() {
      if (state.paused) return;
      // keep 1–3 whales in the area
      state.whales = state.whales.filter((w) => w.remaining > 0);
      while (state.whales.length < 1 || (state.whales.length < 3 && Math.random() < 0.3)) {
        state.whales.push(makeWhale(buoy));
      }
      const w = pick(state.whales);
      w.bearing = (w.bearing + w.driftBearing + rand(-2, 2) + 360) % 360;
      w.range = clamp(w.range + w.driftRange + rand(-0.15, 0.15), 0.3, buoy.range_km);
      w.remaining -= 1;

      const s = w.species;
      const durationS = rand(s.dur[0], s.dur[1]);
      const measuredBearing = (w.bearing + rand(-6, 6) + 360) % 360;   // TDOA error
      const measuredRange = clamp(w.range * rand(0.85, 1.15), 0.2, buoy.range_km);
      const pos = offset(buoy.lat, buoy.lon, measuredBearing, measuredRange);
      // confidence falls off with range and at species boundaries
      const confidence = clamp(rand(0.62, 0.98) - measuredRange / buoy.range_km * 0.25, 0.4, 0.99);

      startCall(s, durationS);
      state.detectionSeq += 1;
      emit('detection', {
        id: `${buoy.id}-${Date.now().toString(36)}-${state.detectionSeq}`,
        buoy_id: buoy.id,
        ts: nowIso(),
        species: s.key,
        common_name: s.common_name,
        confidence: +confidence.toFixed(2),
        bearing_deg: +measuredBearing.toFixed(1),
        range_km: +measuredRange.toFixed(2),
        lat: +pos.lat.toFixed(5),
        lon: +pos.lon.toFixed(5),
        peak_hz: Math.round(rand(s.band[0], s.band[1])),
        duration_s: +durationS.toFixed(1),
      });
    }

    function start() {
      emit('hello', { buoy: Object.assign({}, buoy) });
      tickTelemetry();
      timers.push(setInterval(tickTelemetry, 2000));
      timers.push(setInterval(tickAudio, 100));
      // first detection quickly so the page is not empty
      timers.push(setTimeout(() => { tickDetection(); scheduleDetection(); }, 1500));
      return api;
    }
    function stop() { timers.forEach(clearTimeout); timers.forEach(clearInterval); timers.length = 0; }
    function pause(p) { state.paused = p; }

    // A handful of back-dated detections so "last hour" is not empty on load.
    function backfill(n = 10) {
      const out = [];
      for (let i = n; i > 0; i--) {
        const s = weightedSpecies();
        const bearing = rand(0, 360), range = rand(0.4, buoy.range_km);
        const pos = offset(buoy.lat, buoy.lon, bearing, range);
        const ts = new Date(Date.now() - rand(2, 55) * 60000 - i * 1000);
        out.push({
          id: `${buoy.id}-backfill-${i}`, buoy_id: buoy.id, ts: ts.toISOString(),
          species: s.key, common_name: s.common_name,
          confidence: +clamp(rand(0.6, 0.97) - range / buoy.range_km * 0.25, 0.4, 0.99).toFixed(2),
          bearing_deg: +bearing.toFixed(1), range_km: +range.toFixed(2),
          lat: +pos.lat.toFixed(5), lon: +pos.lon.toFixed(5),
          peak_hz: Math.round(rand(s.band[0], s.band[1])), duration_s: +rand(s.dur[0], s.dur[1]).toFixed(1),
        });
      }
      return out.sort((a, b) => a.ts.localeCompare(b.ts));
    }

    const api = { on, start, stop, pause, backfill, buoy, SPECIES };
    return api;
  }

  global.KeikoSynthetic = { createSyntheticBuoyStream, SPECIES, DEFAULT_BUOY };
})(window);
