"use client";
import { useEffect, useRef, useState } from "react";

// "Ask Keiko": a small chat panel over the app that sends questions to elastic/ask_server.py, where Claude queries
// the hydrophone indices (ES|QL, kNN, ELSER) and answers. The server keeps the conversation per `session`, so
// follow-ups work. Served from NEXT_PUBLIC_KEIKO_ASK (in `npm run dev`: http://localhost:8766); the static build
// has no server unless that is set at build time, in which case the button is not rendered at all.
const ASK_URL = process.env.NEXT_PUBLIC_KEIKO_ASK ?? (process.env.NODE_ENV === "development" ? "http://localhost:8766" : "");

const STARTERS = [
  "What has been on the hydrophone in the last hour?",
  "Any right whales today?",
  "Which buoy is noisiest at night?",
];

interface Msg { role: "user" | "bot"; text: string; error?: boolean }

// The answers are plain sentences with the odd **number** or `field` in them; that is all the markdown rendered.
function rich(text: string) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) =>
    part.startsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong>
    : part.startsWith("`") ? <code key={i}>{part.slice(1, -1)}</code>
    : part);
}

export default function Ask() {
  const [open, setOpen] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null); // null = not checked yet
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const session = useRef<string>("");
  const input = useRef<HTMLInputElement>(null);
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => { session.current = crypto.randomUUID(); }, []);

  // Probe the server when the panel opens (and again on each open, so starting it later just works).
  useEffect(() => {
    if (!open) return;
    let alive = true;
    fetch(ASK_URL + "/health").then((r) => alive && setOnline(r.ok)).catch(() => alive && setOnline(false));
    input.current?.focus();
    return () => { alive = false; };
  }, [open]);

  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }); }, [msgs, busy]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    setQ("");
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    try {
      const r = await fetch(ASK_URL + "/ask", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session: session.current }),
      });
      const j = (await r.json().catch(() => ({}))) as { answer?: string; error?: string };
      if (!r.ok || !j.answer) throw new Error(j.error || "the server answered " + r.status);
      setMsgs((m) => [...m, { role: "bot", text: j.answer! }]);
      setOnline(true);
    } catch (e) {
      const why = e instanceof TypeError ? "can't reach the ask server" : (e as Error).message;
      setMsgs((m) => [...m, { role: "bot", text: "Sorry — " + why + ".", error: true }]);
      if (e instanceof TypeError) setOnline(false);
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  };

  if (!ASK_URL) return null;

  return (
    <div className="ask">
      {open && (
        <section id="ask-panel" className="ask-panel" role="dialog" aria-label="Ask Keiko">
          <div className="ask-head">
            <div>
              <div className="eyebrow">Ask Keiko</div>
              <p className="meta">Claude answers from the hydrophone data in Elasticsearch.</p>
            </div>
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => setOpen(false)} aria-label="Close">✕</button>
          </div>
          <div className="ask-log" ref={log} role="log" aria-live="polite">
            {online === false && (
              <p className="ask-offline">
                The ask server isn&rsquo;t answering at <code>{ASK_URL}</code>. Start it with <code>python3 elastic/ask_server.py</code>.
              </p>
            )}
            {msgs.length === 0 && (
              <div className="ask-starters">
                {STARTERS.map((s) => (
                  <button key={s} type="button" className="ask-starter" onClick={() => send(s)} disabled={busy}>{s}</button>
                ))}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={"ask-msg " + m.role + (m.error ? " error" : "")}>{m.role === "bot" ? rich(m.text) : m.text}</div>
            ))}
            {busy && <div className="ask-msg bot ask-busy" aria-label="Thinking"><i /><i /><i /></div>}
          </div>
          <form className="ask-form" onSubmit={(e) => { e.preventDefault(); send(q); }}>
            <input
              ref={input} className="ask-input" value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Ask about the detections…" aria-label="Your question" maxLength={2000} disabled={busy}
            />
            <button type="submit" className="btn" disabled={busy || !q.trim()}>Ask</button>
          </form>
        </section>
      )}
      <button
        type="button" className={"ask-fab" + (open ? " open" : "")} onClick={() => setOpen((o) => !o)}
        aria-expanded={open} aria-controls="ask-panel"
      >
        <span aria-hidden="true">💬</span> Ask
      </button>
    </div>
  );
}
