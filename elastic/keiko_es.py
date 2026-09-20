#!/usr/bin/env python3
"""Keiko's Elasticsearch layer: the two indices, the doc shapes, a buffered writer for the pipeline, and the three
ways to ask the data a question (ES|QL, kNN over the audio embedding, semantic search over the description).

    from keiko_es import KeikoES
    es = KeikoES.from_env()                 # elastic/.env or ELASTIC_URL / ELASTIC_CLOUD_ID + ELASTIC_API_KEY
    es.ensure_indices()
    es.add_window(window_doc(...))          # every classifier window (1.5 s) -> keiko-windows, bulk-flushed
    es.add_detection(detection_doc(...))    # every event -> keiko-detections, indexed at once
    es.esql("FROM keiko-detections | STATS n = COUNT(*) BY species")
    es.similar("KEIKO-01-20260920T073538")  # kNN on the 512-d CNN embedding
    es.semantic("long low moan near the buoy at night")   # ELSER over `description`

Indices
    keiko-windows     one doc per classifier window: label, confidence, per-class probs, spectral descriptors,
                      packet loss. High volume, noisy — the raw material for the anomaly job and the dashboards.
    keiko-detections  one doc per event: species, confidence, geo_point, embedding (dense_vector), the TDOA fix
                      when the server produced one, and a sentence for semantic search.

Templates live in mappings/*.json; `setup.py` installs them and the ML job / alert rule on top.
"""
import json
import os
import pathlib
import time
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
DETECTIONS, WINDOWS = "keiko-detections", "keiko-windows"


# ---- config -----------------------------------------------------------------
def load_env(path=None):
    """Read KEY=value lines from elastic/.env into os.environ (existing variables win). No dependency needed."""
    p = pathlib.Path(path) if path else HERE / ".env"
    if not p.exists():
        return {}
    got = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v); got[k] = v
    return got


def connect(url=None, api_key=None, cloud_id=None, **kw):
    """An Elasticsearch client from explicit args or the environment. Raises if nothing points at a cluster."""
    from elasticsearch import Elasticsearch
    load_env()
    url = url or os.environ.get("ELASTIC_URL"); cloud_id = cloud_id or os.environ.get("ELASTIC_CLOUD_ID")
    api_key = api_key or os.environ.get("ELASTIC_API_KEY")
    if not (url or cloud_id):
        raise RuntimeError("no Elasticsearch configured: set ELASTIC_URL (or ELASTIC_CLOUD_ID) and ELASTIC_API_KEY, "
                           "e.g. in elastic/.env (see .env.example)")
    opts = {"request_timeout": 30, **kw}
    if api_key:
        opts["api_key"] = api_key
    return Elasticsearch(cloud_id=cloud_id, **opts) if cloud_id else Elasticsearch(url, **opts)


# ---- doc shapes -------------------------------------------------------------
def iso(t):
    """unix seconds -> ISO-8601 UTC with millis (what @timestamp wants)."""
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def describe(rec, audio=None, buoy_name=None):
    """A sentence about the event for `description` (semantic_text -> ELSER). Written for a reader, not a parser:
    the whole point is that "long low moan at night off Stellwagen" should find it."""
    when = rec.get("timestamp_utc", "")
    try:
        dt = datetime.strptime(when[:19], "%Y-%m-%dT%H:%M:%S")
        hour = dt.hour
        tod = "at night" if hour < 5 or hour >= 21 else "in the early morning" if hour < 9 else \
              "in the morning" if hour < 12 else "in the afternoon" if hour < 17 else "in the evening"
        when_txt = dt.strftime("%A %d %B %Y %H:%M UTC") + " " + tod
    except ValueError:
        when_txt = when
    conf = rec.get("confidence", 0.0)
    strength = "confident" if conf >= 0.85 else "probable" if conf >= 0.7 else "tentative"
    dur = rec.get("duration_s")
    length = "" if dur is None else ("brief " if dur < 4 else "long " if dur > 12 else "")
    where = f"buoy {rec.get('buoy_id', '?')}" + (f" ({buoy_name})" if buoy_name else "")
    parts = [f"{strength.capitalize()} {length}{rec.get('species', 'unknown')} call ({conf:.2f}) at {where} {when_txt}."]
    if dur is not None:
        parts.append(f"Lasted {dur:.1f} s over {rec.get('windows', '?')} classifier windows.")
    if audio:
        pk, cen = audio.get("peak_hz"), audio.get("centroid_hz")
        band = "very low frequency" if (pk or 0) < 100 else "low frequency" if (pk or 0) < 500 else \
               "mid frequency" if (pk or 0) < 2000 else "high frequency"
        tone = "tonal" if audio.get("flatness", 1) < 0.2 else "broadband" if audio.get("flatness", 0) > 0.5 else "mixed"
        parts.append(f"{band.capitalize()}, {tone} sound: peak {pk:.0f} Hz, centroid {cen:.0f} Hz, level {audio.get('rms_db', 0):.0f} dBFS.")
    if rec.get("fix"):
        parts.append(f"Localised by TDOA to within {rec['fix'].get('err_m', '?')} m.")
    if rec.get("notes"):
        parts.append(str(rec["notes"]))
    return " ".join(parts)


