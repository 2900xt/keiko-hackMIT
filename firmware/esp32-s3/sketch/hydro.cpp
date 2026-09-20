//
// Samples the piezo follower on GPIO1 (ADC1_CH0) at a fixed rate from a
// high-priority FreeRTOS task paced by a hardware timer, and ships raw 12-bit
// ADC counts to the laptop in framed blocks over native USB CDC:
//
//   "KBLK" | seq | t0_us | dropped | n | n x int16 | crc16
//
//   seq      uint32  block counter
//   t0_us    uint32  esp_timer_get_time() at the first sample of the block
//   dropped  uint32  blocks overwritten because the sender could not keep up
//   n        uint16  samples in this block (BLOCK)
//   data     n x little-endian int16, raw ADC counts 0..4095
//   crc      uint16  CRC-16/CCITT-FALSE over everything before it
//
// Same shape as the UNO Q node's Bridge.notify("hydro/block", …), just on a
// wire with no message boundaries, hence the magic + CRC. USB CDC moves
// ~1 MB/s, so unlike the UNO Q's 115200-baud Bridge the sample rate is limited
// by the ADC conversion time (~25 us), not the link.

#include <Arduino.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

// ---- configuration ---------------------------------------------------------
static const uint32_t SAMPLE_PERIOD_US = 125;   // 8000 Hz. The 1 MHz timer makes this exact; the Python side still
                                                // measures the real rate from t0_us.
static const uint8_t  ADC_PIN          = 1;     // GPIO1 = ADC1_CH0. Stay on ADC1: ADC2 is unusable while Wi-Fi is on.
static const int      ADC_BITS         = 12;
static const size_t   BLOCK            = 256;   // samples per frame (512 bytes payload, ~31 frames/s at 8 kHz)
static const size_t   NBLOCKS          = 4;     // ring depth; sender may lag by NBLOCKS-1 blocks
static const BaseType_t SAMPLER_CORE   = 1;     // the app core (loop() runs there too; the sampler outranks it)

// ---- frame -----------------------------------------------------------------
struct __attribute__((packed)) FrameHeader {
  char     magic[4];
  uint32_t seq;
  uint32_t t0_us;
  uint32_t dropped;
  uint16_t n;
};

static uint16_t crc16_ccitt(uint16_t crc, const uint8_t* p, size_t len) {
  while (len--) {
    crc ^= (uint16_t)(*p++) << 8;
    for (int i = 0; i < 8; i++) crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

// ---- sampler <-> sender plumbing ------------------------------------------
static int16_t  ring[NBLOCKS][BLOCK];
static uint32_t ring_t0_us[NBLOCKS];
static uint32_t dropped_blocks = 0;

static QueueHandle_t     ready_q;     // depth NBLOCKS-1 keeps the block being filled private
static SemaphoreHandle_t tick_sem;    // binary: late ticks coalesce instead of piling up
static hw_timer_t*       tick_timer;

static void IRAM_ATTR on_tick() {
  BaseType_t woken = pdFALSE;
  xSemaphoreGiveFromISR(tick_sem, &woken);
  if (woken) portYIELD_FROM_ISR();
}

static void sampler(void*) {
  uint8_t b = 0;
  size_t  i = 0;
  ring_t0_us[b] = (uint32_t)esp_timer_get_time();
  for (;;) {
    xSemaphoreTake(tick_sem, portMAX_DELAY);
    int raw = analogRead(ADC_PIN);
    if (raw < 0) raw = 1 << (ADC_BITS - 1);   // adc error -> mid-scale, keeps timing intact
    ring[b][i++] = (int16_t)raw;
    if (i == BLOCK) {
      i = 0;
      if (xQueueSend(ready_q, &b, 0) == pdTRUE) {
        b = (b + 1) % NBLOCKS;
      } else {
        dropped_blocks++;                     // sender is behind: reuse this block, keep sampling
      }
      ring_t0_us[b] = (uint32_t)esp_timer_get_time();
    }
  }
}

// ---- Arduino ---------------------------------------------------------------
void setup() {
  Serial.begin(921600);                       // baud is ignored on native USB CDC; matters only if Serial is a UART
  Serial.setTxTimeoutMs(50);                  // no host reading -> writes give up instead of stalling the sender
  analogReadResolution(ADC_BITS);
  analogSetPinAttenuation(ADC_PIN, ADC_11db); // 0..~3.1 V full scale; the follower idles at ~1.7 V
  analogRead(ADC_PIN);                        // first call does the channel setup; do it before the timer starts

  tick_sem = xSemaphoreCreateBinary();
  ready_q  = xQueueCreate(NBLOCKS - 1, sizeof(uint8_t));
  xTaskCreatePinnedToCore(sampler, "hydro_sampler", 4096, NULL, configMAX_PRIORITIES - 1, NULL, SAMPLER_CORE);

  tick_timer = timerBegin(1000000);           // 1 MHz -> alarm counts are microseconds
  timerAttachInterrupt(tick_timer, on_tick);
  timerAlarm(tick_timer, SAMPLE_PERIOD_US, true, 0);
}

void loop() {
  static uint32_t seq = 0;
  uint8_t b;
  xQueueReceive(ready_q, &b, portMAX_DELAY);  // blocks (not spins), so the sampler task gets the CPU

  FrameHeader h = {{'K', 'B', 'L', 'K'}, seq++, ring_t0_us[b], dropped_blocks, (uint16_t)BLOCK};
  const uint8_t* data = reinterpret_cast<const uint8_t*>(ring[b]);
  uint16_t crc = crc16_ccitt(0xFFFF, reinterpret_cast<const uint8_t*>(&h), sizeof h);
  crc = crc16_ccitt(crc, data, BLOCK * sizeof(int16_t));

  Serial.write(reinterpret_cast<const uint8_t*>(&h), sizeof h);
  Serial.write(data, BLOCK * sizeof(int16_t));
  Serial.write(reinterpret_cast<const uint8_t*>(&crc), sizeof crc);
}
