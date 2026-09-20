#!/usr/bin/env python3
"""Ask the hydrophone data a question. Claude writes ES|QL against keiko-detections / keiko-windows, runs it, looks
at the table, and answers — and can pull in kNN "sounds like this" and semantic (ELSER) search when the question
calls for it.

    python3 ask.py "what has been on the hydrophone in the last hour?"
    python3 ask.py "which buoy is noisiest at night, and did that change today?"
    python3 ask.py "find calls that sound like KEIKO-01-20260920T073538"
    python3 ask.py                                   # REPL
    python3 ask.py --esql 'FROM keiko-detections | STATS n = COUNT(*) BY species'     # no LLM, just run it
    python3 ask.py --similar KEIKO-01-20260920T073538                                 # no LLM, kNN
    python3 ask.py --semantic "long low moan at night"                                # no LLM, ELSER

Needs ELASTIC_URL + ELASTIC_API_KEY, and ANTHROPIC_API_KEY for the questions (elastic/.env).
"""
import argparse
import json
import os
import re
import sys

from keiko_es import DETECTIONS, WINDOWS, KeikoES, load_env

MODEL = "claude-opus-5"
MAX_ROWS = 60

SYSTEM = f"""You are Keiko's analyst. Keiko is a network of hydrophone buoys off Massachusetts; a CNN classifies every
3 s window of sound and runs of whale windows become detections. All of it is in Elasticsearch. Answer questions by
querying the data with the tools, then reply in a few plain sentences with the numbers that matter. If the data
does not support an answer, say so. Times in the data are UTC.

INDEX {DETECTIONS} — one doc per detection (event)
  @timestamp date, id keyword, buoy_id keyword, buoy_name keyword, species keyword (common name, e.g. "humpback whale",
  "North Atlantic right whale", "fin whale", "unknown"), model_class keyword (Latin, e.g. Megaptera_novaeangliae),
  confidence float 0-1, duration_s float, windows int, location geo_point (TDOA fix if any, else the buoy),
  buoy_location geo_point, source keyword ("field" | "synthetic"), track_id keyword, fix.err_m float, fix.method keyword,
  audio.rms_db float (dBFS level), audio.peak_hz, audio.centroid_hz, audio.bandwidth_hz, audio.flatness (0 tone .. 1 noise),
  probs.<Latin_class> float (all 22 classifier outputs, incl. probs.no_whale_noise, probs.no_whale_biophony),
  description (text, for semantic search), embedding dense_vector (kNN only, never SELECT it).

INDEX {WINDOWS} — one doc per classifier window (every 1.5 s while a buoy streams; noisy, high volume)
  @timestamp date, buoy_id keyword, label keyword (Latin class or "no_whale"), confidence float, whale boolean,
  top_class keyword, top_p float, in_event boolean, source keyword, location geo_point, sample_rate_hz float,
  audio.rms_db, audio.peak_hz, audio.centroid_hz, audio.bandwidth_hz, audio.flatness, probs.<class>,
  net.packets int, net.dropped_packets int (UDP loss from the buoy in that window).

ES|QL cheat sheet (this cluster only accepts read-only queries starting with FROM):
  FROM {DETECTIONS} | WHERE @timestamp > NOW() - 1 hour | STATS n = COUNT(*), c = AVG(confidence) BY species | SORT n DESC
  FROM {WINDOWS} | STATS level = AVG(audio.rms_db), whale = SUM(CASE(whale, 1, 0)) BY buoy_id, h = BUCKET(@timestamp, 1 hour) | SORT h
  FROM {DETECTIONS} | EVAL hour = DATE_EXTRACT("hour_of_day", @timestamp) | STATS n = COUNT(*) BY hour | SORT hour
  FROM {DETECTIONS} | WHERE species LIKE "*right whale*" AND confidence >= 0.7 | KEEP @timestamp, buoy_id, confidence, duration_s | SORT @timestamp DESC | LIMIT 20
  FROM {WINDOWS} | STATS drops = SUM(net.dropped_packets), pk = SUM(net.packets) BY buoy_id | EVAL loss_pct = 100.0 * drops / pk
  Functions: COUNT, COUNT_DISTINCT, SUM, AVG, MIN, MAX, MEDIAN, PERCENTILE(f, 95), BUCKET(@timestamp, 15 minutes),
  DATE_TRUNC(1 hour, @timestamp), DATE_EXTRACT("hour_of_day", @timestamp), DATE_FORMAT("yyyy-MM-dd HH:mm", @timestamp),
  CASE(cond, a, b), ROUND(x, 2), TO_STRING, ST_DISTANCE(location, TO_GEOPOINT("POINT(-70.28 42.33)")) in metres,
  ST_CENTROID_AGG(location). Keyword equality is ==, patterns use LIKE with *. Always LIMIT unless aggregating.
  There is no JOIN: run two queries instead. Prefer STATS over pulling rows. Field names with dots need no quoting.

Species the classifier knows: bowhead, common minke, Antarctic minke, blue, fin, beluga, common dolphin,
North Atlantic right whale, pilot whale, Risso's dolphin, Fraser's dolphin, white-sided dolphin, humpback whale,
killer whale, sperm whale, false killer whale, spotted/spinner dolphin, bottlenose dolphin, baleen/toothed (unidentified).
Right whales are the ones NOAA cares about (ship-strike rules: 10 kn in a seasonal management area).

Rules: never guess numbers — query. Start with a broad STATS to see what exists if unsure. Keep queries small.
When you have enough, answer; do not narrate your queries."""

