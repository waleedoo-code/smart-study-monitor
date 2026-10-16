# baseline.py — BASELINE (Unconditional Write, Single-Core)
from machine import Pin, ADC
import dht
import time

# sensors
sensor1 = dht.DHT22(Pin(16))
sensor2 = ADC(Pin(26))
time.sleep(2)

# software cache — unconditional write every reading
cache = {"temp": 0, "hum": 0, "light": 0}

def baseline_write(key, value):
    cache[key] = value

# settings
SCRIPT_NAME = "BASELINE (Unconditional Write, Single-Core)"
DURATION = 60

# metrics
write_count = 0
total_write_time = 0
total_read_time = 0

start_time = time.time()

while time.time() - start_time < DURATION:
    read_start = time.ticks_us()
    try:
        sensor1.measure()
        temp = sensor1.temperature()
        hum = sensor1.humidity()
    except OSError as e:
        print("DHT read failed:", e)
        temp, hum = None, None

    raw = sensor2.read_u16()
    light_level = 65535 - raw
    light = light_level / 65535 * 100  # convert to percentage
    read_end = time.ticks_us()

    read_duration = time.ticks_diff(read_end, read_start)
    total_read_time += read_duration

    if temp is not None:
        write_start = time.ticks_us()
        baseline_write("temp", temp)
        baseline_write("hum", hum)
        baseline_write("light", light)
        write_end = time.ticks_us()

        write_duration = time.ticks_diff(write_end, write_start)
        total_write_time += write_duration
        write_count += 1

        print("Write #{}: T={} H={} L={:.1f} | write_time={}us".format(
            write_count, temp, hum, light, write_duration))

    time.sleep(2)

# ── BASELINE has no skips, no ATTC, no dual-core ────────
skipped_count = 0
total_decision_time = 0
read_count = write_count  # every successful read = one write in baseline

# ── PIPELINE STALL ANALYSIS ──────────────────────────────
CLOCK_MHZ = 133
avg_write_us = total_write_time / write_count if write_count > 0 else 57.8
avg_write_cycles = int(avg_write_us * CLOCK_MHZ)
avg_read_us = total_read_time / read_count if read_count > 0 else 0
avg_read_cycles = int(avg_read_us * CLOCK_MHZ)

# baseline: every read is a write, nothing is saved
total_write_stall_cycles = write_count * avg_write_cycles
total_read_stall_cycles = read_count * avg_read_cycles

# ── AMDAHL — baseline is single core so P=0, speedup=1 ──
total = write_count  # no skips in baseline
avg_read = total_read_time / read_count if read_count > 0 else 0
avg_decision = 0     # no decision logic in baseline
avg_single_core = avg_read
avg_dual_core = avg_read
P = 0
speedup_theoretical = 1
speedup_measured = 1
hit_ratio = 0        # baseline never hits, always writes
miss_ratio = 100     # baseline always misses

# ──  execution time, cpu time, throughput, cpi ──────
DURATION_US = DURATION * 1_000_000   # total session in microseconds

# cpu time = time processor was actually doing work (read + write)
cpu_time_us = total_read_time + total_write_time

# total session time in microseconds
total_time_us = DURATION_US

# cpu utilization = how much of the session the cpu was active
cpu_utilization = round(cpu_time_us / total_time_us * 100, 4)

# throughput = reads per second and writes per second
throughput_reads  = round(read_count  / DURATION, 4)
throughput_writes = round(write_count / DURATION, 4)

# execution time using IC x CPI x Clock Cycle Time (Equation 3)
# each write = avg_write_cycles instructions at CPI=1
# each read  = avg_read_cycles instructions at CPI=1
CPI = 1   # cortex-m0+ simple in-order pipeline
clock_cycle_time_ns = 1_000 / CLOCK_MHZ   # 7.52 ns

ic_reads  = read_count  * avg_read_cycles   # total read instructions
ic_writes = write_count * avg_write_cycles  # total write instructions
ic_total  = ic_reads + ic_writes            # total instruction count

exec_time_ns = ic_total * CPI * clock_cycle_time_ns   # in nanoseconds
exec_time_us = exec_time_ns / 1000                    # in microseconds

# enhancement factor s — baseline has no enhancement so s=1
s_enhancement = 1

# ── PRINT SUMMARY ────────────────────────────────────────
print("\n" + "="*60)
print("  SUMMARY — {}".format(SCRIPT_NAME))
print("="*60)
print("Duration:                    {} seconds".format(DURATION))
print("Total reads:                 {}".format(read_count))
print("Writes (cache updated):      {}".format(write_count))
print("Skipped (filtered):          {}".format(skipped_count))
print("Hit ratio:                   {}%".format(hit_ratio))
print("Miss ratio:                  {}%".format(miss_ratio))
print("-"*60)
print("Avg read time:               {} us".format(round(avg_read, 2)))
print("Avg write time:              {} us".format(round(avg_write_us, 2)))
print("Avg decision time (Core 1):  N/A (single-core)")
print("Single-core cycle:           {} us".format(round(avg_read + avg_write_us, 2)))
print("-"*60)
print("P (parallelisable fraction): {} (single-core, no TLP)".format(P))
print("Theoretical speedup:         {}".format(speedup_theoretical))
print("Measured speedup:            {}".format(speedup_measured))
print("-"*60)
print("Avg write stall per op:      {:.1f} us = {:,} cycles".format(
    avg_write_us, avg_write_cycles))
print("Total write stall cycles:    {:,} cycles".format(total_write_stall_cycles))
print("Total read stall cycles:     {:,} cycles".format(total_read_stall_cycles))
print("Pipeline cycles saved:       0 cycles (0% — no filtering)")
print("-"*60)
# new measurements from slide requirements
print("--- EXECUTION TIME (IC x CPI x Clock Cycle Time) ---")
print("Instruction count (reads):   {:,} instructions".format(ic_reads))
print("Instruction count (writes):  {:,} instructions".format(ic_writes))
print("Total instruction count:     {:,} instructions".format(ic_total))
print("CPI:                         {} (Cortex-M0+ in-order)".format(CPI))
print("Clock cycle time:            {:.2f} ns (133 MHz)".format(clock_cycle_time_ns))
print("Execution time (IC*CPI*T):   {:.2f} us".format(exec_time_us))
print("-"*60)
print("--- CPU TIME vs TOTAL TIME ---")
print("CPU active time:             {:,} us ({} s)".format(
    int(cpu_time_us), round(cpu_time_us/1_000_000, 3)))
print("Total session time:          {:,} us ({} s)".format(
    int(total_time_us), DURATION))
print("CPU utilization:             {}%".format(cpu_utilization))
print("-"*60)
print("--- THROUGHPUT ---")
print("Throughput (reads/sec):      {} reads/s".format(throughput_reads))
print("Throughput (writes/sec):     {} writes/s".format(throughput_writes))
print("Useful writes (all writes redundant in baseline)")
print("-"*60)
print("--- BENCHMARK WORKLOAD ---")
print("Workload type:               Application benchmark (real DHT22 + LDR)")
print("Environment:                 Indoor stable room, 600s fixed duration")
print("Enhancement factor (s):      {} (no enhancement applied)".format(s_enhancement))
print("="*60)
