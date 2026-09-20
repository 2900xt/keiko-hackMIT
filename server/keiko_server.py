#!/usr/bin/env python3
"""Keiko central server: takes the pipeline's detections, localizes them across the buoy array, keeps tracks,
and streams everything to the website over one WebSocket.

    python3 keiko_server.py                 # ws://0.0.0.0:8765  (the site's Live tab connects here in dev)
    python3 keiko_server.py --inject        # no pipeline: push a fake humpback every 8 s to exercise the map

Clients say who they are in their first message: {"role": "node"} is the pipeline (see keiko_pipeline.py
--server), anything else is a browser. Node messages are JSON with a "type":
    telemetry  {id, lat, lon, ...}                     forwarded, every 2 s
    audio      {ts, samples[], bins[], level_db}       forwarded as-is (the live waveform/spectrogram)
    window     {ts, label, conf, whale}                forwarded ("hearing now")
    detection  {id, ts, species, confidence, duration_s, lat, lon, buoy_id, ...}   localized, tracked, forwarded

LOCALIZATION. One physical buoy cannot fix a position, so the array is completed with two virtual buoys
(KEIKO-02, KEIKO-03, flagged simulated everywhere they appear). For each detection a hidden source position
(a random walk along the river) gives the true arrival time at each buoy; the real buoy's arrival is the event
time, the virtual ones are simulated with 2 ms of jitter. The fix itself is a genuine TDOA solve (Gauss-Newton
on the hyperbolic residuals, c = 1480 m/s) so the maths is what a three-buoy array would run - only two of
the three arrival times are made up. The error radius comes from the residuals and the timing jitter.

Browsers receive, besides the four above (detection with a "fix" attached):
    buoys      [{id, lat, lon, simulated}]              on connect and when it changes
    track      {id, species, points:[{ts,lat,lon}], ...}  after each detection
    hello      {server, buoys, tracks}                  on connect
"""
import argparse, asyncio, json, math, random, signal, sys, time
from datetime import datetime, timezone

import websockets

C_WATER = 1480.0          # m/s
JITTER_S = 0.002          # simulated timing error per virtual buoy
TRACK_GAP_S = 600         # a detection joins the last track of its species if it is this recent
RIVER_BEARING = 90.0      # President Roads (Boston Harbor) runs E-W between Deer Island and Long Island
RIVER_HALF_LEN, ACROSS_MIN, ACROSS_MAX = 400.0, 15.0, 150.0   # metres, the box the source walks in (between the islands)

REAL_BUOY = {"id": "KEIKO-01", "lat": 42.34000, "lon": -70.97000, "simulated": False}
# A triangle, not a line: the real buoy is the apex on this side of the channel, the virtual pair sits ~350 m up- and down-channel
# on the far side, so TDOA hyperbolae cross at a usable angle anywhere in the box the source walks in.
VIRTUAL_BUOYS = [
    {"id": "KEIKO-02", "along": 350.0, "across": 160.0, "simulated": True},
    {"id": "KEIKO-03", "along": -350.0, "across": 160.0, "simulated": True},
]


