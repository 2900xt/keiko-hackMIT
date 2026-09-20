#!/usr/bin/env python3
"""Tests for the Elastic layer. Run with the pipeline venv: `../.venv/bin/python test_elastic.py`.

Unit part needs nothing. The integration part runs only when ELASTIC_URL / ELASTIC_CLOUD_ID is set (elastic/.env):
it creates keiko-test-* indices via the real templates, indexes docs, runs ES|QL / kNN / semantic, and deletes them.
"""
import os
import pathlib
import sys
import time
import unittest

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from features import audio_features, mean_embedding, unit  # noqa: E402
from keiko_es import describe, detection_doc, window_doc, load_env  # noqa: E402
import ask  # noqa: E402

REC = {"id": "KEIKO-01-20260920T073538", "buoy_id": "KEIKO-01", "timestamp_utc": "2026-09-20T07:35:38Z",
       "latitude": 42.3572, "longitude": -71.0868, "confidence": 0.77, "species": "humpback whale",
       "model_class": "Megaptera_novaeangliae", "windows": 4, "duration_s": 8.5, "sample_rate_hz": 44100,
       "clip": "/tmp/x.wav"}


class Features(unittest.TestCase):
    def test_tone_peak_and_flatness(self):
        fs = 8000; t = np.arange(3 * fs) / fs
        f = audio_features(0.5 * np.sin(2 * np.pi * 300 * t), fs)
        self.assertAlmostEqual(f["peak_hz"], 300, delta=2)
        self.assertLess(f["flatness"], 0.05)
        self.assertAlmostEqual(f["rms_db"], 20 * np.log10(0.5 / np.sqrt(2)), delta=0.5)

    def test_noise_is_flat(self):
        f = audio_features(np.random.default_rng(0).normal(0, 0.1, 8000 * 3), 8000)
        self.assertGreater(f["flatness"], 0.5)
        self.assertGreater(f["bandwidth_hz"], 500)

    def test_short_input(self):
        self.assertEqual(audio_features(np.zeros(4), 8000)["rms_db"], -120.0)

    def test_embedding_mean_is_unit(self):
        v = mean_embedding([np.ones(512), np.zeros(512) + 3])
        self.assertEqual(len(v), 512); self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0, places=5)
        self.assertIsNone(mean_embedding([]))
        self.assertEqual(unit([0, 0]), [0.0, 0.0])


class Docs(unittest.TestCase):
    def test_detection_doc(self):
        d = detection_doc(REC, embedding=np.ones(512) / 512 ** 0.5, probs={"Megaptera_novaeangliae": 0.81, "no_whale_noise": 0.1},
                          audio={"rms_db": -30.0, "peak_hz": 310.0, "centroid_hz": 420.0, "bandwidth_hz": 200.0, "flatness": 0.1},
                          buoy_name="Stellwagen")
        self.assertEqual(d["@timestamp"], "2026-09-20T07:35:38Z")
        self.assertEqual(d["location"], {"lat": 42.3572, "lon": -71.0868})
        self.assertEqual(d["buoy_location"], d["location"])
        self.assertEqual(len(d["embedding"]), 512)
        self.assertEqual(d["probs"]["Megaptera_novaeangliae"], 0.81)
        self.assertEqual(d["clip_path"], "/tmp/x.wav")
        self.assertIn("humpback whale", d["description"]); self.assertIn("Stellwagen", d["description"])
        self.assertIn("310 Hz", d["description"]); self.assertIn("tonal", d["description"])
        self.assertNotIn("notes", d)                       # None values dropped

    def test_fix_moves_location(self):
        fix = {"lat": 42.36, "lon": -71.08, "err_m": 12.5, "method": "tdoa", "truth_m_off": 3.0,
               "simulated_buoys": ["KEIKO-02"], "arrivals": [{"buoy_id": "KEIKO-01", "dt_ms": 0.0, "range_m": 100.0, "simulated": False}]}
        d = detection_doc(REC, fix=fix)
        self.assertEqual(d["location"], {"lat": 42.36, "lon": -71.08})
        self.assertEqual(d["buoy_location"], {"lat": 42.3572, "lon": -71.0868})
        self.assertEqual(d["fix"]["err_m"], 12.5); self.assertNotIn("lat", d["fix"])
        self.assertIn("12.5 m", d["description"])

    def test_describe_time_of_day(self):
        self.assertIn("early morning", describe(REC))
        self.assertIn("at night", describe({**REC, "timestamp_utc": "2026-09-20T23:10:00Z"}))
        self.assertIn("Tentative", describe({**REC, "confidence": 0.6}))
        self.assertIn("Confident", describe({**REC, "confidence": 0.9}))
        self.assertEqual(describe({"timestamp_utc": "garbage"}).count("garbage"), 1)

    def test_window_doc(self):
        w = window_doc(1789890938.25, {"id": "KEIKO-01", "lat": 1.0, "lon": 2.0}, "no_whale", 0.9, False, "no_whale_noise", 0.6,
                       probs={"a": 0.123456}, audio={"rms_db": -40}, fs=3333.0, net={"packets": 9, "dropped_packets": 1}, in_event=False)
        self.assertEqual(w["@timestamp"], "2026-09-20T07:55:38.250Z")
        self.assertEqual(w["probs"]["a"], 0.1235); self.assertFalse(w["whale"]); self.assertEqual(w["net"]["dropped_packets"], 1)
        self.assertEqual(w["location"], {"lat": 1.0, "lon": 2.0})


