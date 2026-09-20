const REPO = "https://github.com/2900xt/keiko-hackMIT";

export default function Landing() {
  return (
    <main className="landing">
      <a className="wordmark" href="./" aria-label="Keiko home">
        <svg className="mark" viewBox="0 0 32 32" aria-hidden="true">
          <circle cx="16" cy="16" r="4" />
          <circle cx="16" cy="16" r="9" fill="none" stroke="currentColor" strokeWidth="2" opacity=".45" />
          <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="2" opacity=".18" />
        </svg>
        Keiko
      </a>
      <h1 className="hero-title">Hydrophone buoys that hear whales.</h1>
      <p className="hero-lead">Underwater sound in, a live map of detections out.</p>
      <div className="hero-cta">
        <a className="btn" href="app/">Open the map</a>
        <a className="btn btn-quiet" href={REPO}>GitHub</a>
      </div>
      <p className="statline">1 buoy · Charles River · 8 kHz · CNN on the buoy</p>
    </main>
  );
}
