#!/usr/bin/env python3
"""Provision Keiko on an Elastic deployment. Idempotent; run it again after changing a mapping.

    python3 setup.py                 # indices + ML anomaly job + Kibana data views + alert rule
    python3 setup.py --no-elser      # clusters without ML: `description` becomes plain text
    python3 setup.py --no-ml         # skip the anomaly job (also implied when the cluster has no ML nodes)
    python3 setup.py --status        # what exists, doc counts, job state, latest anomalies

Needs ELASTIC_URL (or ELASTIC_CLOUD_ID) + ELASTIC_API_KEY; KIBANA_URL for the data views and the rule;
KEIKO_WEBHOOK_URL to have the rule post to Discord/Slack. All read from elastic/.env.

What it creates
    index templates + indices   keiko-detections, keiko-windows           (mappings/*.json)
    ML job keiko-soundscape     bucket 1 min over keiko-windows: mean(audio.rms_db) by buoy  -> noise floor drifts
                                (ships, weather); high_count of whale windows by buoy       -> unusual activity;
                                mean(audio.centroid_hz) by buoy                              -> a new kind of sound
    datafeed                    real-time, started
    Kibana data views           "Keiko detections", "Keiko windows"
    Kibana rule                 ES|QL query rule "Keiko: right whale" every minute; NARW >= 0.7 conf in the last
                                5 min -> webhook action (if KEIKO_WEBHOOK_URL) — the NOAA ship-speed-zone use case
"""
import argparse
import json
import os
import ssl
import urllib.error
import urllib.request

from elasticsearch import ApiError

from keiko_es import DETECTIONS, WINDOWS, KeikoES, load_env

JOB_ID = "keiko-soundscape"
RULE_NAME = "Keiko: North Atlantic right whale"
RULE_ESQL = ('FROM keiko-detections | WHERE species == "North Atlantic right whale" AND confidence >= 0.7 '
             '| KEEP @timestamp, id, buoy_id, confidence, duration_s, location | SORT @timestamp DESC')


# ---- Elasticsearch side -------------------------------------------------------
def has_ml_node(es):
    """True when some node carries the `ml` role (the licence flag alone does not mean a job can open)."""
    try:
        nodes = es.es.nodes.info(filter_path="nodes.*.roles").body["nodes"]
        return any("ml" in n.get("roles", []) for n in nodes.values())
    except Exception:
        return False


def has_ml(es):
    try:
        info = es.es.xpack.info().body
        return info["features"].get("ml", {}).get("available", False) and info["features"]["ml"].get("enabled", False)
    except Exception:
        return False


def ensure_ml_job(es):
    ml = es.es.ml
    job = {
        "description": "Keiko hydrophone soundscape: noise floor, whale-window rate and spectral centroid per buoy",
        "analysis_config": {
            "bucket_span": "1m",
            "detectors": [
                {"detector_description": "noise floor (mean rms_db) by buoy", "function": "mean",
                 "field_name": "audio.rms_db", "by_field_name": "buoy_id"},
                {"detector_description": "whale window rate by buoy", "function": "high_count",
                 "by_field_name": "buoy_id"},
                {"detector_description": "spectral centroid by buoy", "function": "mean",
                 "field_name": "audio.centroid_hz", "by_field_name": "buoy_id"},
            ],
            "influencers": ["buoy_id", "label", "top_class"],
        },
        "data_description": {"time_field": "@timestamp"},
        "analysis_limits": {"model_memory_limit": "32mb"},
    }
    try:
        ml.get_jobs(job_id=JOB_ID)
        print(f"ML job {JOB_ID}: exists")
    except Exception:
        ml.put_job(job_id=JOB_ID, **job)
        print(f"ML job {JOB_ID}: created")
    feed_id = f"datafeed-{JOB_ID}"
    try:
        ml.get_datafeeds(datafeed_id=feed_id)
    except Exception:
        # the whale-rate detector must only see whale windows, the others every window: two feeds would be cleaner,
        # but one feed with all windows and `high_count` on the whale-only partition is what one job allows, so the
        # rate detector counts every window and unusual *whale* activity shows up through the label influencer.
        ml.put_datafeed(datafeed_id=feed_id, job_id=JOB_ID, indices=[WINDOWS], query={"match_all": {}},
                        frequency="30s", query_delay="15s")
        print(f"datafeed {feed_id}: created")
    st = ml.get_job_stats(job_id=JOB_ID).body["jobs"][0]["state"]
    if st != "opened":
        try:
            ml.open_job(job_id=JOB_ID)
        except ApiError as e:
            if e.status_code != 429:
                raise
            # Elastic Cloud with ML autoscaling provisions an ML node on the first open; without it, add one in the console
            print(f"ML job {JOB_ID}: created but no ML node yet ({e.message}).\n"
                  "   Cloud console > deployment > Edit > Machine Learning instances (or enable autoscaling), then rerun setup.py")
            return
    fst = ml.get_datafeed_stats(datafeed_id=feed_id).body["datafeeds"][0]["state"]
    if fst != "started":
        ml.start_datafeed(datafeed_id=feed_id, start="0")     # from the beginning of the index, then real-time
    print(f"ML job {JOB_ID}: open, datafeed started (real-time)")


