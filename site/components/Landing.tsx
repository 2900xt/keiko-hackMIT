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
          <span className="mark" aria-hidden="true">🐋</span>
          Keiko
        </a>
        <h1 className="hero-title">Low-cost acoustic buoys for monitoring whales in the waters you protect.</h1>
        <p className="hero-sub">
          A piezo hydrophone on an Arduino UNO Q hears the harbour; a whale CNN names the species; Elasticsearch makes every
          call searchable, mappable, and worth an alert when a right whale is on the shipping lane.
        </p>
        <div className="hero-cta">
          <a className="btn" href="app/">Open the map</a>
          <a className="btn btn-quiet" href="app/#db">Detection database</a>
          <a className="btn btn-quiet" href={REPO}>GitHub</a>
        </div>
        <dl className="hero-stats" aria-label="At a glance">
          <div><dt>22</dt><dd>species classes</dd></div>
          <div><dt>126k</dt><dd>training clips</dd></div>
          <div><dt>3</dt><dd>hydrophone nodes</dd></div>
          <div><dt>0.96</dt><dd>right-whale F1</dd></div>
        </dl>
      </div>
    </main>
  );
}
