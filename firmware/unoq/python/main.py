#!/usr/bin/env python3
"""Keiko hydrophone node — Arduino UNO Q, Linux side.

Receives raw ADC blocks from the MCU sketch ("hydro/block" Bridge notifications),
then:
  * prints a once-a-second health line (measured sample rate, DC bias, RMS, drops)
  * forwards each block as a UDP datagram to the pipeline (same role as the
    ESP32-S3 / nRF7002 nodes, see PACKET FORMAT below)
  * optionally appends everything to a WAV file

Runs under `arduino-app-cli app start` (uses arduino.app_utils). If that package
is missing it falls back to talking MessagePack-RPC to the router socket directly.

Environment:
  KEIKO_UDP_HOST   default 127.0.0.1      pipeline receiver
  KEIKO_UDP_PORT   default 5005
  KEIKO_NODE_ID    default 0              node id in the packet header
  KEIKO_WAV        default unset          path to append a 16-bit mono WAV log
  KEIKO_QUIET      default unset          set to silence the health line

PACKET FORMAT (little-endian), one datagram per block:
  magic  4s  b"KEIK"
  ver    B   1
  node   B   KEIKO_NODE_ID
  fmt    B   0 = raw ADC counts as int16
  bits   B   ADC resolution (14)
  fs     f   measured sample rate, Hz
  seq    I   MCU block counter
  t_ns   Q   host CLOCK_MONOTONIC ns when the block arrived
  n      H   sample count
  data   n * int16
"""

import os
import struct
import socket
import sys
import time
import wave

import numpy as np

METHOD = "hydro/block"
ADC_BITS = 14
VREF = 3.3

UDP_HOST = os.environ.get("KEIKO_UDP_HOST", "127.0.0.1")
UDP_PORT = int(os.environ.get("KEIKO_UDP_PORT", "5005"))
NODE_ID = int(os.environ.get("KEIKO_NODE_ID", "0"))
WAV_PATH = os.environ.get("KEIKO_WAV")
QUIET = bool(os.environ.get("KEIKO_QUIET"))

HDR = struct.Struct("<4sBBBBfIQH")


class Node:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.fs = 0.0                 # measured from MCU timestamps
        self.dc = None                # running mean of raw counts
        self.last_seq = None
        self.last_t0 = None
        self.missing = 0
        self.wav = None
        self._stat_t = time.monotonic()
        self._stat_blocks = 0
        self._stat_sq = 0.0
        self._stat_n = 0
        self._stat_peak = 0

    # ---- Bridge callback ---------------------------------------------------
    def on_block(self, seq, t0_us, dropped, data):
        t_ns = time.monotonic_ns()
        if isinstance(data, (list, tuple)):          # in case the transport hands us a list of ints
            data = bytes(data)
        x = np.frombuffer(data, dtype="<i2")

        # sample rate from consecutive MCU timestamps (micros() wraps every ~71 min)
        if self.last_t0 is not None and seq == self.last_seq + 1:
            dt = (t0_us - self.last_t0) & 0xFFFFFFFF
            if dt:
                fs = len(x) * 1e6 / dt
                self.fs = fs if self.fs == 0 else 0.9 * self.fs + 0.1 * fs
        if self.last_seq is not None and seq != self.last_seq + 1:
            self.missing += (seq - self.last_seq - 1) & 0xFFFFFFFF
        self.last_seq, self.last_t0 = seq, t0_us

        # DC tracker (the follower biases A0 to ~1.7 V; this is the number to check)
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
            f"peak={peak_v * 1e3:6.1f}mV mcu_drops={dropped} missing={self.missing}",
            flush=True,
        )
        self._stat_t, self._stat_blocks, self._stat_sq, self._stat_n, self._stat_peak = now, 0, 0.0, 0, 0


# ---- transports ------------------------------------------------------------
def run_applab(node):
    from arduino.app_utils import App, Bridge  # only exists inside the App Lab runtime

    Bridge.provide(METHOD, node.on_block)
    App.run()


def run_router_socket(node, path="/var/run/arduino-router.sock"):
    """Talk MessagePack-RPC to the router directly (no App Lab runtime).

    Any client may register a method with "$/register" and the router forwards
    matching requests/notifications to it (see arduino-router's README). This is
    what arduino.app_utils does under the hood; we just skip the wrapper.
    """
    import msgpack

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(path)
    s.sendall(msgpack.packb([0, 1, "$/register", [METHOD]]))
    unp = msgpack.Unpacker(raw=False)
    while True:
        chunk = s.recv(1 << 16)
        if not chunk:
            raise ConnectionError("router closed the socket")
        unp.feed(chunk)
        for msg in unp:
            kind = msg[0]
            if kind == 2 and msg[1] == METHOD:                 # notification
                node.on_block(*msg[2])
            elif kind == 0:                                    # request: answer it so the router is happy
                _, mid, method, params = msg
                result = node.on_block(*params) if method == METHOD else None
                s.sendall(msgpack.packb([1, mid, None, result]))
            # kind == 1: response to our $/register, ignore


def main():
    node = Node()
    print(f"keiko unoq node -> udp {UDP_HOST}:{UDP_PORT}" + (f", wav {WAV_PATH}" if WAV_PATH else ""), flush=True)
    try:
        import arduino.app_utils  # noqa: F401
    except ImportError:
        print("arduino.app_utils not available, using router socket", flush=True)
        run_router_socket(node)
    else:
        run_applab(node)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