def detection_doc(rec, embedding=None, probs=None, audio=None, fix=None, buoy_name=None, source="field"):
    """keiko-detections doc from the pipeline's event record (the events.jsonl line) plus what the ES layer adds."""
    lat, lon = rec.get("latitude"), rec.get("longitude")
    doc = {
        "@timestamp": rec["timestamp_utc"], "id": rec["id"], "buoy_id": rec.get("buoy_id"),
        "species": rec.get("species", "unknown"), "model_class": rec.get("model_class"),
        "confidence": rec.get("confidence"), "duration_s": rec.get("duration_s"), "windows": rec.get("windows"),
        "sample_rate_hz": rec.get("sample_rate_hz"), "source": rec.get("source", source),
        "clip_path": rec.get("clip") or rec.get("clip_path"), "spectrogram_path": rec.get("spectrogram_path"),
        "notes": rec.get("notes"),
    }
    if buoy_name:
        doc["buoy_name"] = buoy_name
    if lat is not None and lon is not None:
        doc["buoy_location"] = {"lat": lat, "lon": lon}
        doc["location"] = {"lat": lat, "lon": lon}
    if fix:
        doc["fix"] = {k: fix[k] for k in ("err_m", "method", "truth_m_off", "simulated_buoys", "arrivals") if k in fix}
        if "lat" in fix and "lon" in fix:
            doc["location"] = {"lat": fix["lat"], "lon": fix["lon"]}     # the map shows the fix, the buoy stays in buoy_location
    if rec.get("track_id"):
        doc["track_id"] = rec["track_id"]
    if probs:
        doc["probs"] = {k: round(float(v), 4) for k, v in probs.items()}
    if audio:
        doc["audio"] = audio
    if embedding is not None:
        doc["embedding"] = [float(x) for x in embedding]
    doc["description"] = describe({**rec, "fix": fix}, audio, buoy_name)
    return {k: v for k, v in doc.items() if v is not None}


def window_doc(t, buoy, label, conf, whale, top, ptop, probs=None, audio=None, fs=None, node=0, net=None,
               in_event=False, source="field"):
    """keiko-windows doc for one classifier window ending at unix time `t`."""
    doc = {"@timestamp": iso(t), "buoy_id": buoy["id"], "node": node, "label": label, "confidence": round(float(conf), 4),
           "whale": bool(whale), "top_class": top, "top_p": round(float(ptop), 4), "in_event": bool(in_event), "source": source}
    if buoy.get("lat") is not None:
        doc["location"] = {"lat": buoy["lat"], "lon": buoy["lon"]}
    if fs:
        doc["sample_rate_hz"] = float(fs)
    if probs:
        doc["probs"] = {k: round(float(v), 4) for k, v in probs.items()}
    if audio:
        doc["audio"] = audio
    if net:
        doc["net"] = net
    return doc


