const REPO = "https://github.com/2900xt/keiko-hackMIT";

const STEPS = [
  { n: "01", title: "Listen", body: "A hydrophone under each buoy streams raw audio over Wi-Fi — nRF7002, ESP32-S3, or the UNO Q's own MCU." },
  { n: "02", title: "Detect", body: "A CNN on the UNO Q's Linux side scores 3 s windows and turns runs of whale calls into timestamped events." },
  { n: "03", title: "Locate", body: "Arrival-time differences across buoys place each call on the water; the map fades detections with age." },
  { n: "04", title: "Search", body: "Every event lands in Elasticsearch with an embedding, so you can query by species, time, or similar sound." },
];

export default function Landing() {
  return (
    <>
      <header className="top">
        <div className="top-left">
          <a className="wordmark" href="./" aria-label="Keiko home">
            <svg className="mark" viewBox="0 0 32 32" aria-hidden="true">
              <circle cx="16" cy="16" r="4" />
              <circle cx="16" cy="16" r="9" fill="none" stroke="currentColor" strokeWidth="2" opacity=".45" />
              <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="2" opacity=".18" />
            </svg>
            Keiko
          </a>
        </div>
        <div className="top-right">
          <a className="btn-link" href={REPO}>GitHub</a>
          <a className="btn" href="app/">Open live map</a>
        </div>
      </header>

      <main className="landing">
        <section className="hero">
          <div className="eyebrow">Acoustic buoys · HackMIT 2026</div>
          <h1 className="hero-title">Hear what&rsquo;s happening on the water.</h1>
          <p className="hero-lead">
            Keiko is a network of hydrophone buoys that turns underwater sound into a live, searchable stream of
            whale detections — where they were heard, how confident we are, and what they sounded like.
          </p>
          <div className="hero-cta">
            <a className="btn" href="app/">Open live map</a>
            <a className="btn btn-quiet" href="app/#db">Browse detections</a>
          </div>
        </section>

        <section className="summary landing-stats" aria-label="At a glance">
          <div className="tile"><div className="eyebrow">Buoys</div><div className="num">1</div><div className="unit">Charles River, off MIT</div></div>
          <div className="tile"><div className="eyebrow">Sample rate</div><div className="num">8 kHz</div><div className="unit">piezo disc array</div></div>
          <div className="tile"><div className="eyebrow">Detector</div><div className="num">CNN</div><div className="unit">on the buoy, 3 s windows</div></div>
          <div className="tile"><div className="eyebrow">Database</div><div className="num">Open</div><div className="unit">CSV + JSON + clips on GitHub</div></div>
        </section>

        <section className="steps" aria-label="How it works">
          <div className="eyebrow">How it works</div>
          <ol className="step-list">
            {STEPS.map((s) => (
              <li key={s.n} className="step">
                <div className="step-n">{s.n}</div>
                <h2 className="step-title">{s.title}</h2>
                <p className="meta">{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="pipeline" aria-label="Pipeline">
          <div className="eyebrow">Buoy to browser</div>
          <pre className="pipe">
{`hydrophone ──> node (UDP/Wi-Fi) ──> UNO Q: detector → classifier → embedding → TDOA ──> Elasticsearch
                                                                                        │
                                                    this site · Kibana · ES|QL + kNN agent · alerting`}
          </pre>
        </section>

        <section className="cta">
          <h2 className="cta-title">Built in the open.</h2>
          <p className="meta">Firmware, pipeline, enclosure, and the detection database are all in one repo.</p>
          <div className="hero-cta">
            <a className="btn btn-quiet" href={REPO}>View on GitHub</a>
            <a className="btn btn-quiet" href={REPO + "/tree/main/site/data"}>Download the data</a>
          </div>
        </section>
      </main>

      <footer className="foot">
        <span>Keiko · Moby Labs</span>
        <span>Taha Rawjani · Matthew Li</span>
      </footer>
    </>
  );
}
