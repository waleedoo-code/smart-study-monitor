# attc_simple.py — ATTC + Dual-Core (DHT22, Isolated Measurement)
from machine import Pin, ADC
import dht
import time
import _thread

# sensors
sensor1 = dht.DHT22(Pin(16))
sensor2 = ADC(Pin(26))
time.sleep(2)

# shared data between cores
old_reading = {"temp": 0, "hum": 0, "light": 0, "time": 0}
data_ready = False

# software cache dictionary — this is the memory hierarchy layer
# stores cached values for comparison (ATTC policy)
cache_seq = {
    "temp":  {"value": 0, "last_update": 0},
    "hum":   {"value": 0, "last_update": 0},
    "light": {"value": 0, "last_update": 0},
}

# software cache using flat variables instead of dictionary
# this is the ILP improvement - no dictionary lookup needed
# flat variables are accessed directly in one instruction
cache_temp_val = 0      # last saved temperature value
cache_temp_ts  = 0      # last time temperature was saved

cache_hum_val  = 0      # last saved humidity value
cache_hum_ts   = 0      # last time humidity was saved

cache_light_val = 0     # last saved light value
cache_light_ts  = 0     # last time light was saved

# ATTC thresholds
T   = 0.3   # temperature threshold (degrees C)
H   = 1.0   # humidity threshold (%)
L   = 2.0   # light threshold (%)
TTL = 10    # time-to-live in seconds

# settings
SCRIPT_NAME = "ATTC + DUAL-CORE + ILP UNROLLED (DHT22 Real Hardware)"
DURATION = 600



# metrics — Core 0
read_count = 0
total_read_time = 0

# metrics — sequential ATTC (no ILP)
write_seq = 0
skip_seq  = 0
time_seq  = 0

# metrics — unrolled ATTC (with ILP)
write_unr = 0
skip_unr  = 0
time_unr  = 0


# sequential ATTC function — 3 separate function calls, dependent chain
# this is the baseline ATTC without ILP
def attc_seq(key, new_value, threshold, now):
    entry = cache_seq[key]
    changed = abs(new_value - entry["value"]) >= threshold
    expired = (now - entry["last_update"]) >= TTL
    if changed or expired:
        entry["value"] = new_value
        entry["last_update"] = now
        return True
    return False

def core1():

    # all the variables core1 needs to change
    global data_ready
    global write_seq, skip_seq, time_seq
    global write_unr, skip_unr, time_unr
    global cache_temp_val, cache_temp_ts
    global cache_hum_val,  cache_hum_ts
    global cache_light_val, cache_light_ts

    while True:
        if data_ready:
            now   = old_reading["time"]
            temp  = old_reading["temp"]
            hum   = old_reading["hum"]
            light = old_reading["light"]

            # ── VERSION A: sequential ATTC (3 function calls) ──
            # this is ATTC without ILP — dependent chain of calls
            s_start = time.ticks_us()
            w1 = attc_seq("temp",  temp,  T, now)
            w2 = attc_seq("hum",   hum,   H, now)
            w3 = attc_seq("light", light, L, now)
            s_end = time.ticks_us()
            time_seq += time.ticks_diff(s_end, s_start)
            if w1 or w2 or w3:
                write_seq += 1
            else:
                skip_seq += 1

            # ── VERSION B: unrolled ATTC (ILP — independent inline) ──
            # no function calls, no dictionary lookup, pipeline can overlap
            u_start = time.ticks_us()

            # check temperature — independent of hum and light
            t_diff    = abs(temp  - cache_temp_val)
            t_expired = (now - cache_temp_ts) >= TTL
            w4 = t_diff >= T or t_expired
            if w4:
                cache_temp_val = temp
                cache_temp_ts  = now

            # check humidity — independent of temp and light
            h_diff    = abs(hum   - cache_hum_val)
            h_expired = (now - cache_hum_ts) >= TTL
            w5 = h_diff >= H or h_expired
            if w5:
                cache_hum_val = hum
                cache_hum_ts  = now

            # check light — independent of temp and hum
            l_diff    = abs(light - cache_light_val)
            l_expired = (now - cache_light_ts) >= TTL
            w6 = l_diff >= L or l_expired
            if w6:
                cache_light_val = light
                cache_light_ts  = now

            u_end = time.ticks_us()
            time_unr += time.ticks_diff(u_end, u_start)
            if w4 or w5 or w6:
                write_unr += 1
            else:
                skip_unr += 1

            data_ready = False

        time.sleep(0.05)   

_thread.start_new_thread(core1, ())

start_time = time.time()

