# UNO Q hydrophone node

Piezo hydrophone captured by the UNO Q's own MCU (STM32U585) and handed to the Linux side,
which forwards blocks to the pipeline over UDP — same role as the ESP32-S3 / nRF7002 nodes.

```
piezos ─► PN2222 Darlington follower ─► A0 (14-bit ADC, ~3.3 kHz)
                                          │  Zephyr timer thread, 256-sample blocks
                                          ▼
                              Bridge.notify("hydro/block", …)   UART 115200 + RTS/CTS
                                          │
                                          ▼
                              python/main.py ─► UDP 127.0.0.1:5005 (pipeline) ─► optional WAV
```

## Files

| | |
|---|---|
| `sketch/hydro.cpp` | MCU: kernel-timer-paced sampler in a cooperative thread, ring of blocks, Bridge sender |
| `sketch/sketch.ino` | empty stub — all code is in the `.cpp` so it never touches the `.ino` prototype generator |
| `sketch/sketch.yaml` | build profile (`arduino:zephyr:unoq`) |
| `python/main.py` | Linux: receives blocks, health line, UDP forward, WAV log |
| `python/test_node.py` | offline test of the Python side with synthetic blocks (`make test`) |
| `python/keiko.env` | settings: UDP destination, node id, WAV log (app.yaml can't carry env vars) |
| `python/udp_listen.py` | receiver that prints what the UDP stream delivers (`make listen`) |
| `app.yaml` | App Lab / `arduino-app-cli` manifest |
| `Makefile` | `make start` / `logs` / `stop` … over USB (adb) or Wi-Fi (ssh) |

## Analog front end (3.3 V — the UNO Q is not 5 V tolerant)

Two PN2222 from the Elegoo kit as a Darlington emitter follower. Input impedance ≈ 1 MΩ, so with
three 27 mm disks in parallel (~90 nF) the low-frequency cutoff is ~2 Hz.

```
 3V3 ───┬──────────────┬─── Q1 C ─── Q2 C        Q1, Q2 = PN2222
        │              │
      [1k]           piezos ─── Q1 B                 disks in parallel, twisted pair
        │              │
      Vb ≈ 3.0V ──[1M]─┘        Q1 E ── Q2 B
        │
      [10k]                     Q2 E ──┬── A0
        │                              │
       GND      100nF Vb→GND         [4.7k]  (5.1k from the kit is fine)
                                       │
                                      GND
```

Output idles at ~1.7 V. The health line prints `dc=…V`; if it isn't 1.5–1.9 V the follower is wired wrong.

## Run

One-time on the Mac (installs arduino-cli + the `arduino:zephyr` core, ~1 GB; that core also brings `adb`):

```bash
make core
```

Compile check without a board (Apple Silicon: `brew install universal-ctags` first — Arduino's bundled ctags is x86-only):

```bash
make check
```

Offline test of the Python side (`make venv` once to get numpy + msgpack):

```bash
make venv && make test
```

Deploy and run on the board — plug the UNO Q into the Mac with USB-C (directly, no hub), wait for the
heartbeat on the LED matrix, then:

```bash
make start
```

That pushes this folder to `~/ArduinoApps/keiko-unoq` on the board over adb and runs `arduino-app-cli app restart`
there, which compiles the sketch on the board, flashes the MCU over SWD, and starts `python/main.py` in a container.
First run takes ~2 min (numpy install); later runs ~20 s.

```bash
make logs      # last 30 lines        make follow   # stream
make stop      make shell             make ip
```

Expect a line per second like:

```
fs= 3333.3Hz blocks/s= 13 dc=1.71V rms=  4.2mV peak= 31.0mV mcu_drops=0 missing=0
```

Over Wi-Fi instead of USB: a fresh board has SSH off. Run `make enable-ssh` once over USB, then add
`VIA=ssh BOARD=<ip or name.local>` to any target (`make ip` prints the address).

### Settings

`python/keiko.env` — read by `main.py` at startup; real environment variables override it. App Lab's `app.yaml`
cannot carry environment variables, so this file is the configuration. Keys: `KEIKO_UDP_HOST` (default `auto`),
`KEIKO_UDP_PORT` (5005), `KEIKO_NODE_ID` (0), `KEIKO_WAV` (path on the board, e.g. `/app/python/hydro.wav`),
`KEIKO_QUIET`.

App Lab runs the Python side in a Docker container on its own bridge network, so `127.0.0.1` in there is the
container, not the board. `KEIKO_UDP_HOST=auto` sends to the container's default gateway, which is the board's
Linux side — a pipeline running on the UNO Q listens on `0.0.0.0:5005` and gets every block. To receive on a
laptop instead, put the laptop's IP there (same network as the board), `make start`, then `make listen`
(`python/udp_listen.py`, prints packets/s, sample rate, and missing sequence numbers).

The Python side also runs outside App Lab (`python3 python/main.py` on the board) — it falls back to
speaking MessagePack-RPC to `/var/run/arduino-router.sock` directly, and `auto` then means `127.0.0.1`.

## UDP packet (proposal for all nodes)

One datagram per block, little-endian:

```
magic 4s "KEIK" | ver B 1 | node B | fmt B 0=int16 raw ADC | bits B | fs f Hz | seq I | t_ns Q host mono | n H | n×int16
```

## Limits and knobs

- **Sample rate is capped by the Bridge UART** (115200 baud ≈ 11 kB/s). 16-bit × 3333 Hz = 6.7 kB/s.
  Nyquist 1.67 kHz: fine for baleen calls and boat noise, not for dolphin clicks. For wideband use the
  ESP32-S3/nRF nodes, or pack 12-bit samples (1.5 B/sample → ~7 kHz).
- `SAMPLE_PERIOD_US` must be a multiple of 100 µs (Zephyr tick). The Python side measures the real rate
  from MCU timestamps, so an off-by-a-tick period only changes the number it prints.
- `mcu_drops` > 0 means the Bridge couldn't drain blocks fast enough (the sampler keeps its timing and
  overwrites). `missing` > 0 means the router or Python dropped a notification. If nothing arrives at all,
  halve `BLOCK` first.
- Block timestamps are MCU `micros()`; host arrival time goes in the UDP header. Good enough for
  single-node work; TDOA between nodes needs the shared clock the ESP32/nRF nodes use.
