# Keiko nRF7002 DK hydrophone node.
#
# On this Mac
#   make sdk         one-time: nrfutil + nRF Connect SDK $(NCS_VERSION) toolchain into ~/ncs (~4 GB)
#   make build       compile (also the type check -- there is no board-side compile here)
#   make flash       program the DK over its J-Link USB (the nRF5340 app core; the net core is untouched)
#   make monitor     serial console: the once-a-second health line, Wi-Fi state, IP address
#   make listen      receive the UDP stream here            make record   DURATION=30 s into recordings/<utc>.wav
#   make sim         emulate the node from this Mac (no board needed; same packets, see host/sim_node.py)
#   make test        offline test of the packet format via the simulator
#   make retarget UDP_HOST=<ip>   rebuild + reflash with the stream sent to that machine (no Linux side to hot-reload)
#
# Settings (Wi-Fi, UDP target, node id, sample rate) live in keiko.conf. Any of them can be overridden per
# build: make build flash SSID=hotspot PSK=secret UDP_HOST=10.0.0.5 NODE_ID=1
#
# `west` must come from the nRF Connect toolchain. Either open a toolchain shell first
# (`nrfutil sdk-manager toolchain launch --ncs-version $(NCS_VERSION) --shell`, or VS Code's nRF Connect terminal),
# or leave `west` off PATH and this Makefile wraps every call in that launcher itself.

BOARD       ?= nrf7002dk/nrf5340/cpuapp
NCS         ?= $(HOME)/ncs
NCS_VERSION ?= v3.0.0
BUILD       ?= build
PORT        ?= 5005
DURATION    ?= 30
PYTHON      ?= python3
# first J-Link VCOM of the DK (VCOM0 = app core console at 115200)
PORT_DEV    ?= $(firstword $(wildcard /dev/tty.usbmodem*))

WEST ?= $(if $(shell command -v west 2>/dev/null),west,nrfutil sdk-manager toolchain launch --ncs-version $(NCS_VERSION) -- west)

# per-build overrides of keiko.conf (empty = keep the file's value)
SSID     ?=
PSK      ?=
UDP_HOST ?=
NODE_ID  ?=
# (Kconfig strings need their double quotes to survive the shell, hence the '"..."')
OVERRIDES = $(if $(SSID),-DCONFIG_KEIKO_WIFI_SSID='"$(SSID)"') $(if $(PSK),-DCONFIG_KEIKO_WIFI_PSK='"$(PSK)"') \
            $(if $(UDP_HOST),-DCONFIG_KEIKO_UDP_HOST='"$(UDP_HOST)"') $(if $(NODE_ID),-DCONFIG_KEIKO_NODE_ID=$(NODE_ID))

.PHONY: sdk build check flash retarget monitor listen record sim test clean

# ---- Mac-side --------------------------------------------------------------
sdk:
	@command -v nrfutil >/dev/null || { echo "install nrfutil first: https://www.nordicsemi.com/Products/Development-tools/nRF-Util (then: nrfutil install sdk-manager device)"; exit 1; }
	nrfutil sdk-manager toolchain install --ncs-version $(NCS_VERSION)
	test -d $(NCS)/.west || (mkdir -p $(NCS) && cd $(NCS) && $(WEST) init -m https://github.com/nrfconnect/sdk-nrf --mr $(NCS_VERSION) . && $(WEST) update)
	@echo "ok: nRF Connect SDK $(NCS_VERSION) in $(NCS)"

# EXTRA_CONF_FILE layers keiko.conf over prj.conf; -p auto reconfigures when a .conf changed
build:
	cd $(NCS) && $(WEST) build -b $(BOARD) -d $(CURDIR)/$(BUILD) -p auto $(CURDIR) -- -DEXTRA_CONF_FILE=$(CURDIR)/keiko.conf $(OVERRIDES)

check: build

test:
	$(PYTHON) host/test_node.py

sim:
	$(PYTHON) host/sim_node.py --port $(PORT) $(ARGS)

listen:
	$(PYTHON) host/udp_listen.py --port $(PORT)

# Record DURATION seconds of the UDP stream into recordings/<utc>.wav on this Mac. The node keeps running;
# the stream must reach this Mac (KEIKO_UDP_HOST = its IP, or the subnet broadcast default).
record:
	@mkdir -p recordings
	$(PYTHON) host/udp_listen.py --port $(PORT) --wav recordings/$$(date -u +%Y%m%dT%H%M%SZ).wav --seconds $(DURATION)
	@ls -la recordings | tail -1

# ---- board-side ------------------------------------------------------------
flash: build
	cd $(NCS) && $(WEST) flash -d $(CURDIR)/$(BUILD)

# Point the node at another receiver. Unlike the UNO Q there is no file to hot-reload: it is a rebuild + reflash (~1 min).
retarget:
	@test -n "$(UDP_HOST)" || { echo "usage: make retarget UDP_HOST=<ip of the machine running the pipeline>  (or 255.255.255.255)"; exit 1; }
	$(MAKE) flash UDP_HOST=$(UDP_HOST)
	@echo "node now streams to $(UDP_HOST):$(PORT) - check with make monitor / make listen"

monitor:
	@test -n "$(PORT_DEV)" || { echo "no DK on USB (no /dev/tty.usbmodem*). Plug the J-Link USB in, retry, or pass PORT_DEV=."; exit 1; }
	@echo "console on $(PORT_DEV) 115200 (ctrl-a k to quit screen)"
	screen $(PORT_DEV) 115200

clean:
	rm -rf $(BUILD)