# ---- Kibana side --------------------------------------------------------------
class Kibana:
    def __init__(self, url, api_key):
        self.url = url.rstrip("/"); self.key = api_key
        self.ctx = ssl.create_default_context()

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.url + path, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"kbn-xsrf": "keiko", "Content-Type": "application/json",
                                              "Authorization": f"ApiKey {self.key}"})
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=30) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"kibana {method} {path} -> {e.code}: {e.read().decode()[:400]}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"kibana {self.url} unreachable ({e.reason}); KIBANA_URL should be the Kibana endpoint "
                               "from the Cloud console (Copy endpoint next to Kibana), not derived from the ES one") from None

    def ensure_data_view(self, title, name):
        for dv in self.call("GET", "/api/data_views")["data_view"]:
            if dv["title"] == title:
                print(f"data view {name!r}: exists"); return dv["id"]
        dv = self.call("POST", "/api/data_views/data_view",
                       {"data_view": {"title": title, "name": name, "timeFieldName": "@timestamp"}})["data_view"]
        print(f"data view {name!r}: created"); return dv["id"]

    def ensure_webhook(self, url):
        for c in self.call("GET", "/api/actions/connectors"):
            if c["name"] == "keiko-webhook":
                return c["id"]
        c = self.call("POST", "/api/actions/connector", {
            "name": "keiko-webhook", "connector_type_id": ".webhook",
            "config": {"url": url, "method": "post", "hasAuth": False, "headers": {"Content-Type": "application/json"}},
            "secrets": {}})
        print("webhook connector: created"); return c["id"]

    def ensure_rule(self, webhook_url=None):
        found = self.call("GET", "/api/alerting/rules/_find?search_fields=name&search=" + urllib.request.quote(RULE_NAME))
        for r in found.get("data", []):
            if r["name"] == RULE_NAME:
                print(f"rule {RULE_NAME!r}: exists"); return r["id"]
        actions = []
        if webhook_url:
            cid = self.ensure_webhook(webhook_url)
            # Discord and Slack incoming webhooks both take {"content"} / {"text"}; send both.
            msg = ("🐋 Keiko: {{context.hits.length}} right whale detection(s) in the last 5 min at "
                   "{{#context.hits}}{{_source.buoy_id}} conf {{_source.confidence}} {{/context.hits}}— "
                   "slow to 10 kn (NOAA seasonal management area).")
            actions.append({"id": cid, "group": "query matched",
                            "params": {"body": json.dumps({"content": msg, "text": msg})}})
        r = self.call("POST", "/api/alerting/rule", {
            "name": RULE_NAME, "rule_type_id": ".es-query", "consumer": "alerts", "schedule": {"interval": "1m"},
            "tags": ["keiko"], "enabled": True, "actions": actions,
            "params": {"searchType": "esqlQuery", "esqlQuery": {"esql": RULE_ESQL}, "timeField": "@timestamp",
                       "timeWindowSize": 5, "timeWindowUnit": "m", "size": 100, "thresholdComparator": ">",
                       "threshold": [0], "excludeHitsFromPreviousRun": True, "aggType": "count", "groupBy": "all"},
        })
        print(f"rule {RULE_NAME!r}: created" + (" with webhook action" if actions else " (no KEIKO_WEBHOOK_URL: no action)"))
        return r["id"]


