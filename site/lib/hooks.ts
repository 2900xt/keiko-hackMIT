"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Feed, FeedEvents, FeedHandler } from "./feed";
import { startLiveAudio, type LiveAudio } from "./audio";

// Subscribe to one feed event for the life of the component. The handler is
// read through a ref so callers can pass a fresh closure every render.
export function useFeedEvent<K extends keyof FeedEvents>(feed: Feed, type: K, handler: FeedHandler<K>) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => feed.on(type, (p) => ref.current(p)), [feed, type]);
}

// Wall clock, ticking every `ms`. null until mounted so the server render and
// the first client render agree.
export function useNow(ms = 1000) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

// Smoothed hydrophone level in dB, updated on every audio frame (20 / s).
export function useAudioLevel(feed: Feed) {
  const [level, setLevel] = useState<number | null>(null);
  const smooth = useRef(-60);
  useFeedEvent(feed, "audio", (a) => {
    smooth.current += (a.level_db - smooth.current) * 0.2;
    setLevel(smooth.current);
  });
  return level;
}

// Rendered size of an element, via ResizeObserver.
export function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setSize({ width: el.clientWidth, height: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

// One shared <audio> element; whichever button started it shows the stop
// state. A clip that fails to load is remembered so its button can say so.
export function usePlayer() {
  const player = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    const a = new Audio();
    player.current = a;
    const ended = () => setPlaying(null);
    const error = () => { setPlaying(null); setFailed(a.src); };
    a.addEventListener("ended", ended);
    a.addEventListener("error", error);
    return () => { a.removeEventListener("ended", ended); a.removeEventListener("error", error); a.pause(); player.current = null; };
  }, []);
  function toggle(src: string) {
    const a = player.current;
    if (!a) return;
    if (playing === src) { a.pause(); setPlaying(null); return; }
    setFailed(null);
    a.pause(); a.src = src;
    a.play().then(() => setPlaying(src), () => { setPlaying(null); setFailed(src); });
  }
  return { playing, failed, toggle };
}

// Live hydrophone audio on/off. Starting must happen inside the click (the
// browser's autoplay rule), so the audio graph is built in `toggle`, not in an
// effect; it is torn down on unmount. `supported` is false where Web Audio is
// missing, so the button can hide itself.
export function useLiveSound(feed: Feed) {
  const live = useRef<LiveAudio | null>(null);
  const [on, setOn] = useState(false);
  const [supported, setSupported] = useState(true);
  useEffect(() => {
    setSupported("AudioContext" in window || "webkitAudioContext" in window);
    return () => { live.current?.stop(); live.current = null; };
  }, []);
  function toggle() {
    if (live.current) { live.current.stop(); live.current = null; setOn(false); return; }
    const a = startLiveAudio(feed);
    if (!a) { setSupported(false); return; }
    live.current = a; setOn(true);
  }
  return { on, supported, toggle };
}
