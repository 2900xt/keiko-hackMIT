# UNO Q piezo hydrophone monitor

Arduino App Lab app for the Arduino UNO Q. The sketch (STM32) exposes `analogRead(A0)`
over Bridge; the Python side (Linux) polls it and prints the deviation from the resting level.

## Wiring

| Piezo lead | Breadboard | UNO Q |
|---|---|---|
| red | row 1 | A0 |
| black | row 5 | GND |
| 1 MΩ (optional) | across row 1 and row 5 | |

Optional 100 kΩ in series between row 1 and A0 protects the pin from hard taps.

## Run

1. Open Arduino App Lab, connect the UNO Q directly over USB-C (no hub).
2. Open this folder as an App, click **Run**.
3. Tap the potted piezo, or dunk it and tap the container: the bar in the console spikes.

The reading is a loudness envelope, not audio. Next step: sample A0 at 10–20 kHz in the
sketch and stream frames over Bridge to the `pipeline/` UDP receiver.
