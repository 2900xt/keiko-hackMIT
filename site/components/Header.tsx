"use client";
import type { Link, View } from "./KeikoApp";

interface Props { view: View; count: number; link: Link; linkWord: string; now: number | null }

export default function Header({ view, count, link, linkWord, now }: Props) {
  const go = (v: View) => () => { location.hash = v; };
  return (
    <header className="top">
      <div className="top-left">
        <a className="wordmark" href="../" aria-label="Keiko home">
          <svg className="mark" viewBox="0 0 32 32" aria-hidden="true">
            <circle cx="16" cy="16" r="4" />
            <circle cx="16" cy="16" r="9" fill="none" stroke="currentColor" strokeWidth="2" opacity=".45" />
            <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="2" opacity=".18" />
          </svg>
          Keiko
        </a>
        <nav className="tabs" aria-label="Sections">
          <button className={"tab" + (view === "live" ? " on" : "")} type="button" onClick={go("live")}>Live</button>
          <button className={"tab" + (view === "db" ? " on" : "")} type="button" onClick={go("db")}>
            Database <span className="count">{count}</span>
          </button>
        </nav>
      </div>
      <div className="top-right">
        <span className={"live " + link}>
          <span className="live-dot" />
          <span>{link === "on" ? "Live" : linkWord[0].toUpperCase() + linkWord.slice(1)}</span>
        </span>
        <span className="clock">{now ? new Date(now).toLocaleTimeString() : "--:--:--"}</span>
      </div>
    </header>
  );
}