# ---- client -----------------------------------------------------------------
class KeikoES:
    def __init__(self, es, flush_every=20, flush_s=3.0, quiet=False):
        self.es = es
        self.flush_every, self.flush_s, self.quiet = flush_every, flush_s, quiet
        self._buf = []; self._last_flush = time.time()
        self.stats = {"windows": 0, "detections": 0, "errors": 0}

    @classmethod
    def from_env(cls, **kw):
        return cls(connect(), **kw)

    # -- schema
    def ensure_indices(self, elser=None):
        """Install both index templates (idempotent) and create the indices so Kibana sees them before data arrives.
        elser=False maps `description` as plain text (clusters without ML / ELSER); default from KEIKO_ELSER."""
        if elser is None:
            elser = os.environ.get("KEIKO_ELSER", "1") not in ("0", "false", "no")
        for name in (DETECTIONS, WINDOWS):
            tpl = json.loads((HERE / "mappings" / f"{name}.json").read_text())
            props = tpl["template"]["mappings"]["properties"]
            if not elser and props.get("description", {}).get("type") == "semantic_text":
                props["description"] = {"type": "text"}
            self.es.indices.put_index_template(name=name, **tpl)
            if not self.es.indices.exists(index=name):
                self.es.indices.create(index=name)
        return elser

    # -- writes
    def add_window(self, doc):
        # deterministic id: a re-run of the backfill (or a replayed stream) overwrites instead of duplicating
        self._buf.append({"_index": WINDOWS, "_id": f"{doc['buoy_id']}-{doc['@timestamp']}", "_source": doc})
        if len(self._buf) >= self.flush_every or time.time() - self._last_flush >= self.flush_s:
            self.flush()

    def add_detection(self, doc, refresh=False):
        self.flush()
        try:
            self.es.index(index=DETECTIONS, id=doc["id"], document=doc, refresh="wait_for" if refresh else False)
            self.stats["detections"] += 1
        except Exception as e:                       # the pipeline must not die because the cluster hiccuped
            self.stats["errors"] += 1
            if not self.quiet:
                print(f"elastic: detection {doc.get('id')} failed: {e}", flush=True)

    def flush(self):
        if not self._buf:
            self._last_flush = time.time(); return
        from elasticsearch import helpers
        batch, self._buf = self._buf, []
        try:
            ok, errs = helpers.bulk(self.es, batch, raise_on_error=False, stats_only=False)
            self.stats["windows"] += ok
            if errs:
                self.stats["errors"] += len(errs)
                if not self.quiet:
                    print(f"elastic: {len(errs)} window docs rejected, first: {json.dumps(errs[0])[:300]}", flush=True)
        except Exception as e:
            self.stats["errors"] += len(batch)
            if not self.quiet:
                print(f"elastic: bulk of {len(batch)} failed: {e}", flush=True)
        self._last_flush = time.time()

    def close(self):
        self.flush()
        try: self.es.close()
        except Exception: pass

    # -- reads
    def esql(self, query, params=None):
        """Run an ES|QL query; returns (columns, rows) with columns as names."""
        r = self.es.esql.query(query=query, params=params, format="json").body
        return [c["name"] for c in r["columns"]], r["values"]

    def esql_rows(self, query, params=None):
        cols, vals = self.esql(query, params)
        return [dict(zip(cols, v)) for v in vals]

    def get(self, det_id):
        return self.es.get(index=DETECTIONS, id=det_id).body["_source"]

    def similar(self, ref, k=5, exclude_self=True, num_candidates=100):
        """kNN on the embedding. `ref` is a detection id (its stored vector is used) or a vector."""
        if isinstance(ref, str):
            # ES 9 keeps dense_vector out of _source; `fields` still returns it
            r = self.es.search(index=DETECTIONS, query={"ids": {"values": [ref]}}, fields=["embedding"], source=False, size=1).body
            hits = r["hits"]["hits"]
            vec = hits[0].get("fields", {}).get("embedding") if hits else None
            if not vec:
                raise ValueError(f"{ref} has no embedding")
            exclude = ref
        else:
            vec, exclude = list(ref), None
        knn = {"field": "embedding", "query_vector": vec, "k": k, "num_candidates": max(num_candidates, k)}
        if exclude and exclude_self:
            knn["filter"] = {"bool": {"must_not": {"term": {"id": exclude}}}}
        r = self.es.search(index=DETECTIONS, knn=knn, size=k, source_excludes=["embedding"]).body
        return [{"score": round(h["_score"], 4), **h["_source"]} for h in r["hits"]["hits"]]

    def semantic(self, text, k=5):
        """ELSER over `description`; falls back to a plain match when the field is not semantic_text."""
        from elasticsearch import BadRequestError
        try:
            r = self.es.search(index=DETECTIONS, query={"semantic": {"field": "description", "query": text}},
                               size=k, source_excludes=["embedding"]).body
        except BadRequestError:
            r = self.es.search(index=DETECTIONS, query={"match": {"description": text}},
                               size=k, source_excludes=["embedding"]).body
        return [{"score": round(h["_score"], 4), **h["_source"]} for h in r["hits"]["hits"]]

    def anomalies(self, job_id="keiko-soundscape", min_score=50, size=20):
        """Latest ML records above `min_score` (setup.py creates the job)."""
        # ES 9 rejects `size` as a query parameter: paging goes in the body as `page`
        r = self.es.ml.get_records(job_id=job_id, record_score=min_score, page={"from": 0, "size": size},
                                   sort="timestamp", desc=True).body
        return [{"timestamp": iso(x["timestamp"] / 1000), "score": round(x["record_score"], 1),
                 "detector": x.get("function_description") or x.get("function"), "field": x.get("field_name"),
                 "by": x.get("by_field_value"), "typical": x.get("typical", [None])[0], "actual": x.get("actual", [None])[0]}
                for x in r.get("records", [])]
