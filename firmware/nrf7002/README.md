# nRF7002 DK hydrophone node

Piezo hydrophone captured by the nRF7002 DK's nRF5340 (SAADC) and sent to the pipeline over Wi-Fi as UDP —
same packets as the UNO Q node, but with no Linux side: the MCU owns the network link. Ported from
`firmware/unoq/` (same sampler thread, ring and header); only the transport changed.

```
piezos ─► passive bias + protection ─► AIN0 / P0.04 (12-bit SAADC, 8192 Hz)
                                          │  Zephyr timer thread, 256-sample blocks
                                          ▼
                                    sender loop (main) ─► UDP 5005 over Wi-Fi (nRF7002) ─► pipeline
                                          │
                                          └─► health line on the J-Link serial console (`make monitor`)
```

## Files

| | |
|---|---|
| `src/main.c` | MCU: kernel-timer-paced SAADC sampler in a cooperative thread, ring of blocks, Wi-Fi bring-up, UDP sender + health line |
| `boards/nrf7002dk_nrf5340_cpuapp.overlay` | SAADC channel 0 on AIN0: gain 1/3, internal 0.6 V ref → 0..1.8 V, 12-bit |
| `prj.conf` | build config: ADC, nRF70 Wi-Fi driver, IPv4/UDP/DHCP, buffers |
| `keiko.conf` | settings: Wi-Fi SSID/PSK, UDP destination, node id, sample rate (the `keiko.env` of this node — baked in at build time) |
| `Kconfig` | declares the `CONFIG_KEIKO_*` options `keiko.conf` sets |
| `host/udp_listen.py` | receiver that prints what the UDP stream delivers (`make listen`) and can record it to a WAV (`make record`); identical to the UNO Q's |
| `host/sim_node.py` | stand-in for the DK: emits the same stream from this Mac (`make sim`) |
| `host/test_node.py` | offline test of the packet format via the simulator (`make test`) |
| `Makefile` | `make build` / `flash` / `monitor` / `listen` / `record` … |

## Analog front end (1.8 V — the nRF7002 DK's I/O rail; the ADC input must never exceed VDD)

The UNO Q's Darlington follower does not fit a 1.8 V rail (two Vbe drops eat most of it), and the SAADC does not
need one: with a 10 µs acquisition it accepts sources up to ~200 kΩ, and three 27 mm disks in parallel (~90 nF)
are ~3.5 kΩ at 500 Hz. So the front end is passive — a mid-rail bias and a series resistor for protection.

```
 VDD (1.8V) ───[10k]───┬─── Vmid ≈ 0.9 V ───[470k]───┬─── piezos (+)      disks in parallel, twisted pair,
                       │                              │                    (−) to GND
                     [10k]         10µF Vmid→GND    [10k]
                       │                              │
                      GND                           AIN0  (P0.04, Arduino header "A0" on the DK)
```

Low-frequency cutoff 1/(2π·470k·90nF) ≈ 4 Hz. The 10k in series with AIN0 plus the pin's own clamp diodes soak up
the tens of volts a knocked piezo can produce. Output idles at ~0.9 V; the health line prints `dc=…V` and it
should read 0.8–1.0 V. Meter the DK's `VDD` header pin first: if it reads 3.0 V your DK is strapped differently —
the divider still lands at VDD/2 but change the overlay to `ADC_GAIN_1_6` and `CONFIG_KEIKO_ADC_FULL_SCALE_MV=3600`.

## Run

One-time on the Mac (nrfutil + the nRF Connect SDK toolchain and tree, ~4 GB):

```bash
make sdk
```

Put the Wi-Fi name/password and, unless the subnet broadcast default is fine, the pipeline machine's IP in
`keiko.conf`. Then, DK plugged in by its J-Link USB port (the one nearest the corner, not the nRF USB):

```bash
make flash
```

(`make build` alone is the compile check.) `make flash` compiles and programs the app core; the first build takes a
few minutes, later ones ~30 s. Then:

```bash
make monitor     # serial console: wifi: up, ip 10.0.0.42 / keiko nrf7002 node 1 -> udp ... / health lines
```

LED1 blinks once a second while the sampler runs, LED2 is on while the Wi-Fi link is up.

Offline test of the packet format, no SDK or board needed:

```bash
make test
```

### Record a clip and run it through the whale CNN (the MVP loop, by hand)

```bash
make record DURATION=30                      # -> recordings/<utc>.wav on this Mac (8192 Hz, 16-bit mono); node keeps running
```

