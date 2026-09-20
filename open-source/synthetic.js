// Synthetic buoy feed. Same event shapes a real buoy would send.
//   telemetry: { id, ts, lat, lon, battery_pct, water_temp_c, uptime_s }   every 2 s
//   audio:     { ts, samples: Float32Array, bins: Float32Array, level_db }  20 / s
//   detection: { id, ts, lat, lon, confidence, f0, sweep, duration_s }        when a call ends
(function (global) {
  'use strict';
  const rand = (a, b) => a + Math.random() * (b - a);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  // Charles River basin, just off the MIT Sailing Pavilion.
  const BUOY = { id: 'KEIKO-01', lat: 42.3572, lon: -71.0868 };
  const NSAMP = 256, NBINS = 80;

  function createFeed() {
    const handlers = {};
    const st = { batt: rand(80, 95), temp: rand(17, 19), uptime: Math.floor(rand(3600, 36000)), call: null };
    const samples = new Float32Array(NSAMP), bins = new Float32Array(NBINS);
    const on = (t, fn) => { (handlers[t] ||= []).push(fn); return api; };
    const emit = (t, p) => (handlers[t] || []).forEach((fn) => fn(p));

    function telemetry() {
      st.batt = clamp(st.batt - rand(0.002, 0.01), 0, 100);
      st.temp = clamp(st.temp + rand(-0.02, 0.02), 5, 28);
      st.uptime += 2;
      emit('telemetry', {
        id: BUOY.id, ts: new Date().toISOString(),
        lat: BUOY.lat + rand(-0.00004, 0.00004), lon: BUOY.lon + rand(-0.00004, 0.00004),
        battery_pct: +st.batt.toFixed(1), water_temp_c: +st.temp.toFixed(2), uptime_s: st.uptime,
      });
    }

    function audio() {
      const t = Date.now();
      // occasional tonal event: boat hum or a whale-like sweep
      if (!st.call && Math.random() < 0.02) {
        st.call = { f0: rand(80, 400), sweep: rand(-150, 150), amp: rand(0.4, 0.8), t0: t, t1: t + rand(1500, 5000) };
      }
      if (st.call && t > st.call.t1) { emit('detection', finish(st.call)); st.call = null; }
      const c = st.call, ph = c ? (t - c.t0) / (c.t1 - c.t0) : 0;
      const f = c ? c.f0 + c.sweep * ph : 0;
      const env = c ? Math.sin(ph * Math.PI) * c.amp : 0;
      let rms = 0;
      for (let i = 0; i < NSAMP; i++) {
        const noise = (Math.random() - 0.5) * 0.25;
        const tone = env * Math.sin(2 * Math.PI * f * (t / 1000 + i / 2000));
        samples[i] = noise + tone;
        rms += samples[i] * samples[i];
      }
      for (let i = 0; i < NBINS; i++) bins[i] = (0.22 * (1 - i / NBINS) + 0.06) * rand(0.5, 1.5);
      if (c) {
        const b = clamp(Math.round(f / 1000 * NBINS), 0, NBINS - 1);
        bins[b] = Math.min(1, bins[b] + env);
        if (b > 0) bins[b - 1] = Math.min(1, bins[b - 1] + env * 0.5);
        if (b < NBINS - 1) bins[b + 1] = Math.min(1, bins[b + 1] + env * 0.5);
      }
      const level = 20 * Math.log10(Math.sqrt(rms / NSAMP) + 1e-6) - 20;
      emit('audio', { ts: new Date().toISOString(), samples, bins, level_db: +level.toFixed(1) });
    }

    let seq = 0;
    // Position the sighting near the buoy but inside the river: the Charles runs
    // roughly NE–SW here (bearing 60°), ~500 m wide, so spread along the axis
    // and keep the across-axis offset small.
    function place() {
      const along = rand(-450, 450), across = rand(-110, 110); // metres
      const ax = Math.sin(60 * Math.PI / 180), ay = Math.cos(60 * Math.PI / 180);
      const east = along * ax + across * ay, north = along * ay - across * ax;
      return {
        lat: +(BUOY.lat + north / 111320).toFixed(5),
        lon: +(BUOY.lon + east / (111320 * Math.cos(BUOY.lat * Math.PI / 180))).toFixed(5),
      };
    }
    function finish(c) {
      const dur = (c.t1 - c.t0) / 1000;
      return Object.assign({
        id: BUOY.id + '-' + (++seq).toString(36) + '-' + c.t0.toString(36),
        ts: new Date(c.t0).toISOString(),
        confidence: +clamp(0.45 + c.amp * 0.55 + rand(-0.08, 0.08), 0.4, 0.99).toFixed(2),
        f0: Math.round(c.f0), sweep: Math.round(c.sweep), duration_s: +dur.toFixed(1),
      }, place());
    }
    // A few back-dated detections so the database is not empty on load.
    function backfill(n) {
      const out = [];
      for (let i = 0; i < n; i++) {
        const t0 = Date.now() - rand(3, 120) * 60000, dur = rand(1500, 5000);
        out.push(finish({ f0: rand(80, 400), sweep: rand(-150, 150), amp: rand(0.4, 0.8), t0, t1: t0 + dur }));
      }
      return out.sort((a, b) => a.ts.localeCompare(b.ts));
    }

    function start() { telemetry(); setInterval(telemetry, 2000); setInterval(audio, 50); return api; }
    const api = { on, start, backfill, buoy: BUOY };
    return api;
  }
  global.createFeed = createFeed;
})(window);
