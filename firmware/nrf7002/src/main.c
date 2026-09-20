//
// Keiko hydrophone node — nRF7002 DK (nRF5340 + nRF7002 Wi-Fi companion).
//
// Samples the piezo front end on AIN0 at a fixed rate from a cooperative
// Zephyr thread paced by a kernel timer, and ships raw 12-bit SAADC counts to
// the pipeline as one UDP datagram per block. Same sampler/ring/sender split
// as firmware/unoq/sketch/hydro.cpp, but there is no Linux side here: the MCU
// owns the Wi-Fi link and writes the "KEIK" header itself.
//
//   magic 4s "KEIK" | ver B 1 | node B | fmt B 0=int16 raw ADC | bits B 12 |
//   fs f Hz | seq I | t_ns Q node uptime | n H | n x int16 (little-endian)
//
// fs is measured from the block timestamps on the node (same EMA the UNO Q's
// Python side uses), so a period rounded to RTC ticks still reports the real
// rate. t_ns is this node's uptime, not a shared clock — TDOA needs SNTP.
//
// Budget: Wi-Fi is not the bottleneck the UNO Q's 115200-baud Bridge was.
// 12-bit samples at 8192 Hz is 16 kB/s = 32 datagrams/s of 538 bytes.

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/net_event.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/net/dhcpv4.h>
#include <zephyr/net/socket.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/logging/log.h>
#include <errno.h>
#include <math.h>
#include <string.h>

LOG_MODULE_REGISTER(keiko, LOG_LEVEL_INF);

// ---- configuration (Kconfig: keiko.conf / prj.conf) ------------------------
#define SAMPLE_PERIOD_TICKS CONFIG_KEIKO_SAMPLE_PERIOD_TICKS  // RTC runs at 32768 Hz: 4 ticks = 122 us = 8192 Hz
#define BLOCK               CONFIG_KEIKO_BLOCK                // samples per datagram
#define NBLOCKS             4                                 // ring depth; sender may lag by NBLOCKS-1 blocks
#define NODE_ID             CONFIG_KEIKO_NODE_ID
#define ADC_BITS            12
#define ADC_FULL_SCALE_MV   CONFIG_KEIKO_ADC_FULL_SCALE_MV    // 0.6 V ref / gain in the overlay (1/3 -> 1800 mV)

static const struct adc_dt_spec adc_ch = ADC_DT_SPEC_GET_BY_IDX(DT_PATH(zephyr_user), 0);
static const struct gpio_dt_spec led_run  = GPIO_DT_SPEC_GET_OR(DT_ALIAS(led0), gpios, {0});  // blinks once per health line
static const struct gpio_dt_spec led_wifi = GPIO_DT_SPEC_GET_OR(DT_ALIAS(led1), gpios, {0});  // on while the link is up

// ---- sampler <-> sender plumbing ------------------------------------------
static int16_t  ring[NBLOCKS][BLOCK];
static uint32_t ring_t0_us[NBLOCKS];
static uint32_t dropped_blocks;             // blocks overwritten because the sender could not keep up

K_MSGQ_DEFINE(ready_q, sizeof(uint8_t), NBLOCKS - 1, 1);  // depth NBLOCKS-1 keeps the block being filled private
K_SEM_DEFINE(tick_sem, 0, 1);                             // max 1: late ticks coalesce instead of piling up

static struct k_timer tick_timer;
static void on_tick(struct k_timer *t) { ARG_UNUSED(t); k_sem_give(&tick_sem); }

static inline uint32_t now_us(void) { return (uint32_t)k_ticks_to_us_floor64(k_uptime_ticks()); }
static inline uint64_t now_ns(void) { return k_ticks_to_ns_floor64(k_uptime_ticks()); }

K_THREAD_STACK_DEFINE(sampler_stack, 1024);
static struct k_thread sampler_thread;