```bash
../../training/whale_cnn/.venv/bin/python ../../training/whale_cnn/predict.py recordings/*.wav --min_conf 0.8
```

Same caveats as the UNO Q: the model resamples to 32 kHz itself, an unwired AIN0 still gets a species at ~0.5 on
noise, so keep `--min_conf` high and check `dc` is 0.8–1.0 V before believing a detection. Archiving a detection on the
website is the same `site/tools/keiko_data.py add …` line as in `firmware/unoq/README.md` (use `--buoy KEIKO-02`).

Expect a line per second on the console like:

```
fs= 8192.0Hz blocks/s= 32 dc=0.91V rms=  2.6mV peak= 19.4mV mcu_drops=0 send_err=0
```

### Feeding the pipeline

The pipeline listens on `0.0.0.0:5005`, so with the default broadcast destination any laptop on the same Wi-Fi as
the DK just runs it: `cd ../../pipeline && make live-nrf`. There is no USB fallback like the UNO Q's `adb reverse`
relay — the node only speaks Wi-Fi — so on a network that isolates clients (MIT GUEST does) put the DK and the laptop
on a phone hotspot. To try the pipeline before the board exists: `make sim` in one terminal, `make live-nrf` in another.

### Settings

`keiko.conf` — Kconfig values compiled into the image; there is no Linux side to re-read a file, so a change is
`make flash` (~1 min). Keys: `CONFIG_KEIKO_WIFI_SSID` / `_PSK`, `CONFIG_KEIKO_UDP_HOST` (default `255.255.255.255`
= the whole subnet; or one IP; a hostname works too since `CONFIG_DNS_RESOLVER` is on, but mDNS `.local` names do
not), `CONFIG_KEIKO_UDP_PORT` (5005), `CONFIG_KEIKO_NODE_ID` (1; the UNO Q is 0), `CONFIG_KEIKO_SAMPLE_PERIOD_TICKS`
(4 = 8192 Hz; 10 = 3277 Hz to match the UNO Q's rate).

Per-build overrides without editing the file: `make flash SSID=hotspot PSK=secret UDP_HOST=10.0.0.5`, or
`make retarget UDP_HOST=<laptop ip>` (the UNO Q's `retarget` is a 1 s hot reload; here it is a reflash).

## UDP packet (same as every node)

One datagram per block, little-endian:

```
magic 4s "KEIK" | ver B 1 | node B | fmt B 0=int16 raw ADC | bits B 12 | fs f Hz | seq I | t_ns Q node uptime | n H | n×int16
```

`src/main.c` has the header as a packed struct with a `BUILD_ASSERT` on its 26-byte size; `host/test_node.py` checks
the Python side against the same layout. `t_ns` is the node's uptime, where the UNO Q put host arrival time.

## Limits and knobs

- **Sample rate is not UART-bound here** (the UNO Q's 115200-baud Bridge capped it at ~3.3 kHz). 8192 Hz is
  16 kB/s of UDP; `CONFIG_KEIKO_SAMPLE_PERIOD_TICKS=2` gives 16 kHz if dolphin clicks matter. Above that the
  10 µs acquisition + conversion (~2 µs) starts to crowd the 61 µs period — drop the acquisition time to 5 µs
  in the overlay (fine for a source under 100 kΩ).
- The period is in RTC ticks (32768 Hz), so rates are 32768/N Hz, never round numbers. fs is measured from block
  timestamps and put in the header, so the receiver never needs to know N.
- `mcu_drops` > 0 means the sender fell behind the sampler (the ring keeps its timing and overwrites).
  `send_err` > 0 means the link was down or `sendto` failed — it counts up while the node is reconnecting; a
  steadily rising value with the link up means the destination is unreachable (wrong subnet, client isolation).
  `missing` on the receiver side (`make listen`) is packets lost in the air.
- Wi-Fi drops are handled: the node reconnects and resumes with the same `seq` counter, the sampler never stops.
- Block timestamps are 30.5 µs RTC resolution and node-local. TDOA between nodes needs a shared clock (SNTP
  over the same link is the obvious next step; not done).
- `boards/*.overlay` and `prj.conf` target nRF Connect SDK v3.0 (`nrf7002dk/nrf5340/cpuapp`, `CONFIG_WIFI_NRF70`).
  On an SDK before v2.7 the driver symbols are the older `CONFIG_WIFI_NRF700X` names. Neither the firmware nor the
  SDK install has been built on this Mac yet — `make build` is the first thing to run when the SDK lands.
