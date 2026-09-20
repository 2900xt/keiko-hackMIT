#!/usr/bin/env python3
"""Keiko hydrophone node — ESP32-S3, host side.

The S3 has no Linux side, so this runs on the laptop the board is plugged into and
does what firmware/unoq/python/main.py does on the UNO Q: receives raw ADC blocks
from the MCU ("KBLK" frames over USB serial), then

  * prints a once-a-second health line (measured sample rate, DC bias, RMS, drops)
  * forwards each block as a UDP datagram to the pipeline (same KEIK packet as
    the UNO Q node, see PACKET FORMAT below)
  * optionally appends everything to a WAV file

    python3 main.py                             # auto-detect the board, stream to udp 127.0.0.1:5005
    python3 main.py --port /dev/cu.usbmodem101 --seconds 30 --wav clip.wav

Configuration (command line > environment variables > python/keiko.env next to
this file; the file is re-read every second, so editing it redirects the stream live):
  KEIKO_SERIAL_PORT  default auto          serial device, or "auto" = first Espressif USB device
  KEIKO_SERIAL_BAUD  default 921600        ignored by native USB CDC, matters for the UART port
  KEIKO_UDP_HOST     default 127.0.0.1     pipeline receiver ("auto" also means this machine)
  KEIKO_UDP_PORT     default 5005
  KEIKO_NODE_ID      default 1             node id in the packet header (the UNO Q is 0)
  KEIKO_WAV          default unset         path to append a 16-bit mono WAV log
  KEIKO_QUIET        default unset         set to silence the health line

SERIAL FRAME (little-endian), one per block, see sketch/hydro.cpp:
  magic   4s  b"KBLK"
  seq     I   MCU block counter
  t0_us   I   esp_timer_get_time() at the first sample
  dropped I   blocks the MCU overwrote because the sender fell behind
  n       H   sample count
  data    n * int16
  crc     H   CRC-16/CCITT-FALSE over everything above

PACKET FORMAT (little-endian), one datagram per block:
  magic  4s  b"KEIK"
  ver    B   1
  node   B   KEIKO_NODE_ID
  fmt    B   0 = raw ADC counts as int16
  bits   B   ADC resolution (12)
  fs     f   measured sample rate, Hz
  seq    I   MCU block counter
  t_ns   Q   host CLOCK_MONOTONIC ns when the block arrived
  n      H   sample count
  data   n * int16
"""

import argparse
import os
import struct
import socket
import sys
import time
import wave

import numpy as np

ADC_BITS = 12
VREF = 3.3
ESPRESSIF_VID = 0x303A          # native USB-Serial-JTAG on the S3
CP210X_VID = 0x10C4             # the DevKitC's "UART" port (CP2102N)

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keiko.env")