static void sampler(void *a, void *b_, void *c)
{
    ARG_UNUSED(a); ARG_UNUSED(b_); ARG_UNUSED(c);
    int16_t sample;
    struct adc_sequence seq = { .buffer = &sample, .buffer_size = sizeof(sample) };
    adc_sequence_init_dt(&adc_ch, &seq);

    uint8_t b = 0;
    size_t  i = 0;
    ring_t0_us[b] = now_us();
    for (;;) {
        k_sem_take(&tick_sem, K_FOREVER);
        int raw = (adc_read_dt(&adc_ch, &seq) == 0) ? sample : (1 << (ADC_BITS - 1));  // adc error -> mid-scale, keeps timing intact
        if (raw < 0) raw = 0;                                                            // SAADC can return slightly negative counts near 0 V
        ring[b][i++] = (int16_t)raw;
        if (i == BLOCK) {
            i = 0;
            if (k_msgq_put(&ready_q, &b, K_NO_WAIT) == 0) {
                b = (b + 1) % NBLOCKS;
            } else {
                dropped_blocks++;             // sender is behind: reuse this block, keep sampling
            }
            ring_t0_us[b] = now_us();
        }
    }
}

// ---- Wi-Fi -----------------------------------------------------------------
static struct net_mgmt_event_callback wifi_cb, ipv4_cb;
static K_SEM_DEFINE(ipv4_ready, 0, 1);
static atomic_t link_up;

static void wifi_connect(struct k_work *w);
static K_WORK_DELAYABLE_DEFINE(reconnect_work, wifi_connect);

static void wifi_connect(struct k_work *w)
{
    ARG_UNUSED(w);
    struct net_if *iface = net_if_get_first_wifi();
    struct wifi_connect_req_params p = {
        .ssid        = (const uint8_t *)CONFIG_KEIKO_WIFI_SSID,
        .ssid_length = strlen(CONFIG_KEIKO_WIFI_SSID),
        .psk         = (const uint8_t *)CONFIG_KEIKO_WIFI_PSK,
        .psk_length  = strlen(CONFIG_KEIKO_WIFI_PSK),
        .security    = strlen(CONFIG_KEIKO_WIFI_PSK) ? WIFI_SECURITY_TYPE_PSK : WIFI_SECURITY_TYPE_NONE,
        .channel     = WIFI_CHANNEL_ANY,
        .band        = WIFI_FREQ_BAND_UNKNOWN,
        .mfp         = WIFI_MFP_OPTIONAL,
        .timeout     = SYS_FOREVER_MS,
    };
    LOG_INF("wifi: connecting to \"%s\"", CONFIG_KEIKO_WIFI_SSID);
    int rc = net_mgmt(NET_REQUEST_WIFI_CONNECT, iface, &p, sizeof(p));
    if (rc) {
        LOG_ERR("wifi: connect request failed (%d), retrying in 5 s", rc);
        k_work_schedule(&reconnect_work, K_SECONDS(5));
    }
}

static void on_wifi_event(struct net_mgmt_event_callback *cb, uint32_t ev, struct net_if *iface)
{
    ARG_UNUSED(iface);
    const struct wifi_status *st = cb->info;
    switch (ev) {
    case NET_EVENT_WIFI_CONNECT_RESULT:
        if (st->status) {
            LOG_ERR("wifi: connect failed (%d), retrying in 5 s", st->status);
            k_work_schedule(&reconnect_work, K_SECONDS(5));
        } else {
            LOG_INF("wifi: associated, waiting for DHCP");
            net_dhcpv4_start(net_if_get_first_wifi());
        }
        break;
    case NET_EVENT_WIFI_DISCONNECT_RESULT:
        LOG_WRN("wifi: disconnected, reconnecting in 2 s");
        atomic_set(&link_up, 0);
        if (led_wifi.port) gpio_pin_set_dt(&led_wifi, 0);
        k_work_schedule(&reconnect_work, K_SECONDS(2));
        break;
    }
}