while time.time() - start_time < DURATION:
    now = time.time()
    if not data_ready:
        read_start = time.ticks_us()
        try:
            sensor1.measure()
            temp = sensor1.temperature()
            hum  = sensor1.humidity()
        except OSError as e:
            print("DHT read failed:", e)
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
            
            print("Read #{}: T={} H={} | seq={}us unr={}us | writes_seq={} writes_unr={}".format(
                read_count, temp, hum,
                round(time_seq / read_count, 1) if read_count > 0 else 0,
                round(time_unr / read_count, 1) if read_count > 0 else 0,
                write_seq, write_unr))

    time.sleep(2)
    
    
# ── CALCULATIONS ─────────────────────────────────────────
CLOCK_MHZ = 133

# sequential metrics
total_seq  = write_seq + skip_seq
avg_seq_us = time_seq / total_seq if total_seq > 0 else 0
avg_seq_cy = avg_seq_us * CLOCK_MHZ

# unrolled metrics
total_unr  = write_unr + skip_unr
avg_unr_us = time_unr / total_unr if total_unr > 0 else 0
avg_unr_cy = avg_unr_us * CLOCK_MHZ

# ILP speedup
ilp_speedup = avg_seq_us / avg_unr_us if avg_unr_us > 0 else 1
cycles_per_decision_saved = avg_seq_cy - avg_unr_cy
total_ilp_cycles_saved = cycles_per_decision_saved * total_unr

# read time
avg_read = total_read_time / read_count if read_count > 0 else 0

# Amdahl for sequential version
avg_decision_seq = avg_seq_us
avg_single_seq   = avg_read + avg_decision_seq
P_seq = avg_decision_seq / avg_single_seq if avg_single_seq > 0 else 0
speedup_seq_theoretical = 1 / ((1 - P_seq) + P_seq / 2) if P_seq > 0 else 1
speedup_seq_measured    = avg_single_seq / avg_read if avg_read > 0 else 1

# Amdahl for unrolled version
avg_decision_unr = avg_unr_us
avg_single_unr   = avg_read + avg_decision_unr
P_unr = avg_decision_unr / avg_single_unr if avg_single_unr > 0 else 0
speedup_unr_theoretical = 1 / ((1 - P_unr) + P_unr / 2) if P_unr > 0 else 1
speedup_unr_measured    = avg_single_unr / avg_read if avg_read > 0 else 1

# pipeline stall
baseline_write_stall = total_seq * int(55.38 * CLOCK_MHZ)
seq_write_stall      = write_seq * int(55.38 * CLOCK_MHZ)
unr_write_stall      = write_unr * int(55.38 * CLOCK_MHZ)
seq_cycles_saved     = baseline_write_stall - seq_write_stall
unr_cycles_saved     = baseline_write_stall - unr_write_stall
seq_pct = round(seq_cycles_saved / baseline_write_stall * 100, 2) if baseline_write_stall > 0 else 0
unr_pct = round(unr_cycles_saved / baseline_write_stall * 100, 2) if baseline_write_stall > 0 else 0

hit_seq  = round(skip_seq / total_seq * 100, 2) if total_seq > 0 else 0
miss_seq = round(write_seq / total_seq * 100, 2) if total_seq > 0 else 0
hit_unr  = round(skip_unr / total_unr * 100, 2) if total_unr > 0 else 0
miss_unr = round(write_unr / total_unr * 100, 2) if total_unr > 0 else 0

# ── NEW: execution time, cpu time, throughput, cpi ──────
DURATION_US = DURATION * 1_000_000   # total session in microseconds

# cpu time = time both cores were actively doing work
cpu_time_core0_us = total_read_time                    # Core 0 active time
cpu_time_core1_seq_us = time_seq                       # Core 1 sequential active time
cpu_time_core1_unr_us = time_unr                       # Core 1 unrolled active time

# total session time
total_time_us = DURATION_US

# cpu utilization per core
util_core0    = round(cpu_time_core0_us    / total_time_us * 100, 4)
util_core1_seq = round(cpu_time_core1_seq_us / total_time_us * 100, 4)
util_core1_unr = round(cpu_time_core1_unr_us / total_time_us * 100, 4)

# throughput — reads per second, useful writes per second
throughput_reads     = round(read_count   / DURATION, 4)
throughput_writes_seq = round(write_seq   / DURATION, 4)
throughput_writes_unr = round(write_unr   / DURATION, 4)

# execution time using IC x CPI x Clock Cycle Time (Equation 3)
CPI = 1
clock_cycle_time_ns = 1_000 / CLOCK_MHZ   # 7.52 ns

# read instruction count from measured cycles
avg_read_cycles = avg_read * CLOCK_MHZ
ic_reads = read_count * avg_read_cycles

# sequential version execution time
ic_seq_total  = ic_reads + (total_seq * avg_seq_cy)
exec_seq_ns   = ic_seq_total * CPI * clock_cycle_time_ns
exec_seq_us   = exec_seq_ns / 1000

# unrolled version execution time
ic_unr_total  = ic_reads + (total_unr * avg_unr_cy)
exec_unr_ns   = ic_unr_total * CPI * clock_cycle_time_ns
exec_unr_us   = exec_unr_ns / 1000

