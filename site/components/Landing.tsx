const REPO = "https://github.com/2900xt/keiko-hackMIT";

// One wave path, repeated at three depths and drifted sideways by CSS.
const WAVE = "M0 60 C 240 20, 480 100, 720 60 S 1200 20, 1440 60 S 1920 100, 2160 60 S 2640 20, 2880 60 V 200 H 0 Z";

export default function Landing() {
  return (
    <main className="landing">
      <svg className="waves" viewBox="0 0 1440 200" preserveAspectRatio="none" aria-hidden="true">
        <path className="wave wave-1" d={WAVE} />
        <path className="wave wave-2" d={WAVE} />
        <path className="wave wave-3" d={WAVE} />
      </svg>
      <div className="hero">
        <a className="wordmark" href="./" aria-label="Keiko home">
          <svg className="mark" viewBox="0 0 32 32" aria-hidden="true">
            <circle cx="16" cy="16" r="4" />
            <circle cx="16" cy="16" r="9" fill="none" stroke="currentColor" strokeWidth="2" opacity=".45" />
            <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="2" opacity=".18" />
          </svg>
          Keiko
        </a>
        <h1 className="hero-title">Low-cost acoustic buoys for monitoring whales in the waters you protect.</h1>
        <div className="hero-cta">
          <a className="btn" href="app/">Open the map</a>
          <a className="btn btn-quiet" href={REPO}>GitHub</a>
        </div>
      </div>
    </main>
  );
}