static void on_ipv4_event(struct net_mgmt_event_callback *cb, uint32_t ev, struct net_if *iface)
{
    ARG_UNUSED(iface);
    if (ev != NET_EVENT_IPV4_ADDR_ADD) return;
    char ip[NET_IPV4_ADDR_LEN] = "?";
    if (cb->info && cb->info_length == sizeof(struct in_addr)) {   // the event carries the new address
        net_addr_ntop(AF_INET, cb->info, ip, sizeof(ip));
    }
    LOG_INF("wifi: up, ip %s", ip);
    atomic_set(&link_up, 1);
    if (led_wifi.port) gpio_pin_set_dt(&led_wifi, 1);
    k_sem_give(&ipv4_ready);
}

// ---- UDP -------------------------------------------------------------------
struct __packed keik_hdr {
    char     magic[4];
    uint8_t  ver, node, fmt, bits;
    float    fs;
    uint32_t seq;
    uint64_t t_ns;
    uint16_t n;
};
BUILD_ASSERT(sizeof(struct keik_hdr) == 26, "header must match struct.Struct('<4sBBBBfIQH')");

static int udp_open(struct sockaddr_in *dst)
{
    memset(dst, 0, sizeof(*dst));
    dst->sin_family = AF_INET;
    dst->sin_port = htons(CONFIG_KEIKO_UDP_PORT);
    if (zsock_inet_pton(AF_INET, CONFIG_KEIKO_UDP_HOST, &dst->sin_addr) != 1) {
        // not a dotted quad: resolve it (needs CONFIG_DNS_RESOLVER)
        struct zsock_addrinfo hints = { .ai_family = AF_INET, .ai_socktype = SOCK_DGRAM }, *res;
        int rc = zsock_getaddrinfo(CONFIG_KEIKO_UDP_HOST, NULL, &hints, &res);
        if (rc) {
            LOG_ERR("udp: cannot resolve \"%s\" (%d)", CONFIG_KEIKO_UDP_HOST, rc);
            return -1;
        }
        dst->sin_addr = ((struct sockaddr_in *)res->ai_addr)->sin_addr;
        zsock_freeaddrinfo(res);
    }
    int s = zsock_socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (s < 0) { LOG_ERR("udp: socket failed (%d)", errno); return -1; }
    if (dst->sin_addr.s_addr == 0xFFFFFFFFu) {             // 255.255.255.255
        int one = 1;
        zsock_setsockopt(s, SOL_SOCKET, SO_BROADCAST, &one, sizeof(one));
    }
    char ip[NET_IPV4_ADDR_LEN];
    net_addr_ntop(AF_INET, &dst->sin_addr, ip, sizeof(ip));
    LOG_INF("keiko nrf7002 node %d -> udp %s:%d (%s)", NODE_ID, ip, CONFIG_KEIKO_UDP_PORT, CONFIG_KEIKO_UDP_HOST);
    return s;
}

