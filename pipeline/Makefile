# Keiko pipeline: UDP stream from a hydrophone node -> whale CNN -> detections on the website.
#
#   make venv    one-time: ../.venv with torch, librosa, ... (~2 GB, a few minutes)
#   make test    offline regression: white noise -> 0 events, humpback sample -> a humpback event
#   make demo    no board needed: loops the humpback sample into the pipeline as if a node were streaming it
#   make live    the real thing: points the UNO Q node's stream at this machine and runs the pipeline
#                (board on USB for control, both on the same Wi-Fi, e.g. a phone hotspot: `make wifi` in ../firmware/unoq;
#                add ARGS="--archive" to write to the site database; VIA=usb carries the stream over the cable instead)
#   make live-nrf  same with the nRF7002 DK node (../firmware/nrf7002): nothing to point, its stream target is baked in
#                at flash time (keiko.conf, default = subnet broadcast), so this just runs the pipeline listening on :5005
#   make server  the central server (../server/keiko_server.py): localizes + tracks detections, feeds the site's Live tab.
#                Run it first, then `make live ARGS="--server ws://127.0.0.1:8765"` (or make demo ARGS=...) and `npm run dev` in ../site.
#
# The node side lives in ../firmware/unoq (make start / logs / record there) or ../firmware/nrf7002 (make flash / monitor / record).

PY   ?= ../.venv/bin/python
ARGS ?=
VIA  ?= usb

.PHONY: venv test demo live live-nrf server

venv:
	python3 -m venv ../.venv && ../.venv/bin/pip install -q -r requirements.txt

test:
	$(PY) test_pipeline.py

demo:
	-PY=$(PY) ./demo.sh $(ARGS)

live:
	-PY=$(PY) VIA=$(VIA) ./live.sh $(ARGS)

live-nrf:
	$(PY) keiko_pipeline.py --buoy KEIKO-02 $(ARGS)

server:
	$(PY) ../server/keiko_server.py $(ARGS)
