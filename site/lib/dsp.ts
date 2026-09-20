// Colour map, mel scale, and the two things a live detection row renders from
// its call parameters: a spectrogram thumbnail and an 8 kHz WAV clip.

const MAGMA = [[0,0,4],[28,16,68],[79,18,123],[129,37,129],[181,54,122],[229,80,100],[251,135,97],[254,194,135],[252,253,191]];
export const SPEC_BG = "#000004";

export function magmaRGB(v: number): [number, number, number] {
  const x = Math.max(0, Math.min(0.999, v)) * (MAGMA.length - 1), i = Math.floor(x), f = x - i, a = MAGMA[i], b = MAGMA[i + 1];
  return [a[0] + (b[0] - a[0]) * f | 0, a[1] + (b[1] - a[1]) * f | 0, a[2] + (b[2] - a[2]) * f | 0];
}
export function magma(v: number) {
  const [r, g, b] = magmaRGB(v);
  return "rgb(" + r + "," + g + "," + b + ")";
}

export const melOf = (hz: number) => 2595 * Math.log10(1 + hz / 700);
export const MEL_MAX = melOf(1000);
export const melInv = (m: number) => 700 * (Math.pow(10, m / 2595) - 1);
// y position (0 = top, 1 = bottom) of a frequency on the 0–1 kHz mel axis
export const yFrac = (hz: number) => 1 - melOf(hz) / MEL_MAX;
export const yPct = (hz: number) => (yFrac(hz) * 100).toFixed(2) + "%";

export function hash(str: string) {
  let h = 2166136261;
  for (const ch of str) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
export function mulberry(a: number) {
  return () => {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

export interface CallParams { id: string; f0: number; sweep: number; duration_s: number }

// Draw the spectrogram of a live call, from its parameters, onto a canvas of
// any size (the 144×48 table thumbnail and the 600×200 detail view share it).
export function drawThumb(c: HTMLCanvasElement, d: CallParams) {
  const g = c.getContext("2d");
  if (!g) return;
  const W = c.width, H = c.height, span = d.duration_s + 1, noise = mulberry(hash(d.id));
  const img = g.createImageData(W, H), px = img.data;
  const hzAt = new Float32Array(H);
  for (let y = 0; y < H; y++) hzAt[y] = melInv((1 - (y + 0.5) / H) * MEL_MAX);
  for (let x = 0; x < W; x++) {
    const ph = (x / W * span - 0.5) / d.duration_s, env = ph > 0 && ph < 1 ? Math.sin(ph * Math.PI) * 0.85 : 0, f = d.f0 + d.sweep * ph;
    for (let y = 0; y < H; y++) {
      const hz = hzAt[y];
      let v = (0.22 * (1 - hz / 1000) + 0.06) * (0.5 + noise());
      if (env) v += env * Math.exp(-Math.pow((hz - f) / 22, 2));
      const [r, gg, b] = magmaRGB(v), o = (y * W + x) * 4;
      px[o] = r; px[o + 1] = gg; px[o + 2] = b; px[o + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
}

// 8 kHz WAV of a live call, as an object URL.
export function wavUrl(d: CallParams) {
  const sr = 8000, n = Math.round(sr * (d.duration_s + 0.6)), out = new Int16Array(n), noise = mulberry(hash(d.id) ^ 7);
  let phase = 0;
  for (let i = 0; i < n; i++) {
    const t = i / sr - 0.3, ph = t / d.duration_s, env = ph > 0 && ph < 1 ? Math.sin(ph * Math.PI) * 0.7 : 0;
    phase += 2 * Math.PI * (d.f0 + d.sweep * Math.max(0, Math.min(1, ph))) / sr;
    out[i] = Math.max(-1, Math.min(1, (noise() - 0.5) * 0.12 + env * Math.sin(phase))) * 32767;
  }
  const buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); str(8, "WAVE"); str(12, "fmt "); v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, "data"); v.setUint32(40, n * 2, true);
  new Int16Array(buf, 44).set(out);
  return URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
}