// ---- main: bring-up, then the sender loop (the UNO Q sketch's loop()) ------
int main(void)
{
    if (led_run.port)  { gpio_pin_configure_dt(&led_run, GPIO_OUTPUT_INACTIVE); }
    if (led_wifi.port) { gpio_pin_configure_dt(&led_wifi, GPIO_OUTPUT_INACTIVE); }

    if (!adc_is_ready_dt(&adc_ch) || adc_channel_setup_dt(&adc_ch) != 0) {
        LOG_ERR("adc: channel setup failed");
        return 0;
    }

    net_mgmt_init_event_callback(&wifi_cb, on_wifi_event, NET_EVENT_WIFI_CONNECT_RESULT | NET_EVENT_WIFI_DISCONNECT_RESULT);
    net_mgmt_add_event_callback(&wifi_cb);
    net_mgmt_init_event_callback(&ipv4_cb, on_ipv4_event, NET_EVENT_IPV4_ADDR_ADD);
    net_mgmt_add_event_callback(&ipv4_cb);
    k_work_schedule(&reconnect_work, K_NO_WAIT);
    k_sem_take(&ipv4_ready, K_FOREVER);

    struct sockaddr_in dst;
    int sock = udp_open(&dst);
    if (sock < 0) return 0;

    // sampler starts only once the socket exists, so the ring never fills with nowhere to go
    k_thread_create(&sampler_thread, sampler_stack, K_THREAD_STACK_SIZEOF(sampler_stack),
                    sampler, NULL, NULL, NULL,
                    K_PRIO_COOP(1), 0, K_NO_WAIT);   // cooperative: preempts main + net threads on every tick
    k_thread_name_set(&sampler_thread, "hydro_sampler");
    k_timer_init(&tick_timer, on_tick, NULL);
    k_timer_start(&tick_timer, K_TICKS(SAMPLE_PERIOD_TICKS), K_TICKS(SAMPLE_PERIOD_TICKS));

    static uint8_t pkt[sizeof(struct keik_hdr) + BLOCK * sizeof(int16_t)];
    struct keik_hdr *h = (struct keik_hdr *)pkt;
    memcpy(h->magic, "KEIK", 4);
    h->ver = 1; h->node = NODE_ID; h->fmt = 0; h->bits = ADC_BITS; h->n = BLOCK;

    uint32_t seq = 0, last_t0 = 0, send_err = 0;
    float fs = 0.f, dc = -1.f;
    // once-a-second health line, same fields as the UNO Q's python/main.py
    int64_t  stat_t = k_uptime_get();
    uint32_t stat_blocks = 0, stat_n = 0; float stat_sq = 0.f; int stat_peak = 0;

    for (;;) {
        uint8_t b;
        k_msgq_get(&ready_q, &b, K_FOREVER);   // blocks (not spins), so the sampler thread gets the CPU
        const int16_t *x = ring[b];
        uint32_t t0 = ring_t0_us[b];

        if (seq) {                              // sample rate from consecutive block timestamps
            uint32_t dt = t0 - last_t0;
            if (dt) { float f = BLOCK * 1e6f / dt; fs = (fs == 0.f) ? f : 0.9f * fs + 0.1f * f; }
        }
        last_t0 = t0;

        float m = 0.f;
        for (size_t i = 0; i < BLOCK; i++) m += x[i];
        m /= BLOCK;
        dc = (dc < 0.f) ? m : 0.98f * dc + 0.02f * m;   // the front end biases AIN0 to ~VDD/2; this is the number to check

        h->fs = fs; h->seq = seq++; h->t_ns = now_ns();
        memcpy(pkt + sizeof(*h), x, BLOCK * sizeof(int16_t));
        if (!atomic_get(&link_up) || zsock_sendto(sock, pkt, sizeof(pkt), 0, (struct sockaddr *)&dst, sizeof(dst)) < 0) {
            send_err++;                         // link down or pipeline unreachable; keep the sampler's timing intact
        }

        for (size_t i = 0; i < BLOCK; i++) {
            float ac = x[i] - dc;
            stat_sq += ac * ac;
            int pk = (int)fabsf(ac);
            if (pk > stat_peak) stat_peak = pk;
        }
        stat_n += BLOCK; stat_blocks++;
        int64_t now = k_uptime_get();
        if (now - stat_t >= 1000) {
            const float lsb_mv = (float)ADC_FULL_SCALE_MV / (1 << ADC_BITS);
            float rms_mv = sqrtf(stat_sq / MAX(stat_n, 1u)) * lsb_mv;
            printk("fs=%7.1fHz blocks/s=%3u dc=%.2fV rms=%6.1fmV peak=%6.1fmV mcu_drops=%u send_err=%u\n",
                   (double)fs, stat_blocks, (double)(dc * lsb_mv / 1000.f), (double)rms_mv,
                   (double)(stat_peak * lsb_mv), dropped_blocks, send_err);
            if (led_run.port) gpio_pin_toggle_dt(&led_run);
            stat_t = now; stat_blocks = 0; stat_n = 0; stat_sq = 0.f; stat_peak = 0;
        }
    }
    return 0;
}