TOOLS = [
    {"name": "esql", "description": "Run a read-only ES|QL query and get the result table (max 60 rows). Use it for anything countable.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "ES|QL starting with FROM"}},
                      "required": ["query"], "additionalProperties": False}, "strict": True},
    {"name": "similar_sounds", "description": "kNN over the CNN audio embedding: the k detections that sound most like the given detection id.",
     "input_schema": {"type": "object", "properties": {"detection_id": {"type": "string"}, "k": {"type": "integer"}},
                      "required": ["detection_id", "k"], "additionalProperties": False}, "strict": True},
    {"name": "semantic_search", "description": "Semantic (ELSER) search over each detection's plain-language description: use for fuzzy asks like 'long low moans at night near the harbour'.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}, "k": {"type": "integer"}},
                      "required": ["text", "k"], "additionalProperties": False}, "strict": True},
]

READ_ONLY = re.compile(r"^\s*FROM\s+keiko-\w+", re.IGNORECASE)


def guard(query):
    """Only FROM keiko-* pipelines; ES|QL has no writes, but the cluster key may be broader than this script."""
    if not READ_ONLY.match(query):
        raise ValueError("only `FROM keiko-...` queries are allowed")
    return query


def fmt_table(cols, rows, limit=MAX_ROWS):
    if not rows:
        return "(no rows)"
    rows = rows[:limit]
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
    line = lambda r: "  ".join(str(v).ljust(w) for v, w in zip(r, widths))
    out = [line(cols), line(["-" * w for w in widths])] + [line(r) for r in rows]
    return "\n".join(out) + (f"\n… {len(rows)} of more rows" if len(rows) == limit else "")


def slim(hits):
    keep = ("score", "id", "@timestamp", "buoy_id", "species", "confidence", "duration_s", "audio", "description")
    return [{k: h[k] for k in keep if k in h} for h in hits]


def run_tool(es, name, inp):
    if name == "esql":
        cols, rows = es.esql(guard(inp["query"]))
        return fmt_table(cols, rows)
    if name == "similar_sounds":
        return json.dumps(slim(es.similar(inp["detection_id"], k=min(int(inp.get("k") or 5), 20))), indent=1)
    if name == "semantic_search":
        return json.dumps(slim(es.semantic(inp["text"], k=min(int(inp.get("k") or 5), 20))), indent=1)
    raise ValueError(f"unknown tool {name}")


def ask(es, client, question, history=None, verbose=False):
    """One question -> answer text. `history` (a list) keeps the conversation across REPL turns."""
    import anthropic
    messages = history if history is not None else []
    messages.append({"role": "user", "content": question})
    while True:
        resp = client.messages.create(model=MODEL, max_tokens=4096, system=SYSTEM, tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            if verbose:
                print(f"   ⟶ {b.name} {json.dumps(b.input)}", file=sys.stderr, flush=True)
            try:
                out = run_tool(es, b.name, b.input); err = False
            except Exception as e:
                out, err = f"error: {e}", True
            if verbose:
                print("\n".join("     " + l for l in out.splitlines()[:12]), file=sys.stderr, flush=True)
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out[:12000], "is_error": err})
        messages.append({"role": "user", "content": results})
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?")
    ap.add_argument("--esql", help="run this ES|QL and print the table (no LLM)")
    ap.add_argument("--similar", metavar="ID", help="kNN neighbours of a detection (no LLM)")
    ap.add_argument("--semantic", metavar="TEXT", help="ELSER search over descriptions (no LLM)")
    ap.add_argument("--anomalies", action="store_true", help="latest ML anomalies (no LLM)")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("-v", "--verbose", action="store_true", help="show the queries Claude runs")
    a = ap.parse_args()
    load_env()
    es = KeikoES.from_env()

    if a.esql:
        cols, rows = es.esql(guard(a.esql)); print(fmt_table(cols, rows)); return
    if a.similar:
        for h in es.similar(a.similar, k=a.k):
            print(f"{h['score']:.3f}  {h['id']}  {h.get('species'):28s} conf {h.get('confidence')}  {h.get('description', '')[:90]}")
        return
    if a.semantic:
        for h in es.semantic(a.semantic, k=a.k):
            print(f"{h['score']:.3f}  {h['id']}  {h.get('species'):28s} {h.get('description', '')[:100]}")
        return
    if a.anomalies:
        for x in es.anomalies():
            print(f"{x['timestamp']}  score {x['score']:5.1f}  {x['detector']} [{x['by']}]  typical {x['typical']} -> actual {x['actual']}")
        return

    import anthropic
    client = anthropic.Anthropic()
    if a.question:
        print(ask(es, client, a.question, verbose=a.verbose)); return
    history = []
    print("keiko> ask about the hydrophone data (ctrl-d to quit)")
    while True:
        try:
            q = input("keiko> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if q:
            print(ask(es, client, q, history, verbose=a.verbose), "\n")


if __name__ == "__main__":
    main()
