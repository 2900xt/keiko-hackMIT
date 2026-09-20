# Keiko pipeline: UDP stream from a hydrophone node -> whale CNN -> detections on the website.
#
#   make venv    one-time: ../.venv with torch, librosa, ... (~2 GB, a few minutes)
#   make test    offline regression: white noise -> 0 events, humpback sample -> a humpback event
#   make demo    no board needed: loops the humpback sample into the pipeline as if a node were streaming it
#   make live    the real thing: points the UNO Q node's stream at this machine and runs the pipeline
#                (board on USB for control, both on the same Wi-Fi, e.g. a phone hotspot: `make wifi` in ../firmware/unoq;
#                add ARGS="--archive" to write to the site database; VIA=usb carries the stream over the cable instead)
#
# The node side lives in ../firmware/unoq (make start / logs / record there).

PY   ?= ../.venv/bin/python
ARGS ?=
VIA  ?= wifi

.PHONY: venv test demo live

venv:
	python3 -m venv ../.venv && ../.venv/bin/pip install -q -r requirements.txt

test:
	$(PY) test_pipeline.py

demo:
	-PY=$(PY) ./demo.sh $(ARGS)

live:
	-PY=$(PY) VIA=$(VIA) ./live.sh $(ARGS)