def load_env_file(path=ENV_FILE):
    """KEY=VALUE lines (# comments allowed) into os.environ, without overriding what is already set."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    except OSError:
        pass


def resolve_udp_host(value):
    """'auto' / 'host' -> this machine (the pipeline runs here unless told otherwise)."""
    if value.strip().lower() in ("", "auto", "host"):
        return "127.0.0.1"
    return value.strip()


_REAL_ENV = dict(os.environ)          # what was set outside the file; the file never overrides these
load_env_file()
UDP_HOST = resolve_udp_host(os.environ.get("KEIKO_UDP_HOST", "auto"))
UDP_PORT = int(os.environ.get("KEIKO_UDP_PORT", "5005"))
NODE_ID = int(os.environ.get("KEIKO_NODE_ID", "1"))
WAV_PATH = os.environ.get("KEIKO_WAV")
QUIET = bool(os.environ.get("KEIKO_QUIET"))

HDR = struct.Struct("<4sBBBBfIQH")
FRAME_HDR = struct.Struct("<4sIIIH")
FRAME_MAGIC = b"KBLK"


def crc16_ccitt(data, crc=0xFFFF):
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def read_env_file(path=ENV_FILE):
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip("\"'")
    except OSError:
        pass
    return out


def reload_settings(path=ENV_FILE):
    """Re-read keiko.env and apply UDP host/port/node id (keys set in the real environment win).
    Returns True if anything changed."""
    global UDP_HOST, UDP_PORT, NODE_ID
    f = read_env_file(path)
    get = lambda k, d: _REAL_ENV.get(k, f.get(k, d))
    host = resolve_udp_host(get("KEIKO_UDP_HOST", "auto"))
    port = int(get("KEIKO_UDP_PORT", "5005"))
    node = int(get("KEIKO_NODE_ID", "1"))
    changed = (host, port, node) != (UDP_HOST, UDP_PORT, NODE_ID)
    UDP_HOST, UDP_PORT, NODE_ID = host, port, node
    return changed


def watch_settings(period=1.0):
    """Daemon thread: poll keiko.env and apply changes."""
    import threading

    def run():
        last = read_env_file()
        while True:
            time.sleep(period)
            cur = read_env_file()
            if cur != last:
                last = cur
                if reload_settings():
                    print(f"settings reloaded: udp -> {UDP_HOST}:{UDP_PORT} node {NODE_ID}", flush=True)

    threading.Thread(target=run, name="keiko-env-watch", daemon=True).start()


class Node:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.fs = 0.0                 # measured from MCU timestamps
        self.dc = None                # running mean of raw counts
        self.last_seq = None
        self.last_t0 = None
        self.missing = 0
        self.crc_bad = 0
        self.wav = None
        self._stat_t = time.monotonic()
        self._stat_blocks = 0
        self._stat_sq = 0.0
        self._stat_n = 0
        self._stat_peak = 0

    # ---- one block from the MCU ---------------------------------------------
    def on_block(self, seq, t0_us, dropped, data):
        t_ns = time.monotonic_ns()
        x = np.frombuffer(data, dtype="<i2")

        # sample rate from consecutive MCU timestamps (esp_timer is 64-bit but we ship the low 32: wraps every ~71 min)
        if self.last_t0 is not None and seq == self.last_seq + 1:
            dt = (t0_us - self.last_t0) & 0xFFFFFFFF
            if dt:
                fs = len(x) * 1e6 / dt
                self.fs = fs if self.fs == 0 else 0.9 * self.fs + 0.1 * fs
        if self.last_seq is not None and seq != self.last_seq + 1:
            self.missing += (seq - self.last_seq - 1) & 0xFFFFFFFF
        self.last_seq, self.last_t0 = seq, t0_us

        # DC tracker (the follower biases the pin to ~1.7 V; this is the number to check)
        m = float(x.mean())
        self.dc = m if self.dc is None else 0.98 * self.dc + 0.02 * m

        self.forward(seq, t_ns, x)
        self.log_wav(x)
        self.stats(x, dropped)

    # ---- outputs -----------------------------------------------------------
    def forward(self, seq, t_ns, x):
        hdr = HDR.pack(b"KEIK", 1, NODE_ID, 0, ADC_BITS, float(self.fs), seq, t_ns, len(x))
        try:
            self.sock.sendto(hdr + x.tobytes(), (UDP_HOST, UDP_PORT))
        except OSError:
            pass  # pipeline not up yet; nothing to do

    def log_wav(self, x):
        if not WAV_PATH:
            return
        if self.wav is None:
            if self.fs == 0:
                return  # wait until the rate is measured so the header is right
            self.wav = wave.open(WAV_PATH, "wb")
            self.wav.setnchannels(1)
            self.wav.setsampwidth(2)
            self.wav.setframerate(int(round(self.fs)))
        ac = (x.astype(np.int32) - int(self.dc)) << (16 - ADC_BITS)
        self.wav.writeframes(np.clip(ac, -32768, 32767).astype("<i2").tobytes())

    def stats(self, x, dropped):
        ac = x.astype(np.float64) - self.dc
        self._stat_sq += float((ac * ac).sum())
        self._stat_n += len(x)
        self._stat_peak = max(self._stat_peak, int(np.abs(ac).max()))
        self._stat_blocks += 1
        now = time.monotonic()
        if now - self._stat_t < 1.0 or QUIET:
            return
        rms_v = (self._stat_sq / max(self._stat_n, 1)) ** 0.5 * VREF / (1 << ADC_BITS)
        peak_v = self._stat_peak * VREF / (1 << ADC_BITS)
        print(
            f"fs={self.fs:7.1f}Hz blocks/s={self._stat_blocks:3d} "
            f"dc={self.dc * VREF / (1 << ADC_BITS):.2f}V rms={rms_v * 1e3:6.1f}mV "
            f"peak={peak_v * 1e3:6.1f}mV mcu_drops={dropped} missing={self.missing} crc_bad={self.crc_bad}",
            flush=True,
        )
        self._stat_t, self._stat_blocks, self._stat_sq, self._stat_n, self._stat_peak = now, 0, 0.0, 0, 0


# ---- serial transport ------------------------------------------------------
class FrameParser:
    """Byte stream -> (seq, t0_us, dropped, data) tuples. Resyncs on the magic, drops frames with a bad CRC."""

    def __init__(self, node):
        self.node = node
        self.buf = bytearray()

    def feed(self, chunk):
        self.buf += chunk
        while True:
            i = self.buf.find(FRAME_MAGIC)
            if i < 0:
                del self.buf[:-3]                 # keep a partial magic at the tail
                return
            if i:
                del self.buf[:i]
            if len(self.buf) < FRAME_HDR.size:
                return
            magic, seq, t0_us, dropped, n = FRAME_HDR.unpack_from(self.buf)
            total = FRAME_HDR.size + 2 * n + 2
            if n == 0 or n > 4096:                # not a real header: skip this magic, search on
                del self.buf[:1]
                continue
            if len(self.buf) < total:
                return
            frame = bytes(self.buf[:total])
            del self.buf[:total]
            (crc,) = struct.unpack_from("<H", frame, total - 2)
            if crc != crc16_ccitt(frame[:-2]):
                self.node.crc_bad += 1
                continue
            self.node.on_block(seq, t0_us, dropped, frame[FRAME_HDR.size:total - 2])


def find_port():
    from serial.tools import list_ports

    ports = list(list_ports.comports())
    for vid in (ESPRESSIF_VID, CP210X_VID):
        for p in ports:
            if p.vid == vid:
                return p.device
    for p in ports:
        if "usbmodem" in p.device or "usbserial" in p.device:
            return p.device
    sys.exit("no ESP32-S3 found on USB (looked for an Espressif or CP210x device); pass --port /dev/cu.xxx")


def run_serial(node, port, baud, seconds=0):
    import serial

    if port.strip().lower() in ("", "auto"):
        port = find_port()
    ser = serial.Serial(port, baud, timeout=0.2)
    ser.reset_input_buffer()
    print(f"reading {port}", flush=True)
    parser = FrameParser(node)
    t_first = None
    while True:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            parser.feed(chunk)
            t_first = t_first or time.monotonic()
        if seconds and t_first and time.monotonic() - t_first >= seconds:
            break
    if node.wav:
        node.wav.close()
        with wave.open(WAV_PATH) as w:
            print(f"wrote {WAV_PATH}: {w.getnframes() / w.getframerate():.1f} s @ {w.getframerate()} Hz", flush=True)


def main():
    global WAV_PATH
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", default=os.environ.get("KEIKO_SERIAL_PORT", "auto"), help="serial device (default: auto)")
    ap.add_argument("--baud", type=int, default=int(os.environ.get("KEIKO_SERIAL_BAUD", "921600")))
    ap.add_argument("--wav", default=WAV_PATH, help="append a 16-bit mono WAV here (default: KEIKO_WAV)")
    ap.add_argument("--seconds", type=float, default=0, help="stop this long after the first frame (0 = run until ctrl-c)")
    a = ap.parse_args()
    WAV_PATH = a.wav

    node = Node()
    watch_settings()
    print(f"keiko esp32-s3 node -> udp {UDP_HOST}:{UDP_PORT} node {NODE_ID}" + (f", wav {WAV_PATH}" if WAV_PATH else ""), flush=True)
    run_serial(node, a.port, a.baud, a.seconds)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
