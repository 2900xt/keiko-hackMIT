# Keiko on Elastic

Elasticsearch is where the hydrophone stream stops being audio and becomes something you can ask questions of.
Built for the HackMIT 2026 **Elastic — Find the Signal** challenge (*best use of Elasticsearch to turn complex,
messy data into insights, answers or actions*).

```
pipeline --elastic ──► keiko-windows      every 1.5 s: label, 22 class probs, level/peak/centroid/flatness, packet loss
                   └─► keiko-detections   every event: species, confidence, geo_point, TDOA fix, 512-d CNN embedding,
                                          a sentence for ELSER
                              │
        ┌─────────────────────┼──────────────────────┬─────────────────────┬──────────────────┐
   ES|QL (queries.esql)   kNN "sounds like"    semantic_text / ELSER   ML anomaly job     alert rule → webhook
   Kibana Lens + Maps     ask.py --similar     ask.py --semantic       keiko-soundscape   "right whale: slow to 10 kn"
                                     ask.py  — Claude writes the ES|QL, runs it, answers
```

**Messy in:** a 3.3 kHz ADC stream over lossy UDP from a buoy, a classifier that is wrong a quarter of the time on
noise, synthetic and field recordings mixed in one CSV. **Insight out:** what species, when, where, how the
soundscape is drifting, which windows are *unusual*, in plain English.

| | |
|---|---|
| `keiko_es.py` | client, doc shapes (`detection_doc`, `window_doc`, `describe`), buffered bulk writer, ES\|QL / kNN / semantic reads |
| `features.py` | spectral descriptors per window; the CNN's pooled 512-d activations as the embedding |
| `mappings/*.json` | index templates: `geo_point`, `dense_vector` (cosine), `semantic_text`, dynamic `probs.*` floats |
| `setup.py` | provisions everything: templates, indices, ML job + datafeed, Kibana data views, ES\|QL alert rule (+ webhook) |
| `backfill.py` | loads `pipeline/out/events.jsonl` + `site/data/detections.csv`, re-running the CNN on each clip |
| `ask.py` | the agent (Claude ⇄ ES\|QL / kNN / ELSER tools) and the no-LLM `--esql` `--similar` `--semantic` `--anomalies` modes |
| `ask_server.py` | HTTP front for `ask.py` (`POST /ask`), the website's "Ask Keiko" chat panel |
| `queries.esql` | 11 ES\|QL queries: the dashboard panels and the demo questions |
| `kibana/dashboard.md` | the six-panel dashboard recipe + alerting |
| `test_elastic.py` | unit tests (docs, features, guard) + an integration round-trip against a real cluster |

## Setup

1. Elastic Cloud trial (sponsor credit): <https://www.elastic.co/cloud/cloud-trial-overview/30-days>. Create a
   deployment (any size; ML is on by default), then *Manage → API keys → create* with write access.
2. `cp .env.example .env` and fill in `ELASTIC_URL` (the Elasticsearch endpoint), `ELASTIC_API_KEY`, `KIBANA_URL`,
   `ANTHROPIC_API_KEY` (for `ask.py`), optionally `KEIKO_WEBHOOK_URL` (Discord/Slack) for the alert.
3. Python: the pipeline venv plus two packages.

```bash
cd ../pipeline && make venv                         # once, if not done
../.venv/bin/pip install -r ../elastic/requirements.txt
cd ../elastic
../.venv/bin/python setup.py                        # indices, ML job, data views, rule
../.venv/bin/python backfill.py                     # what we already recorded, with embeddings
../.venv/bin/python setup.py --status
```

Without ML nodes (self-hosted basic): `setup.py --no-elser --no-ml`; `description` becomes plain `text` and
`--semantic` falls back to a match query.

## Live

```bash
cd ../pipeline && make demo ARGS="--elastic"        # humpback loop -> windows + events into Elastic every few seconds
cd ../pipeline && make live ARGS="--elastic"        # the buoy
```

Both also accept `--server ws://…` (the map) and `--archive` (the site) at the same time.

## Ask

```bash
../.venv/bin/python ask.py "what has been on the hydrophone in the last hour, and how sure are we?"
../.venv/bin/python ask.py -v "is the noise floor at KEIKO-01 higher tonight than this afternoon?"
../.venv/bin/python ask.py "find three calls that sound like KEIKO-01-20260920T073538 and say what they have in common"
../.venv/bin/python ask.py --similar KEIKO-01-20260920T073538       # kNN, no LLM
../.venv/bin/python ask.py --semantic "long low tonal call at night"  # ELSER, no LLM
../.venv/bin/python ask.py --anomalies                                # ML job records
../.venv/bin/python ask.py --esql 'FROM keiko-windows | STATS n = COUNT(*), db = AVG(audio.rms_db) BY buoy_id'
../.venv/bin/python ask_server.py -v      # the same agent behind http://localhost:8766/ask for the site's Ask panel
```

`ask_server.py` is the website's chatbot: `POST /ask {question, session}` runs `ask()` and keeps one conversation per
`session`, so follow-ups work. The site posts to `NEXT_PUBLIC_KEIKO_ASK` (`http://localhost:8766` in `npm run dev`; unset
in the static build, which hides the button — set it at build time to a tunnel to this server for a deployed demo).

`ask.py` gives Claude (`claude-opus-5`) the two index schemas and an ES|QL cheat sheet, and three tools. It only
runs `FROM keiko-*` queries. `-v` prints every query it tries — good for the demo.

## What the judges should see (5 min)

1. `make demo ARGS="--elastic"` running; Kibana Discover on `keiko-windows` auto-refreshing: the raw, noisy stream.
2. Dashboard: detections by species, the map, soundscape level vs whale share, stream loss.
3. `ask.py --similar <id>`: kNN over the CNN embedding finds the same song bout's other events.
4. `ask.py --semantic "…"`: ELSER finds calls by how they were described, not by keyword.
5. Anomaly Explorer: the job flags the moment the loop started (level jump) — the "unlabelled sound" story.
6. `ask.py "…"`: the agent answers a question none of the panels were built for, with the ES|QL it wrote.
7. The right-whale rule firing to Discord: an *action*, the reason the buoys exist.

## Tests

```bash
../.venv/bin/python test_elastic.py                # unit tests always; integration when .env points at a cluster
```
