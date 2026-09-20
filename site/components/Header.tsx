"use client";
import type { Link, View } from "./KeikoApp";

interface Props { view: View; count: number; link: Link; linkWord: string; now: number | null; onSkip: () => void }

export default function Header({ view, count, link, linkWord, now, onSkip }: Props) {
  const go = (v: View) => () => { location.hash = v; };
  // The tab is called "Live"; the connection is "Online", so one word never means two things.
  const status = linkWord[0].toUpperCase() + linkWord.slice(1);
  return (
    <header className="top">
      <button type="button" className="skip" onClick={onSkip}>Skip to content</button>
      <div className="top-left">
        <a className="wordmark" href="#live" aria-label="Keiko home">
          <svg className="mark" viewBox="0 0 32 32" aria-hidden="true">
            <circle cx="16" cy="16" r="4" />
            <circle cx="16" cy="16" r="9" fill="none" stroke="currentColor" strokeWidth="2" opacity=".45" />
            <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="2" opacity=".18" />
          </svg>
          Keiko
        </a>
        <nav className="tabs" aria-label="Sections">
          <button className="tab" type="button" aria-current={view === "live" ? "page" : undefined} onClick={go("live")}>Live</button>
          <button className="tab" type="button" aria-current={view === "db" ? "page" : undefined} onClick={go("db")}>
            Database <span className="count">{count}</span>
          </button>
        </nav>
      </div>
      <div className="top-right">
        <span className={"live " + link} role="status" aria-live="polite">
          <span className="live-dot" aria-hidden="true" />
          <span>{status}</span>
        </span>
        <span className="clock">{now ? new Date(now).toLocaleTimeString() : "--:--:--"}</span>
      </div>
    </header>
  );
}
