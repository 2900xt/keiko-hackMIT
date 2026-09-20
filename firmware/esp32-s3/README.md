# ESP32-S3 hydrophone node

Piezo hydrophone captured by an ESP32-S3-DevKitC-1 (N8R8) and shipped as sample blocks over USB to
a laptop, which forwards them to the pipeline over UDP -- same role as the UNO Q node in
`../unoq`, with the laptop standing in for the UNO Q's Linux side (the S3 has none).

```
piezos ─► PN2222 Darlington follower ─► GPIO1 (ADC1_CH0, 12-bit, 8 kHz)
                                          │  hw timer ISR → FreeRTOS sampler task, 256-sample blocks
                                          ▼
                              Serial.write("KBLK" frame)   USB-Serial-JTAG (native USB, ~1 MB/s)
                                          │
                                          ▼
                              python/main.py (laptop) ─► UDP 127.0.0.1:5005 (pipeline) ─► optional WAV
```

## Files

| | |
|---|---|
| `sketch/hydro.cpp` | MCU: hardware-timer-paced sampler task, ring of blocks, framed serial sender |
| `sketch/sketch.ino` | empty stub -- all code is in the `.cpp` so it never touches the `.ino` prototype generator |
| `sketch/sketch.yaml` | build profile (`esp32:esp32:esp32s3`, native USB CDC, 8 MB flash, octal PSRAM) |
| `python/main.py` | laptop: reads frames from the serial port, health line, UDP forward, WAV log |
| `python/test_node.py` | offline test of the Python side with synthetic blocks (`make test`) |
| `python/keiko.env` | settings: UDP destination, node id, serial port |
| `python/udp_listen.py` | receiver that prints what the UDP stream delivers (`make listen`) |
| `Makefile` | `make core` / `check` / `flash` / `start` / `record` … |

## Analog front end (3.3 V -- ESP32 pins are not 5 V tolerant)

Identical to the UNO Q node's: two PN2222 as a Darlington emitter follower, input impedance ≈ 1 MΩ.
The only wiring difference is the ADC pin -- **GPIO1** (ADC1 channel 0) instead of A0. Stay on ADC1:
ADC2 on the ESP32 family is shared with the Wi-Fi radio and returns garbage while it is on.

```
 3V3 ───┬──────────────┬─── Q1 C ─── Q2 C        Q1, Q2 = PN2222
        │              │
      [1k]           piezos ─── Q1 B                 disks in parallel, twisted pair
        │              │
      Vb ≈ 3.0V ──[1M]─┘        Q1 E ── Q2 B
        │
      [10k]                     Q2 E ──┬── GPIO1
        │                              │
       GND      100nF Vb→GND         [4.7k]  (5.1k from the kit is fine)
                                       │
                                      GND
```

Output idles at ~1.7 V. The health line prints `dc=…V`; if it isn't 1.5-1.9 V the follower is wired wrong.
The S3's ADC at 11 dB attenuation covers 0-3.1 V, so the follower's swing fits with margin.

## Run

One-time on the Mac (installs arduino-cli + the `esp32:esp32` core, ~600 MB):

```bash
make core
```

Compile check without a board (Apple Silicon: `brew install universal-ctags` first -- Arduino's bundled ctags is x86-only):

```bash
make check
```

Offline test of the Python side (`make venv` once to get numpy + pyserial):

```bash
make venv && make test
```

Flash the board -- plug the DevKitC's port labelled **USB** (not UART) into the Mac, then:

```bash
make flash            # auto-detects /dev/cu.usbmodem*; PORT=/dev/cu.xxx to pick one
```

If esptool cannot find the board, hold BOOT, tap RESET, release BOOT, retry (the S3 only needs this
the first time it is flashed over native USB). Then start the host side:

```bash
make start            # health line once a second; blocks go to udp 127.0.0.1:5005
```

Expect a line per second like:

```
fs= 8000.0Hz blocks/s= 31 dc=1.71V rms=  4.2mV peak= 31.0mV mcu_drops=0 missing=0 crc_bad=0
```

To run the pipeline on another machine, `make start UDP_HOST=<its ip>`; `pipeline/`'s `make live` picks
the node up on 5005 the same way it does the UNO Q's.

### Record a clip and run it through the whale CNN

```bash
make record DURATION=30                      # -> recordings/<utc>.wav (8000 Hz, 16-bit mono)
```

```bash
../../training/whale_cnn/.venv/bin/python ../../training/whale_cnn/predict.py recordings/*.wav --min_conf 0.8
```

The model resamples to 32 kHz itself. Same caveat as the UNO Q: with nothing wired to GPIO1 it still
reports a species at ~0.5 on pure electrical noise, so check `dc` is 1.5-1.9 V before believing a detection.

### Settings

`python/keiko.env` -- read by `main.py` at startup; real environment variables and command-line flags
override it. Keys: `KEIKO_SERIAL_PORT` (default `auto`: the first Espressif USB device),
`KEIKO_UDP_HOST` (default `127.0.0.1`), `KEIKO_UDP_PORT` (5005), `KEIKO_NODE_ID` (1 -- the UNO Q is 0),
`KEIKO_WAV`, `KEIKO_QUIET`.

## Serial frame (board → laptop)

One frame per block, little-endian, resynchronised on the magic if a byte is lost:

```
magic 4s "KBLK" | seq I | t0_us I | dropped I | n H | n×int16 raw ADC 0..4095 | crc H (CRC-16/CCITT-FALSE over everything before it)
```

`python/main.py` re-emits each frame as a KEIK datagram (format in `../unoq/README.md`; `bits`=12).

## Limits and knobs

- **Sample rate**: native USB CDC moves ~1 MB/s, so the UART bottleneck the UNO Q has is gone. The
  default is 8 kHz (Nyquist 4 kHz: baleen calls, boat noise, the lower half of dolphin whistles).
  `analogRead` on the S3 takes ~25 µs, so `SAMPLE_PERIOD_US` can go down to ~50 (20 kHz) before the
  sampler task starts missing ticks; raise `BLOCK`/`NBLOCKS` alongside.
- The timer runs at 1 MHz, so `SAMPLE_PERIOD_US` is exact -- the Python side still measures the real
  rate from MCU timestamps and puts that in the UDP header.
- `mcu_drops` > 0 means the sender fell behind (the sampler keeps its timing and overwrites).
  `missing` > 0 means a frame was lost on the wire; `crc_bad` > 0 means a frame arrived corrupted.
  Both should stay 0 on a direct USB connection -- if not, try another cable or skip the hub.
- Block timestamps are `esp_timer_get_time()` (µs since boot); host arrival time goes in the UDP
  header. Fine for single-node work; TDOA between nodes needs a shared clock.