class Agent(unittest.TestCase):
    def test_guard(self):
        ask.guard("FROM keiko-detections | LIMIT 1")
        ask.guard("  from KEIKO-windows | STATS COUNT(*)")
        for bad in ("ROW a = 1", "FROM logs-* | LIMIT 1", "SHOW INFO", "FROM keiko-detections | LIMIT 1; DROP x"):
            with self.subTest(bad=bad):
                if bad.startswith("FROM keiko"):
                    continue                                 # ES|QL has no DDL; the prefix is the whole guard
                self.assertRaises(ValueError, ask.guard, bad)

    def test_table(self):
        t = ask.fmt_table(["species", "n"], [["humpback whale", 3], ["fin whale", 10]])
        self.assertIn("humpback whale  3", t); self.assertEqual(ask.fmt_table(["a"], []), "(no rows)")

    def test_tools_are_strict_and_named(self):
        self.assertEqual({t["name"] for t in ask.TOOLS}, {"esql", "similar_sounds", "semantic_search"})
        for t in ask.TOOLS:
            self.assertTrue(t["strict"]); self.assertFalse(t["input_schema"]["additionalProperties"])


@unittest.skipUnless(load_env() or os.environ.get("ELASTIC_URL") or os.environ.get("ELASTIC_CLOUD_ID"), "no cluster configured")
class Integration(unittest.TestCase):
    """Real cluster, throwaway indices. ELSER is skipped unless KEIKO_TEST_ELSER=1 (it needs an ML node + model download)."""
    D, W = "keiko-test-detections", "keiko-test-windows"

    @classmethod
    def setUpClass(cls):
        import json
        from keiko_es import KeikoES
        cls.k = KeikoES.from_env(flush_every=5, quiet=True); es = cls.k.es
        elser = os.environ.get("KEIKO_TEST_ELSER") == "1"
        for name, idx in (("keiko-detections", cls.D), ("keiko-windows", cls.W)):
            tpl = json.loads((HERE / "mappings" / f"{name}.json").read_text())
            tpl["index_patterns"] = [idx + "*"]; tpl["priority"] = 600
            props = tpl["template"]["mappings"]["properties"]
            if not elser and props.get("description", {}).get("type") == "semantic_text":
                props["description"] = {"type": "text"}
            es.indices.put_index_template(name=idx, **tpl)
            es.indices.delete(index=idx, ignore_unavailable=True); es.indices.create(index=idx)
        # point the client at the test indices
        import keiko_es
        cls._orig = (keiko_es.DETECTIONS, keiko_es.WINDOWS); keiko_es.DETECTIONS, keiko_es.WINDOWS = cls.D, cls.W

    @classmethod
    def tearDownClass(cls):
        import keiko_es
        keiko_es.DETECTIONS, keiko_es.WINDOWS = cls._orig
        for idx in (cls.D, cls.W):
            cls.k.es.indices.delete(index=idx, ignore_unavailable=True); cls.k.es.indices.delete_index_template(name=idx)
        cls.k.close()

    def test_roundtrip(self):
        rng = np.random.default_rng(1)
        base = unit(rng.normal(size=512)); other = unit(rng.normal(size=512))
        docs = []
        for i in range(6):
            rec = {**REC, "id": f"T-{i}", "timestamp_utc": f"2026-09-20T0{i}:00:00Z", "confidence": 0.6 + i * 0.05,
                   "species": "humpback whale" if i < 4 else "North Atlantic right whale"}
            emb = unit(np.asarray(base if i < 4 else other) + rng.normal(scale=0.05, size=512))
            docs.append(detection_doc(rec, embedding=emb, probs={"Megaptera_novaeangliae": 0.8}, audio={"rms_db": -30.0 - i, "peak_hz": 300.0 + i, "centroid_hz": 400.0, "bandwidth_hz": 100.0, "flatness": 0.1},
                                      buoy_name="test buoy"))
        for d in docs:
            self.k.add_detection(d, refresh=True)
        for i in range(12):
            self.k.add_window(window_doc(1758326400 + i * 1.5, {"id": "KEIKO-01", "lat": 42.3, "lon": -70.3}, "no_whale", 0.9, i % 3 == 0,
                                         "no_whale_noise", 0.6, probs={"no_whale_noise": 0.6}, audio={"rms_db": -40.0 + i, "peak_hz": 100.0, "centroid_hz": 200.0, "bandwidth_hz": 50.0, "flatness": 0.5},
                                         fs=3333.0, net={"packets": 10, "dropped_packets": i % 2}))
        self.k.flush(); self.k.es.indices.refresh(index=[self.D, self.W])
        self.assertEqual(self.k.stats["errors"], 0, self.k.stats)

        cols, rows = self.k.esql(f"FROM {self.D} | STATS n = COUNT(*), c = AVG(confidence) BY species | SORT n DESC")
        self.assertEqual(cols, ["n", "c", "species"]); self.assertEqual(rows[0][0], 4); self.assertEqual(rows[0][2], "humpback whale")
        rows = self.k.esql_rows(f"FROM {self.W} | STATS drops = SUM(net.dropped_packets), pk = SUM(net.packets), whale = SUM(CASE(whale, 1, 0)) BY buoy_id")
        self.assertEqual(rows[0]["drops"], 6); self.assertEqual(rows[0]["pk"], 120); self.assertEqual(rows[0]["whale"], 4)
        rows = self.k.esql_rows(f"FROM {self.D} | EVAL hour = DATE_EXTRACT(\"hour_of_day\", @timestamp) | STATS n = COUNT(*) BY hour | SORT hour")
        self.assertEqual([r["hour"] for r in rows], [0, 1, 2, 3, 4, 5])
        rows = self.k.esql_rows(f"FROM {self.D} | WHERE location IS NOT NULL | STATS km = AVG(ST_DISTANCE(location, TO_GEOPOINT(\"POINT(-71.0868 42.3572)\")))")
        self.assertAlmostEqual(rows[0]["km"], 0.0, delta=1.0)

        sim = self.k.similar("T-0", k=3)
        self.assertEqual({h["id"] for h in sim}, {"T-1", "T-2", "T-3"}); self.assertNotIn("embedding", sim[0])
        sim = self.k.similar("T-5", k=1); self.assertEqual(sim[0]["id"], "T-4")

        sem = self.k.semantic("right whale", k=2)
        self.assertTrue(sem and all("right whale" in h["species"] for h in sem))
        self.assertIn("test buoy", self.k.get("T-0")["description"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