# ---- status -------------------------------------------------------------------
def status(es):
    info = es.es.info().body
    print(f"cluster {info['cluster_name']}  es {info['version']['number']}")
    for idx in (DETECTIONS, WINDOWS):
        if es.es.indices.exists(index=idx):
            n = es.es.count(index=idx).body["count"]
            m = es.es.indices.get_mapping(index=idx).body[idx]["mappings"]["properties"]
            extra = f"  description: {m.get('description', {}).get('type')}" if idx == DETECTIONS else ""
            print(f"{idx}: {n} docs{extra}")
        else:
            print(f"{idx}: missing")
    try:
        js = es.es.ml.get_job_stats(job_id=JOB_ID).body["jobs"][0]
        fs = es.es.ml.get_datafeed_stats(datafeed_id=f"datafeed-{JOB_ID}").body["datafeeds"][0]
        print(f"ML job {JOB_ID}: {js['state']}, datafeed {fs['state']}, {js['data_counts']['processed_record_count']} records processed")
        if js["state"] != "opened" and not has_ml_node(es):
            print("   (no ML node in this deployment: Cloud console > Edit > add Machine Learning instances, then rerun setup.py)")
        for a in es.anomalies(JOB_ID, min_score=30, size=5):
            print(f"   anomaly {a['timestamp']} score {a['score']} {a['detector']} by {a['by']}: typical {a['typical']} actual {a['actual']}")
    except Exception as e:
        print(f"ML job {JOB_ID}: none ({type(e).__name__})")
    try:
        cols, rows = es.esql(f"FROM {DETECTIONS} | STATS n = COUNT(*), conf = AVG(confidence) BY species | SORT n DESC")
        for r in rows:
            print(f"   {r[2]:32s} {r[0]:4d}  avg conf {r[1]:.2f}")
    except Exception as e:
        print(f"ES|QL: {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-elser", action="store_true", help="map description as text (no ML nodes / ELSER)")
    ap.add_argument("--no-ml", action="store_true", help="skip the anomaly job")
    ap.add_argument("--no-kibana", action="store_true", help="skip data views + rule")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    load_env()
    es = KeikoES.from_env()
    if a.status:
        status(es); return
    elser = es.ensure_indices(elser=False if a.no_elser else None)
    print(f"indices {DETECTIONS}, {WINDOWS}: ok (description: {'semantic_text/ELSER' if elser else 'text'})")
    if not a.no_ml:
        if has_ml(es):
            ensure_ml_job(es)
        else:
            print("ML not available on this cluster: skipping the anomaly job")
    kb = os.environ.get("KIBANA_URL")
    if a.no_kibana or not kb:
        print("KIBANA_URL not set: skipping data views + rule" if not kb else "skipping kibana")
    else:
        k = Kibana(kb, os.environ["ELASTIC_API_KEY"])
        try:
            k.ensure_data_view(f"{DETECTIONS}*", "Keiko detections")
            k.ensure_data_view(f"{WINDOWS}*", "Keiko windows")
            k.ensure_rule(os.environ.get("KEIKO_WEBHOOK_URL"))
        except RuntimeError as e:
            print(f"kibana: {e}\n   (data views + the rule can also be made in Kibana by hand: see kibana/dashboard.md)")
    print("done. next: python3 backfill.py  •  cd ../pipeline && make demo ARGS=\"--elastic\"  •  python3 ask.py")


if __name__ == "__main__":
    main()