def utc(ts=None):
    return datetime.fromtimestamp(ts if ts is not None else time.time(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---- local flat-earth frame around the real buoy (x east, y north, metres) -----------------------------
class Frame:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111320.0 * math.cos(math.radians(lat0)); self.ky = 111320.0

    def xy(self, lat, lon):
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)

    def latlon(self, x, y):
        return (round(self.lat0 + y / self.ky, 6), round(self.lon0 + x / self.kx, 6))

    def river(self, along, across):
        """river-axis coordinates -> x, y"""
        b = math.radians(RIVER_BEARING)
        return (along * math.sin(b) + across * math.cos(b), along * math.cos(b) - across * math.sin(b))


def _gn(rx, toa, x, y, c, iters=30):
    """Gauss-Newton from (x, y) on the hyperbolic residuals d_i - d_0 - c (t_i - t_0). Returns x, y, residual rms (m), JtJ."""
    JtJ = ((1.0, 0.0), (0.0, 1.0))
    for _ in range(iters):
        d = [math.hypot(x - px, y - py) + 1e-9 for px, py in rx]
        J, r = [], []
        for i in range(1, len(rx)):
            r.append((d[i] - d[0]) - c * (toa[i] - toa[0]))
            J.append([(x - rx[i][0]) / d[i] - (x - rx[0][0]) / d[0], (y - rx[i][1]) / d[i] - (y - rx[0][1]) / d[0]])
        a11 = sum(j[0] * j[0] for j in J); a12 = sum(j[0] * j[1] for j in J); a22 = sum(j[1] * j[1] for j in J)
        b1 = sum(j[0] * ri for j, ri in zip(J, r)); b2 = sum(j[1] * ri for j, ri in zip(J, r))
        det = a11 * a22 - a12 * a12
        JtJ = ((a11, a12), (a12, a22))
        if abs(det) < 1e-12:
            break
        dx = (a22 * b1 - a12 * b2) / det; dy = (a11 * b2 - a12 * b1) / det
        step = math.hypot(dx, dy)
        if step > 150:                      # damp big jumps
            dx *= 150 / step; dy *= 150 / step
        x -= dx; y -= dy
        if step < 1e-3:
            break
    d = [math.hypot(x - px, y - py) for px, py in rx]
    r = [(d[i] - d[0]) - c * (toa[i] - toa[0]) for i in range(1, len(rx))]
    return x, y, math.sqrt(sum(e * e for e in r) / len(r)), JtJ


def solve_tdoa(rx, toa, c=C_WATER, prior=None, sigma_t=JITTER_S):
    """rx: [(x, y)] receivers, toa: arrival times (s). Multi-start Gauss-Newton (two hyperbolae can cross twice), the
    lowest-residual solution wins, ties go to the one nearest `prior`. Returns x, y, residual rms (m), error radius (m)
    = 2 sigma from the timing noise mapped through the geometry at the solution."""
    cx, cy = sum(p[0] for p in rx) / len(rx), sum(p[1] for p in rx) / len(rx)
    starts = [(cx, cy)] + list(rx) + [(cx + dx, cy + dy) for dx in (-400, 0, 400) for dy in (-300, 0, 300)]
    if prior: starts.insert(0, prior)
    best = None
    for sx, sy in starts:
        x, y, rms, JtJ = _gn(rx, toa, sx, sy, c)
        far = math.hypot(x - cx, y - cy)
        if far > 3000: continue
        key = (round(rms, 1), math.hypot(x - prior[0], y - prior[1]) if prior else far)
        if best is None or key < best[0]:
            best = (key, x, y, rms, JtJ)
    if best is None:
        return cx, cy, 1e9, 1e9
    _, x, y, rms, JtJ = best
    (a11, a12), (_, a22) = JtJ
    det = a11 * a22 - a12 * a12
    sig = c * sigma_t
    err = 2 * sig * math.sqrt((a11 + a22) / det) if det > 1e-12 else 500.0     # 2 * sqrt(trace(sigma^2 (JtJ)^-1))
    return x, y, rms, max(err, 3.0)


class Localizer:
    """Hidden source + virtual arrivals + the TDOA fix."""

    def __init__(self, buoys, frame):
        self.frame = frame
        self.buoys = buoys
        self.rx = [frame.xy(b["lat"], b["lon"]) for b in buoys]
        self.along, self.across = random.uniform(-250, 250), random.uniform(40, 120)
        self.heading = random.choice([1, -1])
        self.prior = None

    def advance(self, dt_s):
        """The source swims along the river at ~1-2 m/s, wandering across it."""
        step = min(dt_s, 600) * random.uniform(1.0, 2.0)
        self.along += self.heading * step
        self.across += random.uniform(-25, 25)
        if abs(self.along) > RIVER_HALF_LEN: self.heading *= -1; self.along = math.copysign(RIVER_HALF_LEN, self.along)
        self.across = max(ACROSS_MIN, min(ACROSS_MAX, self.across))

    def localize(self, t_event, dt_since_last):
        self.advance(dt_since_last)
        sx, sy = self.frame.river(self.along, self.across)
        # true time of emission such that the real buoy hears it at t_event
        d = [math.hypot(sx - px, sy - py) for px, py in self.rx]
        t_emit = t_event - d[0] / C_WATER
        toa = [t_emit + di / C_WATER + (random.gauss(0, JITTER_S) if b["simulated"] else 0.0) for di, b in zip(d, self.buoys)]
        x, y, rms, err = solve_tdoa(self.rx, toa, prior=self.prior)
        self.prior = (x, y)
        lat, lon = self.frame.latlon(x, y)
        err = min(max(err, 1.5 * rms), 300.0)
        return {
            "lat": lat, "lon": lon, "err_m": round(err, 1), "method": "tdoa", "c_m_s": C_WATER,
            "arrivals": [{"buoy_id": b["id"], "dt_ms": round((ti - toa[0]) * 1000, 2), "range_m": round(di, 1),
                          "simulated": b["simulated"]} for b, ti, di in zip(self.buoys, toa, d)],
            "simulated_buoys": [b["id"] for b in self.buoys if b["simulated"]],
            "truth_m_off": round(math.hypot(x - sx, y - sy), 1),   # how far the solve landed from the hidden source
        }


# ---- server ---------------------------------------------------------------------------------------------
class Server:
    def __init__(self):
        self.frame = Frame(REAL_BUOY["lat"], REAL_BUOY["lon"])
        self.buoys = [dict(REAL_BUOY)]
        for v in VIRTUAL_BUOYS:
            x, y = self.frame.river(v["along"], v["across"]); lat, lon = self.frame.latlon(x, y)
            self.buoys.append({"id": v["id"], "lat": lat, "lon": lon, "simulated": True})
        self.loc = Localizer(self.buoys, self.frame)
        self.browsers = set(); self.node = None
        self.tracks = []            # newest last
        self.detections = []        # this session, with fixes
        self.last_t = None
        self.telemetry = {REAL_BUOY["id"]: {"id": REAL_BUOY["id"], "ts": utc(), "lat": REAL_BUOY["lat"], "lon": REAL_BUOY["lon"], "simulated": False}}
        self.t0 = time.time()

    # -- fan-out
    async def broadcast(self, msg):
        if not self.browsers: return
        data = json.dumps(msg)
        dead = []
        for ws in self.browsers:
            try: await ws.send(data)
            except Exception: dead.append(ws)
        for ws in dead: self.browsers.discard(ws)

    def track_for(self, det):
        species = det.get("species", "unknown"); t = det["_t"]
        for tr in reversed(self.tracks):
            if tr["species"] == species and t - tr["_t_last"] <= TRACK_GAP_S:
                return tr
        tr = {"id": f"T{len(self.tracks) + 1:03d}", "species": species, "points": [], "_t_last": t, "started": utc(t)}
        self.tracks.append(tr)
        return tr

    async def on_detection(self, det):
        t = time.time()
        try:
            t_ev = datetime.strptime(det["ts"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            t_ev = t
        det["_t"] = t_ev
        fix = self.loc.localize(t_ev, 0 if self.last_t is None else max(0.0, t_ev - self.last_t))
        self.last_t = t_ev
        det["fix"] = fix
        det["lat"], det["lon"] = fix["lat"], fix["lon"]          # the map shows the fix; the buoy stays in buoy_id
        tr = self.track_for(det)
        tr["points"].append({"ts": det["ts"], "lat": fix["lat"], "lon": fix["lon"], "err_m": fix["err_m"], "id": det["id"]})
        tr["_t_last"] = t_ev; det["track_id"] = tr["id"]
        self.detections.append(det)
        print(f"{utc(t)}  DETECTION {det['id']} {det.get('species')} conf={det.get('confidence')} -> fix "
              f"{fix['lat']:.5f},{fix['lon']:.5f} ±{fix['err_m']} m (solve {fix['truth_m_off']} m off truth)  track {tr['id']} "
              f"({len(tr['points'])} pts)", flush=True)
        await self.broadcast({"type": "detection", **{k: v for k, v in det.items() if not k.startswith("_")}})
        await self.broadcast({"type": "track", **self.public_track(tr)})

    def public_track(self, tr):
        return {k: v for k, v in tr.items() if not k.startswith("_")}

    # -- connections
    async def handle(self, ws):
        role = "browser"
        try:
            first = await asyncio.wait_for(ws.recv(), timeout=5)
            hello = json.loads(first)
            role = hello.get("role", "browser")
        except Exception:
            pass
        if role == "node":
            await self.serve_node(ws)
        else:
            await self.serve_browser(ws)

    async def serve_node(self, ws):
        peer = ws.remote_address
        print(f"{utc()}  node connected from {peer}", flush=True)
        self.node = ws
        try:
            async for raw in ws:
                try: msg = json.loads(raw)
                except Exception: continue
                kind = msg.get("type")
                if kind == "detection":
                    await self.on_detection(msg)
                elif kind == "telemetry":
                    msg["simulated"] = False; self.telemetry[msg.get("id", REAL_BUOY["id"])] = msg
                    await self.broadcast(msg)
                elif kind in ("audio", "window"):
                    await self.broadcast(msg)
        except websockets.ConnectionClosed:
            pass
        finally:
            if self.node is ws: self.node = None
            print(f"{utc()}  node disconnected", flush=True)

    async def serve_browser(self, ws):
        self.browsers.add(ws)
        print(f"{utc()}  browser connected ({len(self.browsers)} open)", flush=True)
        try:
            await ws.send(json.dumps({"type": "hello", "server": "keiko", "buoys": self.buoys,
                                      "tracks": [self.public_track(t) for t in self.tracks],
                                      "detections": [{k: v for k, v in d.items() if not k.startswith("_")} for d in self.detections[-50:]],
                                      "node_online": self.node is not None}))
            async for _ in ws:
                pass  # browsers only listen
        except websockets.ConnectionClosed:
            pass
        finally:
            self.browsers.discard(ws)

    async def virtual_telemetry(self):
        """Every 2 s: the virtual buoys report (flagged), and the real one's last report is repeated if the node is quiet."""
        while True:
            now = utc()
            for b in self.buoys:
                if b["simulated"]:
                    await self.broadcast({"type": "telemetry", "id": b["id"], "ts": now, "lat": b["lat"], "lon": b["lon"],
                                          "battery_pct": round(88 - (time.time() - self.t0) / 3600, 1), "water_temp_c": 18.2,
                                          "uptime_s": int(time.time() - self.t0), "simulated": True})
            await self.broadcast({"type": "status", "node_online": self.node is not None, "ts": now})
            await asyncio.sleep(2)

    async def inject(self, every_s):
        """Stand-in for the pipeline: a humpback detection every `every_s` seconds."""
        n = 0
        while True:
            await asyncio.sleep(every_s)
            n += 1; now = time.time()
            await self.on_detection({"type": "detection", "id": f"KEIKO-01-{datetime.fromtimestamp(now, timezone.utc).strftime('%Y%m%dT%H%M%S')}",
                                     "ts": utc(now)[:19] + "Z", "buoy_id": "KEIKO-01", "species": "humpback whale",
                                     "model_class": "Megaptera_novaeangliae", "confidence": round(random.uniform(0.7, 0.95), 2),
                                     "duration_s": round(random.uniform(4, 12), 1), "f0": 300, "sweep": 0, "injected": True})


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0"); ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--inject", nargs="?", const=8.0, type=float, metavar="SECONDS", help="fake a detection every N s (default 8) for testing the map")
    a = ap.parse_args()
    srv = Server()
    print(f"keiko server on ws://{a.host}:{a.port}  buoys: " + ", ".join(f"{b['id']}{' (simulated)' if b['simulated'] else ''}" for b in srv.buoys), flush=True)
    stop = asyncio.get_running_loop().create_future()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, lambda: stop.done() or stop.set_result(None))
    tasks = [asyncio.create_task(srv.virtual_telemetry())]
    if a.inject: tasks.append(asyncio.create_task(srv.inject(a.inject)))
    async with websockets.serve(srv.handle, a.host, a.port, ping_interval=20, max_size=2**20):
        await stop
    for t in tasks: t.cancel()


if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
