//
// Samples the piezo follower on A0 at a fixed rate from a cooperative Zephyr
// thread paced by a kernel timer, and ships raw 14-bit ADC counts to the Linux
// side in blocks over the Bridge:
//
//   Bridge.notify("hydro/block", seq, t0_us, dropped, bytes)
//
//   seq      uint32  block counter
//   t0_us    uint32  micros() at the first sample of the block
//   dropped  uint32  blocks overwritten because the Bridge could not keep up
//   bytes    bin     BLOCK little-endian int16, raw ADC counts 0..16383
//
// The Bridge is a 115200-baud UART, so the budget is ~11 kB/s. 16-bit samples
// at ~3.3 kHz is 6.7 kB/s. Do not raise the rate without dropping to 8-bit or
// packing 12-bit samples.

#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include <zephyr/kernel.h>

// ---- configuration ---------------------------------------------------------
static const uint32_t SAMPLE_PERIOD_US = 300;   // ~3333 Hz. Zephyr rounds this to whole ticks (100 us here); the
                                                // Python side measures the real rate from t0_us, so it self-corrects.
static const pin_size_t ADC_PIN         = A0;
static const int        ADC_BITS        = 14;
static const size_t     BLOCK           = 256;  // samples per Bridge message (512 bytes)
static const size_t     NBLOCKS         = 4;    // ring depth; sender may lag by NBLOCKS-1 blocks

// ---- sampler <-> sender plumbing ------------------------------------------
static int16_t  ring[NBLOCKS][BLOCK];
static uint32_t ring_t0_us[NBLOCKS];
static uint32_t dropped_blocks = 0;

K_MSGQ_DEFINE(ready_q, sizeof(uint8_t), NBLOCKS - 1, 1);  // depth NBLOCKS-1 keeps the block being filled private
K_SEM_DEFINE(tick_sem, 0, 1);                             // max 1: late ticks coalesce instead of piling up

static struct k_timer tick_timer;
static void on_tick(struct k_timer*) { k_sem_give(&tick_sem); }

K_THREAD_STACK_DEFINE(sampler_stack, 1024);
static struct k_thread sampler_thread;

static void sampler(void*, void*, void*) {
  uint8_t b = 0;
  size_t  i = 0;
  ring_t0_us[b] = micros();
  for (;;) {
    k_sem_take(&tick_sem, K_FOREVER);
    int raw = analogRead(ADC_PIN);
    if (raw < 0) raw = 1 << (ADC_BITS - 1);   // adc error -> mid-scale, keeps timing intact
    ring[b][i++] = (int16_t)raw;
    if (i == BLOCK) {
      i = 0;
      if (k_msgq_put(&ready_q, &b, K_NO_WAIT) == 0) {
        b = (b + 1) % NBLOCKS;
      } else {
        dropped_blocks++;                     // sender is behind: reuse this block, keep sampling
      }
      ring_t0_us[b] = micros();
    }
  }
}

// ---- Arduino ---------------------------------------------------------------
void setup() {
  Bridge.begin();
  analogReadResolution(ADC_BITS);
  analogRead(ADC_PIN);                        // first call does the pinctrl/channel setup; do it before the timer starts

  k_thread_create(&sampler_thread, sampler_stack, K_THREAD_STACK_SIZEOF(sampler_stack),
                  sampler, NULL, NULL, NULL,
                  K_PRIO_COOP(1), 0, K_NO_WAIT);   // cooperative: preempts main + bridge threads on every tick
  k_thread_name_set(&sampler_thread, "hydro_sampler");

  k_timer_init(&tick_timer, on_tick, NULL);
  k_timer_start(&tick_timer, K_USEC(SAMPLE_PERIOD_US), K_USEC(SAMPLE_PERIOD_US));
}

void loop() {
  static uint32_t seq = 0;
  uint8_t b;
  k_msgq_get(&ready_q, &b, K_FOREVER);        // blocks (not spins), so the sampler thread gets the CPU

  const uint8_t* p = reinterpret_cast<const uint8_t*>(ring[b]);
  MsgPack::bin_t<uint8_t> payload(p, p + BLOCK * sizeof(int16_t));
  Bridge.notify("hydro/block", seq++, ring_t0_us[b], dropped_blocks, payload);
}
