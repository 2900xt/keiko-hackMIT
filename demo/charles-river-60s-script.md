# Keiko — 60-second demo video script

**Style:** Mark Rober. Cold open on the payoff, fast build montage, one real moment of truth, data payoff, punchline out.
**Runtime:** 60s. **VO:** ~170 words, energetic, conversational, no narrator voice.
**Location:** Charles River, MIT side (dock at Walter C. Wood Sailing Pavilion or the Harvard Bridge landing).

---

## 0:00–0:07 — COLD OPEN (hook)

**SHOT:** Hard cut, already mid-action. Low angle at water level, buoy swinging on its tether, then *splash*. Cut the
splash on the first VO beat. No logo, no intro card.

**VO:**
> This is a buoy we built in a day. And we're about to drop it in the Charles River to find out if it can hear a whale.

**ON-SCREEN:** nothing yet — let the splash carry it.

**NOTE:** Shoot the drop 4+ times: (1) wide from the dock, (2) water-level slow-mo, (3) GoPro on the tether looking down,
(4) underwater half-in/half-out. You only need one to land.

---

## 0:07–0:16 — THE STAKES

**SHOT:** Whale stock footage / NOAA right whale b-roll. Then a map zoom: Boston Harbor shipping lanes, ship icons crossing.

**VO:**
> There are about 370 North Atlantic right whales left. The single biggest thing killing them is boats — and the only way
> a boat knows one is there is if somebody's listening.

**ON-SCREEN:** `~370 LEFT` big, then `#1 CAUSE: SHIP STRIKES`

**NOTE:** Verify the current NOAA population estimate the morning you post — it changes yearly.

---

## 0:16–0:32 — THE BUILD (montage, fast cuts, ~3s each)

**SHOT A:** Three 27 mm piezo discs soldered in parallel, then submerged in epoxy in a cup. *Tap tap* on the disc → the
waveform on the laptop spikes in sync.
**SHOT B:** 3D printer laying down the hull, timelapse. Lid threading on.
**SHOT C:** ESP32 dropped in its pocket, antenna up, power bank in, lid sealed, hand-tightened.
**SHOT D:** Bathtub/bucket test — buoy floats upright, someone flicks it, it self-rights.

**VO:**
> A commercial hydrophone costs more than my tuition. Ours is three piezo discs in a cup of epoxy. That feeds an ESP32
> that samples eight thousand times a second and streams it over Wi-Fi to a neural net trained on a hundred and
> twenty-six thousand whale recordings. All of it inside a 3D-printed hull that weighs half a kilo and floats — we checked.

**ON-SCREEN:** `3 PIEZO DISCS` · `8 kHz` · `126,000 CLIPS · 22 SPECIES` · `545 g · FLOATS (barely)`

**NOTE:** The self-righting flick shot is the laugh — hold it a half-beat longer than feels right.

---

## 0:32–0:40 — MOMENT OF TRUTH

**SHOT:** Real time, no music, ambient sound only. Buoy lowered hand-over-hand off the dock. Hold on it bobbing. Cut to
laptop screen — nothing. Beat. Then the spectrogram starts scrolling.

**VO:**
> Okay. Moment of truth.

**ON-SCREEN:** `CHARLES RIVER · LIVE` with a running clock.

**NOTE:** Let ~2 full seconds of silence sit before the spectrogram moves. The pause is the whole shot.

---

## 0:40–0:52 — PAYOFF (the data)

**SHOT:** Split screen — buoy bobbing on the left, laptop/phone showing the live site on the right. A motorboat passes;
the spectrogram lights up and a detection card drops into the feed. Cut to a crew shell sliding by, oars in the water,
and the classifier tagging it too.

**VO:**
> It's hearing everything. That's a motorboat. That's an eight-man crew shell. Every three seconds it cuts the sound into
> a window, and fifteen milliseconds later it's on the map.

**ON-SCREEN:** `MOTORBOAT · 0.94` · `CREW SHELL · 0.88` · `3 s WINDOW → 15 ms → LIVE`

**NOTE:** Screen-record the live site during the actual deployment — do not fake this in post. If nothing passes in
10 minutes, have a teammate row by.

---

## 0:52–1:00 — THE BUTTON

**SHOT:** Back to the dock, wide. Team standing over the buoy in the water. Then hard cut to the ocean / Cape Cod map
with the right whale alert firing.

**VO:**
> To be clear — there are no whales in the Charles River. That's the point. If it can hear a duck paddle past MIT,
> it can hear a right whale off Cape Cod. Then it texts somebody.

**ON-SCREEN:** `RIGHT WHALE DETECTED` alert card, then `KEIKO` + the site URL.

**NOTE:** Optional tag after the cut: duck paddles past the buoy, classifier outputs `unknown`. Two seconds, then black.

---

## Shot list (what you actually have to film)

| # | Shot | Where | Must-have? |
|---|---|---|---|
| 1 | Buoy drop / splash — 4 angles | Dock | **YES** |
| 2 | Buoy bobbing, untethered look, 20s hold | Dock | **YES** |
| 3 | Laptop screen-record of live site during deployment | Dock | **YES** |
| 4 | Piezo discs + epoxy cup, tap-test with waveform | Bench | YES |
| 5 | Print timelapse + lid threading | Bench | nice |
| 6 | Electronics going into the hull | Bench | YES |
| 7 | Float / self-right test in a bucket | Anywhere | nice |
| 8 | Boat + crew shell passing the buoy | Dock | **YES** |
| 9 | Team wide shot on the dock | Dock | YES |
| 10 | Duck (opportunistic) | Dock | lol |

## Production notes

- **Audio is the product.** Record real hydrophone audio and use it under the payoff section — the actual underwater
  motorboat sound is more convincing than any music cue.
- **Music:** upbeat but sparse. Drop it out completely for 0:32–0:40 so the moment of truth has silence, bring it back
  hard on the first detection.
- **Captions:** burn them in. Most of this gets watched muted.
- **Fill the blanks before shooting:** current NOAA right whale count, real per-unit build cost, real confidence values
  from the deployment.
