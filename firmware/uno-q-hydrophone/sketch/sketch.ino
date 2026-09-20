// Keiko — piezo hydrophone level reader (Arduino UNO Q, MCU side).
// Piezo red lead -> A0, black lead -> GND, optional 1 MOhm across the two.
#include <Arduino_RouterBridge.h>

int readHydro() { return analogRead(A0); }

void setup() {
  Bridge.begin();
  Bridge.provide("readHydro", readHydro);
}

void loop() { delay(1); }
