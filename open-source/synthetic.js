// Synthetic buoy feed. Same event shapes a real buoy would send.
//   telemetry: { id, ts, lat, lon, battery_pct, water_temp_c, uptime_s }   every 2 s
//   audio:     { ts, samples: Float32Array, bins: Float32Array, level_db }  20 / s
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
      if (st.call && t > st.call.t1) st.call = null;
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
      for (let i = 0; i < NBINS; i++) bins[i] = (0.14 * (1 - i / NBINS) + 0.03) * rand(0.5, 1.5);
      if (c) {
        const b = clamp(Math.round(f / 1000 * NBINS), 0, NBINS - 1);
        bins[b] = Math.min(1, bins[b] + env);
        if (b > 0) bins[b - 1] = Math.min(1, bins[b - 1] + env * 0.5);
        if (b < NBINS - 1) bins[b + 1] = Math.min(1, bins[b + 1] + env * 0.5);
      }
      const level = 20 * Math.log10(Math.sqrt(rms / NSAMP) + 1e-6) - 20;
      emit('audio', { ts: new Date().toISOString(), samples, bins, level_db: +level.toFixed(1) });
    }

    function start() { telemetry(); setInterval(telemetry, 2000); setInterval(audio, 50); return api; }
    const api = { on, start, buoy: BUOY };
    return api;
  }
  global.createFeed = createFeed;
})(window);
