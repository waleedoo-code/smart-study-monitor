# attc_ilp.py — ILP demonstration via loop unrolling of ATTC decision
# Compares sequential ATTC calls vs unrolled inline ATTC
# Purpose: demonstrate ILP benefit on Cortex-M0+ 2-stage pipeline
from machine import Pin, ADC
import dht
import time
import _thread

sensor1 = dht.DHT22(Pin(16))
sensor2 = ADC(Pin(26))
time.sleep(2)

# thresholds
T, H, L, TTL = 0.3, 1.0, 2.0, 10

# ── VERSION A: Sequential ATTC (function calls, dependent) ──
cache_seq = {
    "temp":  {"value": 0, "last_update": 0},
    "hum":   {"value": 0, "last_update": 0},
    "light": {"value": 0, "last_update": 0},
}

def attc_seq(key, new_value, threshold, now):
    entry = cache_seq[key]
    changed = abs(new_value - entry["value"]) >= threshold
    expired = (now - entry["last_update"]) >= TTL
    if changed or expired:
        entry["value"] = new_value
        entry["last_update"] = now
        return True
    return False

# ── VERSION B: Unrolled ATTC (inlined, independent comparisons) ──
# Cache values stored as flat variables — no dictionary lookup overhead
cache_t_val = 0; cache_t_ts = 0
cache_h_val = 0; cache_h_ts = 0
cache_l_val = 0; cache_l_ts = 0

def attc_unrolled(temp, hum, light, now):
    global cache_t_val, cache_t_ts
    global cache_h_val, cache_h_ts
    global cache_l_val, cache_l_ts

    # all three threshold checks computed independently — no function call overhead
    # processor can overlap these in the pipeline since they share no dependencies
    t_changed = (temp  - cache_t_val) if temp  >= cache_t_val else (cache_t_val - temp)
    h_changed = (hum   - cache_h_val) if hum   >= cache_h_val else (cache_h_val - hum)
    l_changed = (light - cache_l_val) if light >= cache_l_val else (cache_l_val - light)

    t_expired = (now - cache_t_ts) >= TTL
    h_expired = (now - cache_h_ts) >= TTL
    l_expired = (now - cache_l_ts) >= TTL

    t_write = t_changed >= T or t_expired
    h_write = h_changed >= H or h_expired
    l_write = l_changed >= L or l_expired

    if t_write:
        cache_t_val = temp;  cache_t_ts = now
    if h_write:
        cache_h_val = hum;   cache_h_ts = now
    if l_write:
        cache_l_val = light; cache_l_ts = now

    return t_write or h_write or l_write

# ── shared state ──
old_reading = {"temp": 0, "hum": 0, "light": 0, "time": 0}
data_ready = False
running = True

# ── metrics ──
read_count = 0
total_read_time = 0

write_seq = 0; skip_seq = 0; time_seq = 0
write_unr = 0; skip_unr = 0; time_unr = 0

SCRIPT_NAME = "ILP DEMONSTRATION — Sequential vs Unrolled ATTC"
DURATION = 600

def core1_job():
    global data_ready
    global write_seq, skip_seq, time_seq
    global write_unr, skip_unr, time_unr

    while running:
        if data_ready:
            now  = old_reading["time"]
            temp = old_reading["temp"]
            hum  = old_reading["hum"]
            light= old_reading["light"]

            # ── measure sequential version ──
            s_start = time.ticks_us()
            w1 = attc_seq("temp",  temp,  T, now)
            w2 = attc_seq("hum",   hum,   H, now)
            w3 = attc_seq("light", light, L, now)
            s_end = time.ticks_us()
            time_seq += time.ticks_diff(s_end, s_start)
            if w1 or w2 or w3: write_seq += 1
            else: skip_seq += 1

            # ── measure unrolled version ──
            u_start = time.ticks_us()
            w4 = attc_unrolled(temp, hum, light, now)
            u_end = time.ticks_us()
            time_unr += time.ticks_diff(u_end, u_start)
            if w4: write_unr += 1
            else:  skip_unr += 1

            data_ready = False

        time.sleep(0.05)

_thread.start_new_thread(core1_job, ())

start_time = time.time()

while time.time() - start_time < DURATION:
    now = time.time()
    if not data_ready:
        read_start = time.ticks_us()
        try:
            sensor1.measure()
            temp = sensor1.temperature()
            hum  = sensor1.humidity()
        except OSError:
            temp, hum = None, None
        raw   = sensor2.read_u16()
        light = (65535 - raw) / 65535 * 100
        read_end = time.ticks_us()
        total_read_time += time.ticks_diff(read_end, read_start)

        if temp is not None:
            read_count += 1
            old_reading["temp"]  = temp
            old_reading["hum"]   = hum
            old_reading["light"] = light
            old_reading["time"]  = now
            data_ready = True

            print("Read #{} | seq_time={}us unr_time={}us".format(
                read_count,
                round(time_seq/read_count, 2) if read_count > 0 else 0,
                round(time_unr/read_count, 2) if read_count > 0 else 0))

    time.sleep(2)

running = False
time.sleep(0.3)

# ── SUMMARY ──────────────────────────────────────────────
CLOCK_MHZ = 133
total_seq = write_seq + skip_seq
total_unr = write_unr + skip_unr

avg_seq = time_seq / total_seq if total_seq > 0 else 0
avg_unr = time_unr / total_unr if total_unr > 0 else 0
ilp_speedup = avg_seq / avg_unr if avg_unr > 0 else 1

avg_seq_cyc = round(avg_seq * CLOCK_MHZ, 1)
avg_unr_cyc = round(avg_unr * CLOCK_MHZ, 1)
cycles_saved_per_decision = avg_seq_cyc - avg_unr_cyc
total_cycles_saved = round(cycles_saved_per_decision * total_unr, 0)

print("\n" + "="*60)
print("  SUMMARY — {}".format(SCRIPT_NAME))
print("="*60)
print("Duration:                      {} seconds".format(DURATION))
print("Total reads:                   {}".format(read_count))
print("-"*60)
print("SEQUENTIAL ATTC (3 function calls):")
print("  Avg decision time:           {:.2f} us = {:,} cycles".format(
    avg_seq, int(avg_seq_cyc)))
print("  Writes: {}  Skipped: {}".format(write_seq, skip_seq))
print("-"*60)
print("UNROLLED ATTC (inlined, independent):")
print("  Avg decision time:           {:.2f} us = {:,} cycles".format(
    avg_unr, int(avg_unr_cyc)))
print("  Writes: {}  Skipped: {}".format(write_unr, skip_unr))
print("-"*60)
print("ILP SPEEDUP (sequential / unrolled):  {:.4f}x".format(ilp_speedup))
print("Cycles saved per decision:            {:,} cycles".format(
    int(cycles_saved_per_decision)))
print("Total cycles saved (session):         {:,} cycles".format(
    int(total_cycles_saved)))
print("="*60)