# enhancement factor s for ILP
s_ilp = round(ilp_speedup, 4)

# fraction enhanced P already calculated above as P_seq and P_unr
# overall speedup already calculated as speedup_seq_measured and speedup_unr_measured

# ── PRINT SUMMARY ────────────────────────────────────────
print("\n" + "="*60)
print("  SUMMARY — ATTC + DUAL-CORE: Sequential vs ILP Unrolled")
print("="*60)
print("Duration:                    {} seconds".format(DURATION))
print("Total reads:                 {}".format(read_count))
print("Avg read time (Core 0):      {} us".format(round(avg_read, 2)))
print("-"*60)
print("VERSION A — Sequential ATTC (no ILP, function calls):")
print("  Writes:                    {}".format(write_seq))
print("  Skipped:                   {}".format(skip_seq))
print("  Hit ratio:                 {}%".format(hit_seq))
print("  Avg decision time:         {} us = {:,} cycles".format(
    round(avg_seq_us, 2), int(avg_seq_cy)))
print("  P (parallelisable):        {}".format(round(P_seq, 6)))
print("  Theoretical speedup:       {}x".format(round(speedup_seq_theoretical, 6)))
print("  Measured speedup:          {}x".format(round(speedup_seq_measured, 6)))
print("  Write stall cycles saved:  {:,} cycles ({}%)".format(seq_cycles_saved, seq_pct))
print("-"*60)
print("VERSION B — Unrolled ATTC (ILP, inlined independent):")
print("  Writes:                    {}".format(write_unr))
print("  Skipped:                   {}".format(skip_unr))
print("  Hit ratio:                 {}%".format(hit_unr))
print("  Avg decision time:         {} us = {:,} cycles".format(
    round(avg_unr_us, 2), int(avg_unr_cy)))
print("  P (parallelisable):        {}".format(round(P_unr, 6)))
print("  Theoretical speedup:       {}x".format(round(speedup_unr_theoretical, 6)))
print("  Measured speedup:          {}x".format(round(speedup_unr_measured, 6)))
print("  Write stall cycles saved:  {:,} cycles ({}%)".format(unr_cycles_saved, unr_pct))
print("-"*60)
print("ILP SPEEDUP (A vs B):        {}x".format(round(ilp_speedup, 4)))
print("Cycles saved per decision:   {:,} cycles".format(int(cycles_per_decision_saved)))
print("Total ILP cycles saved:      {:,} cycles".format(int(total_ilp_cycles_saved)))
print("="*60)
print("-"*60)
print("--- EXECUTION TIME (IC x CPI x Clock Cycle Time) ---")
print("CPI:                         {} (Cortex-M0+ in-order)".format(CPI))
print("Clock cycle time:            {:.2f} ns (133 MHz)".format(clock_cycle_time_ns))
print("Exec time VERSION A (seq):   {:.2f} us".format(exec_seq_us))
print("Exec time VERSION B (unr):   {:.2f} us".format(exec_unr_us))
print("Exec time reduction (ILP):   {:.2f} us saved".format(exec_seq_us - exec_unr_us))
print("-"*60)
print("--- CPU TIME vs TOTAL TIME ---")
print("Core 0 active time:          {:,} us ({:.3f} s)".format(
    int(cpu_time_core0_us), cpu_time_core0_us/1_000_000))
print("Core 1 active (seq):         {:,} us ({:.3f} s)".format(
    int(cpu_time_core1_seq_us), cpu_time_core1_seq_us/1_000_000))
print("Core 1 active (unr):         {:,} us ({:.3f} s)".format(
    int(cpu_time_core1_unr_us), cpu_time_core1_unr_us/1_000_000))
print("Total session time:          {:,} us ({} s)".format(int(total_time_us), DURATION))
print("Core 0 utilization:          {}%".format(util_core0))
print("Core 1 utilization (seq):    {}%".format(util_core1_seq))
print("Core 1 utilization (unr):    {}%".format(util_core1_unr))
print("-"*60)
print("--- THROUGHPUT ---")
print("Throughput (reads/sec):      {} reads/s".format(throughput_reads))
print("Useful writes/sec (seq):     {} writes/s".format(throughput_writes_seq))
print("Useful writes/sec (unr):     {} writes/s".format(throughput_writes_unr))
print("-"*60)
print("--- BENCHMARK WORKLOAD ---")
print("Workload type:               Application benchmark (real DHT22 + LDR sensors)")
print("Environment:                 Indoor stable room, 600s fixed duration")
print("Enhancement factor s (ILP):  {}x (seq decision / unr decision)".format(s_ilp))
print("Fraction enhanced P (seq):   {}".format(round(P_seq, 6)))
print("Fraction enhanced P (unr):   {}".format(round(P_unr, 6)))
print("="*60)
