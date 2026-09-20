// Plays the feed's audio frames through Web Audio. Each frame's `pcm` chunk is
// resampled from AUDIO_RATE to the context rate (linear, carried across chunk
// edges so the stream stays gapless) and scheduled right after the previous
// one. A short lead absorbs timer jitter; if the source stalls (hidden tab) the
// clock restarts, and if it runs ahead by more than MAX_LAG frames are dropped.

import { AUDIO_RATE, type AudioFrame, type Feed } from "./feed";

export interface LiveAudio { stop(): void }

const LEAD = 0.12;     // s of buffer before the first chunk plays
const MAX_LAG = 0.5;   // s the schedule may run ahead of the clock before dropping frames
const VOLUME = 0.6;
const FADE = 0.06;     // s, in and out, so toggling never clicks
const LOWPASS_HZ = 950; // just under the feed's Nyquist; removes resampling images

type AudioContextCtor = typeof AudioContext;

export function startLiveAudio(feed: Feed): LiveAudio | null {
  const AC: AudioContextCtor | undefined =
    typeof AudioContext !== "undefined" ? AudioContext : (window as { webkitAudioContext?: AudioContextCtor }).webkitAudioContext;
  if (!AC) return null;
  const ctx = new AC();
  void ctx.resume(); // Safari can hand back a suspended context even inside a click

  const master = ctx.createGain();
  master.gain.setValueAtTime(0, ctx.currentTime);
  master.gain.linearRampToValueAtTime(VOLUME, ctx.currentTime + FADE);
  const lowpass = ctx.createBiquadFilter();
  lowpass.type = "lowpass"; lowpass.frequency.value = LOWPASS_HZ; lowpass.Q.value = 0.7;
  master.connect(lowpass); lowpass.connect(ctx.destination);

  const step = AUDIO_RATE / ctx.sampleRate; // source samples per output sample
  let last = 0, p0 = 0;                     // previous chunk's final sample; first output position in this chunk (-1..0]
  function resample(src: Float32Array) {
    const n = src.length, out = new Float32Array(Math.ceil((n - p0) / step) + 1);
    let m = 0, p = p0;
    while (p <= n - 1) {
      let v: number;
      if (p < 0) v = last + (src[0] - last) * (p + 1);
      else { const i = p | 0, f = p - i; v = i + 1 < n ? src[i] + (src[i + 1] - src[i]) * f : src[i]; }
      out[m++] = v; p += step;
    }
    p0 = p - n; last = src[n - 1];
    return out.subarray(0, m);
  }

  let next = 0;
  function onFrame(a: AudioFrame) {
    if (ctx.state === "closed" || !a.pcm?.length) return;
    const now = ctx.currentTime;
    if (next < now) next = now + LEAD;         // first frame, or the source stalled
    else if (next - now > MAX_LAG) return;     // running ahead: drop to catch up
    const data = resample(a.pcm);
    if (!data.length) return;
    const buf = ctx.createBuffer(1, data.length, ctx.sampleRate);
    buf.copyToChannel(data, 0);
    const src = ctx.createBufferSource();
    src.buffer = buf; src.connect(master); src.start(next);
    next += data.length / ctx.sampleRate;
  }
  const off = feed.on("audio", onFrame);

  let stopped = false;
  return {
    stop() {
      if (stopped) return;
      stopped = true;
      off();
      const t = ctx.currentTime;
      master.gain.cancelScheduledValues(t);
      master.gain.setValueAtTime(master.gain.value, t);
      master.gain.linearRampToValueAtTime(0, t + FADE);
      setTimeout(() => { void ctx.close(); }, FADE * 1000 + 40);
    },
  };
}
