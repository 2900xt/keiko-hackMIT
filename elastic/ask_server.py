#!/usr/bin/env python3
"""The website's "Ask Keiko" chatbot: a small HTTP front for ask.py. Claude writes ES|QL / kNN / ELSER queries against
the hydrophone indices, runs them, and answers; this server keeps one conversation per browser tab.

    python3 ask_server.py                 # http://0.0.0.0:8766  (the site's Ask panel posts here in dev)
    python3 ask_server.py --port 8766 -v  # -v prints the queries Claude runs

    POST /ask   {"question": "...", "session": "<any id>"}   ->  {"answer": "...", "session": "..."}
    GET  /health                                             ->  {"ok": true, "model": "..."}

Needs ELASTIC_URL + ELASTIC_API_KEY and ANTHROPIC_API_KEY (elastic/.env). The site reads NEXT_PUBLIC_KEIKO_ASK
(default http://localhost:8766 in `npm run dev`); for the static build, point it at a tunnel to this server.
CORS is wide open: the demo site is on GitHub Pages and the only thing here is read-only questions.
"""
import argparse
import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ask import MODEL, ask
from keiko_es import KeikoES, load_env

MAX_QUESTION = 2000
MAX_HISTORY = 40          # messages kept per session (tool calls count); trimmed at a question boundary
SESSION_TTL_S = 2 * 3600


class Sessions:
    """Conversation history per session id, so follow-ups ("and yesterday?") work. In memory, one process."""

    def __init__(self):
        self.lock = threading.Lock()
        self.by_id = {}   # id -> {"history": [...], "at": time, "busy": Lock}

    def get(self, sid):
        with self.lock:
            now = time.time()
            for k in [k for k, s in self.by_id.items() if now - s["at"] > SESSION_TTL_S]:
                del self.by_id[k]
            s = self.by_id.setdefault(sid, {"history": [], "at": now, "busy": threading.Lock()})
            s["at"] = now
            return s


def trim(history):
    """Drop the oldest turns once the history is long. Only cut where a user *question* starts, so a tool_use never
    loses its tool_result."""
    while len(history) > MAX_HISTORY:
        cut = next((i for i in range(1, len(history))
                    if history[i]["role"] == "user" and isinstance(history[i]["content"], str)), None)
        if cut is None:
            break
        del history[:cut]


class Handler(BaseHTTPRequestHandler):
    es = client = sessions = None
    verbose = False

    def log_message(self, fmt, *args):   # one line per question instead of the default access log
        pass

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            return self.send_json(200, {"ok": True, "model": MODEL})
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/ask":
            return self.send_json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
            question = str(req.get("question", "")).strip()
        except (ValueError, TypeError):
            return self.send_json(400, {"error": "bad JSON"})
        if not question:
            return self.send_json(400, {"error": "question is empty"})
        question = question[:MAX_QUESTION]
        sid = str(req.get("session") or uuid.uuid4())[:64]

        s = self.sessions.get(sid)
        if not s["busy"].acquire(blocking=False):
            return self.send_json(429, {"error": "still answering the previous question"})
        try:
            history = s["history"]
            mark = len(history)
            t0 = time.time()
            print(f"[{sid[:8]}] Q: {question}", flush=True)
            try:
                answer = ask(self.es, self.client, question, history, verbose=self.verbose)
            except Exception as e:
                del history[mark:]          # a failed turn leaves no dangling user message behind
                print(f"[{sid[:8]}] error: {e}", file=sys.stderr, flush=True)
                return self.send_json(502, {"error": f"{type(e).__name__}: {e}"})
            trim(history)
            print(f"[{sid[:8]}] A ({time.time() - t0:.1f}s): {answer[:200]}", flush=True)
            self.send_json(200, {"answer": answer, "session": sid})
        finally:
            s["busy"].release()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0"); ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("-v", "--verbose", action="store_true", help="show the queries Claude runs")
    a = ap.parse_args()
    load_env()
    import anthropic
    Handler.es = KeikoES.from_env()
    Handler.client = anthropic.Anthropic()
    Handler.sessions = Sessions()
    Handler.verbose = a.verbose
    print(f"keiko ask server on http://{a.host}:{a.port}  model: {MODEL}  (ctrl-c to stop)", flush=True)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
