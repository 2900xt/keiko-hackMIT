"""Keiko — piezo hydrophone level monitor (Arduino UNO Q, Linux side).

Polls the MCU for the raw A0 reading, tracks the resting level, and prints
the deviation as a bar so a tap or splash on the potted piezo is obvious.
"""
from arduino.app_utils import *
import time

baseline = None
while True:
    v = Bridge.call("readHydro")
    if baseline is None:
        baseline = v
    baseline = 0.99 * baseline + 0.01 * v      # slow tracking of the resting level
    dev = abs(v - baseline)
    print(f"{v:4d}  dev={dev:4.0f}  {'#' * int(dev / 8)}")
    time.sleep(0.01)
