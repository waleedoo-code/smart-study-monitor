#final project - attc_full_demo.py
from machine import Pin, ADC, PWM, I2C  
import ssd1306 #Library for oled screen
import time
import dht #Library for temperature sensor
import _thread 

# dht sensor
sensor1 = dht.DHT22(Pin(16))

#ldr sensor
sensor2 = ADC(Pin(26))

#oled screen
i2c = I2C(0, scl=Pin(1), sda=Pin(0))  #initialization of i2c
output1 = ssd1306.SSD1306_I2C(128, 64, i2c)

# button
input1 = Pin(17, Pin.IN, Pin.PULL_DOWN) #pull down to cancel the noise effect

#buzzer
output2 = PWM(Pin(18)) # PWM used to control buzzer sound intensity and generate tones
output2.duty_u16(0) #buzzer is selint so no starting noise can effect it

#storing the last read values from the senosrs
old_reading = {"temp": 0, "hum": 0, "light": 0, "time": 0}  # light 
data_ready = False   #this is the flag between both core0 and core1
write_count = 0      #the number of times writing happens 
skipped_count = 0    #the number of times writing has been skipped

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

#software cache
cache = {
    "temp":  {"value": 0, "last_update": 0},
    "hum":   {"value": 0, "last_update": 0},
    "light": {"value": 0, "last_update": 0},   
}

#software cache with ILP
cache_temp_val = 0;  cache_temp_ts = 0
cache_hum_val  = 0;  cache_hum_ts  = 0
cache_light_val = 0; cache_light_ts = 0


#threshold for ATTC Adaptive Threshold TTL Cache
T=0.3  #thershold for temperature 
H=1.0  #thershold for humidity 
L=2.0  #thershold for light percentage
TTL=10 #time-to-live in seconds, forces refresh even if value is stable

running = True # if false code stop

#attc as a function
def attc_seq(key, new_value, threshold, now):
    #getting variable needed from cache 
    entry=cache[key]
    
    # did we have meaningfull change
    changed =abs(new_value - entry["value"])>= threshold
    #did TTL expire
    expire=(now - entry["last_update"])>=TTL
    
    #equation |new_value − cached_value| ≥ threshold  OR  Δt ≥ TTL
    if changed or expire:
        entry["value"] = new_value
        entry["last_update"] = now
        return True  #writing happened 
    return False #writing did not happened

#function for core1
def core1():
    # all the variables core1 needs to change
    global data_ready
    global write_seq, skip_seq, time_seq
    global write_unr, skip_unr, time_unr
    global cache_temp_val, cache_temp_ts
    global cache_hum_val,  cache_hum_ts
    global cache_light_val, cache_light_ts

    while running:
        if data_ready:  #if data is ready from core0(not flagged)
            
            now   = old_reading["time"]
            temp  = old_reading["temp"]
            hum   = old_reading["hum"]
            light = old_reading["light"]
            
            # this is ATTC without ILP 
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
                
            # this is ATTC with ILP 
            u_start = time.ticks_us()

            # check temperature 
            t_diff    = abs(temp  - cache_temp_val)
            t_expired = (now - cache_temp_ts) >= TTL
            w4 = t_diff >= T or t_expired
            if w4:
                cache_temp_val = temp
                cache_temp_ts  = now

            # check humidity 
            h_diff    = abs(hum   - cache_hum_val)
            h_expired = (now - cache_hum_ts) >= TTL
            w5 = h_diff >= H or h_expired
            if w5:
                cache_hum_val = hum
                cache_hum_ts  = now

            # check light 
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


            #print("writes:", write_count, "skipped:", skipped_count)

            data_ready = False # tell Core 0 it's safe to fetch the next reading

        time.sleep(0.05) # small idle wait, avoids hammering the CPU pointlessly 

#lanching core1 
_thread.start_new_thread(core1, ())

#function to read light intensity
def sensor_ldr():
    try:
        raw = sensor2.read_u16()   #read sensor value betwen 0 to 65535
        light_level= 65535 - raw   # fix the inversion of the ldr
        light_percent= light_level / 65535 * 100  # percentage of ldr
        
        # figuring outt light status
        if light_percent > 80: 
            status= "Very Bright"
        elif light_percent > 50:
            status= "Bright"
        elif light_percent > 35:
            status= "Dim"
        else:
            status= "Dark"
        return light_percent, status #returning light percentage and the status
            
    except OSError as e:            # if it is Operating System Error print error
        print("Failed to read sensor:", e)

# function to read temperature and humidity
def sensor_dht():
    try:
        sensor1.measure()
        temp= sensor1.temperature()   #getting temperature 
        hum= sensor1.humidity()       #getting humidity
        # FIX: removed debug print("Temp:", temp, "C  Humidity:", hum, "%")
        return temp, hum   #return temperature and humidity
    except OSError as e:            # if it is Operating System Error print error
        print("Failed to read sensor:", e)

#function for calculating comfort score and status
def comfortscore(temp,hum,light_percent):
    score = 100.00

    # Temperature: ideal center 22C
    temp_center = 22
    if temp < temp_center:
        score -= (temp_center - temp) * 1
    else:
        score -= (temp - temp_center) * 1
    # extra penalty if far outside acceptable range
    if temp < 18:
        score -= (18 - temp) * 2
    elif temp > 26:
        score -= (temp - 26) * 2

    # Humidity: ideal center 50%
    hum_center = 50
    if hum < hum_center:
        score -= (hum_center - hum) * 0.5
    else:
        score -= (hum - hum_center) * 0.5
    if hum < 40:
        score -= (40 - hum) * 1
    elif hum > 60:
        score -= (hum - 60) * 1

    # Light: ideal center 70%
    light_center = 70
    if light_percent < light_center:
        score -= (light_center - light_percent) * 0.2
    else:
        score -= (light_percent - light_center) * 0.2
    if light_percent < 40:
        score -= (40 - light_percent) * 0.5
        
    #making sure the comfort score is between 0 to 100
    if score < 0:
        score = 0
    if score > 100:
        score = 100
    
    #getting comfort status
    if score >90:
        status="Excellent"
    elif score >80:
        status="good"
    else:
        status= "poor"
    
    return score,status

#function for displaying readings on the screen
def oled(temp ,humidity, status,comfyscore,comfystatus,state,second_left):
    output1.fill(0)  # clear screen
    output1.text("T:{}C H:{}%".format(temp,humidity), 0, 0)  #display temperture and humidity
    output1.text("Light:{}".format(status), 0, 10) # display light status
    output1.text("score:{:.2f} ".format(comfyscore), 0, 20) # display comfort score 
    output1.text("{}".format(comfystatus), 0, 30) # display comfort status 
    
    mins = seconds_left // 60    #minutes 
    secs = seconds_left % 60      # sec using modules
    # display time and messages passed on status 
    if state == "idle":
        timer_text = "Press to start"
    elif state == "running":
        timer_text = "Focus {:02d}:{:02d}".format(mins, secs)
    elif state == "paused":
        timer_text = "PAUSED {:02d}:{:02d}".format(mins, secs)
    elif state == "break":
        timer_text = "Break {:02d}:{:02d}".format(mins, secs)
    elif state == "smile_break":
        timer_text = ":) Break time!"
    elif state == "smile_back":
        timer_text = ":) Back to study!"

    output1.text(timer_text, 0, 40)
    output1.show()   #update the screen

# function for buzzer 
def buzzer(duration=2, freq=850):
    output2.freq(freq)        # frequency dicide on the pitch of the sound
    output2.duty_u16(60000)   #intesity of the sound between 0 to 65535
    time.sleep(duration) #duration of the buzzer 
    output2.duty_u16(0)  #mute the buzzer again

state = "idle"  #intial contion before any button pressed
last_button = 0 
seconds_left = 0
last_tick = time.time() #getting time from pico timer
smile_until = 0

focus=10  #1500 # 25min study
bk=5 #300  # 5min break can not use break since it is a function so use bk instead

def update_timer():
    global state, seconds_left, last_button, last_tick,smile_until
    
    #button check
    current_button = input1.value()
    
    if current_button == 1 and last_button == 0:
        if state == "idle":
            state = "running"
            seconds_left = focus  
        elif state == "running":
            state = "paused"
        elif state == "paused":
            state = "running"
        print("State is now:", state)
        time.sleep(0.05)   #debounce delay to prevent multiple detections from a single button press
    
    last_button = current_button

    #timer check
    now = time.time()   #get the current time from pico 
    if now != last_tick:
        last_tick = now    #prevent counting down in the same second
        
        # decrease countdown during focus or break session
        if state == "running" or state == "break":
            seconds_left -= 1
            
            # timer finished
            if seconds_left <= 0:
                
                # focus session completed
                if state == "running":
                    buzzer()    #buzzer 
                    state = "smile_break"
                    smile_until = now + 5   
                    
                # break session completed
                elif state == "break":
                    buzzer() #buzzer
                    state= "smile_back"
                    smile_until =now + 5
                    
         # after smile message, start break timer
        elif state == "smile_break" and now >= smile_until:
            state= "break"
            seconds_left = bk
            
         # after smile message, return to idle state
        elif state == "smile_back" and now >= smile_until:
            state= "idle"
            seconds_left = 0
            
    # return updated timer state and remaining time
    return state, seconds_left

#to have arefrence for checking 
last_sensor_read = time.time()

#definig values before the loop since they would not be defined until 2 sec
temp =0 
hum= 0
light_percent= 0
status= ""
comfy_score= 0
comfy_status =""

test_start = time.time()
DURATION = 60  # 10 minutes 
summary_printed = False
SCRIPT_NAME = "ATTC + DUAL-CORE FULL DEMO"
avg_read = 0
CLOCK_MHZ = 133


while True:
    state, seconds_left = update_timer()
    
    now = time.time()
    # read sensors every 2 seconds so sensor reading does not effect button sensitivity 
    if now - last_sensor_read >= 2:
        last_sensor_read = now
        
        #read timing for Amdahl measurement
        read_start = time.ticks_us()
        # Returns both light percentage and status since the same reading is processed in two stages (value + classification).
        light_percent, status = sensor_ldr()
        temp, hum = sensor_dht()
        read_end = time.ticks_us()
        
        if temp is not None:
            total_read_time += time.ticks_diff(read_end, read_start)
            read_count += 1
        
        comfy_score ,comfy_status=comfortscore(temp,hum,light_percent)
        
        # hand off this reading to Core 1 for ATTC evaluation (NEW)
        old_reading["temp"] = temp
        old_reading["hum"] = hum
        old_reading["light"] = light_percent  
        old_reading["time"] = now
        data_ready = True
        
        # live feedback every reading
        print("Read #{}: T={} H={} | seq={}us unr={}us | writes_seq={} writes_unr={}".format(
                read_count, temp, hum,
                round(time_seq / read_count, 1) if read_count > 0 else 0,
                round(time_unr / read_count, 1) if read_count > 0 else 0,
                write_seq, write_unr))
        
        
        
    oled(temp, hum, status,comfy_score ,comfy_status,state, seconds_left)
    
    
    time.sleep(0.05) # enough time for dht to response
    
    #summary 
    if not summary_printed and time.time() - test_start >= DURATION:  
        summary_printed = True

        # sequential metrics
        total_seq  = write_seq + skip_seq
        avg_seq_us = time_seq / total_seq if total_seq > 0 else 0
        avg_seq_cy = avg_seq_us * CLOCK_MHZ

        # unrolled metrics
        total_unr  = write_unr + skip_unr
        avg_unr_us = time_unr / total_unr if total_unr > 0 else 0
        avg_unr_cy = avg_unr_us * CLOCK_MHZ

        # ILP speedup
        ilp_speedup               = avg_seq_us / avg_unr_us if avg_unr_us > 0 else 1
        cycles_per_decision_saved = avg_seq_cy - avg_unr_cy
        total_ilp_cycles_saved    = cycles_per_decision_saved * total_unr

        # read time
        avg_read = total_read_time / read_count if read_count > 0 else 0

        # Amdahl for sequential version
        avg_decision_seq        = avg_seq_us
        avg_single_seq          = avg_read + avg_decision_seq
        P_seq                   = avg_decision_seq / avg_single_seq if avg_single_seq > 0 else 0
        speedup_seq_theoretical = 1 / ((1 - P_seq) + P_seq / 2) if P_seq > 0 else 1
        speedup_seq_measured    = avg_single_seq / avg_read if avg_read > 0 else 1

        # Amdahl for unrolled version
        avg_decision_unr        = avg_unr_us
        avg_single_unr          = avg_read + avg_decision_unr
        P_unr                   = avg_decision_unr / avg_single_unr if avg_single_unr > 0 else 0
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

        # hit/miss ratios
        hit_seq  = round(skip_seq / total_seq * 100, 2) if total_seq > 0 else 0
        miss_seq = round(write_seq / total_seq * 100, 2) if total_seq > 0 else 0
        hit_unr  = round(skip_unr / total_unr * 100, 2) if total_unr > 0 else 0
        miss_unr = round(write_unr / total_unr * 100, 2) if total_unr > 0 else 0

        # ── execution time, cpu time, throughput, cpi ───
        DURATION_US = DURATION * 1_000_000

        # cpu time = time each core was actively doing work
        cpu_time_core0_us     = total_read_time
        cpu_time_core1_seq_us = time_seq
        cpu_time_core1_unr_us = time_unr
        total_time_us         = DURATION_US

        # cpu utilization per core
        util_core0     = round(cpu_time_core0_us     / total_time_us * 100, 4)
        util_core1_seq = round(cpu_time_core1_seq_us / total_time_us * 100, 4)
        util_core1_unr = round(cpu_time_core1_unr_us / total_time_us * 100, 4)

        # throughput
        throughput_reads      = round(read_count / DURATION, 4)
        throughput_writes_seq = round(write_seq  / DURATION, 4)
        throughput_writes_unr = round(write_unr  / DURATION, 4)

        # execution time using IC x CPI x Clock Cycle Time (Equation 3)
        CPI                 = 1
        clock_cycle_time_ns = 1_000 / CLOCK_MHZ
        avg_read_cycles     = avg_read * CLOCK_MHZ

        ic_seq_total = (read_count * avg_read_cycles) + (total_seq * avg_seq_cy)
        exec_seq_us  = (ic_seq_total * CPI * clock_cycle_time_ns) / 1000

        ic_unr_total = (read_count * avg_read_cycles) + (total_unr * avg_unr_cy)
        exec_unr_us  = (ic_unr_total * CPI * clock_cycle_time_ns) / 1000

        # enhancement factor s for ILP
        s_ilp = round(ilp_speedup, 4)
        # AMAT calculation (Equation 2: Hit Time + Miss Rate x Miss Penalty)
        miss_penalty_us = 55.38  # measured avg write time from baseline

        # baseline AMAT
        amat_baseline = 0 + (1.0 * miss_penalty_us)  # hit time=0, miss rate=100%

        # sequential ATTC AMAT
        amat_seq = avg_seq_us + ((miss_seq / 100) * miss_penalty_us)

        # ILP unrolled ATTC AMAT
        amat_unr = avg_unr_us + ((miss_unr / 100) * miss_penalty_us)

        # total write cost
        total_write_cost_baseline = total_seq * miss_penalty_us
        total_write_cost_seq      = write_seq * miss_penalty_us
        total_write_cost_unr      = write_unr * miss_penalty_us
        write_time_saved_seq      = total_write_cost_baseline - total_write_cost_seq
        write_time_saved_unr      = total_write_cost_baseline - total_write_cost_unr

        # ── PRINT SUMMARY ────────────────────────────────
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
            int(cpu_time_core0_us), cpu_time_core0_us / 1_000_000))
        print("Core 1 active (seq):         {:,} us ({:.3f} s)".format(
            int(cpu_time_core1_seq_us), cpu_time_core1_seq_us / 1_000_000))
        print("Core 1 active (unr):         {:,} us ({:.3f} s)".format(
            int(cpu_time_core1_unr_us), cpu_time_core1_unr_us / 1_000_000))
        print("Total session time:          {:,} us ({} s)".format(
            int(total_time_us), DURATION))
        print("Core 0 utilization:          {}%".format(util_core0))
        print("Core 1 utilization (seq):    {}%".format(util_core1_seq))
        print("Core 1 utilization (unr):    {}%".format(util_core1_unr))
        print("-"*60)
        print("--- THROUGHPUT ---")
        print("Throughput (reads/sec):      {} reads/s".format(throughput_reads))
        print("Useful writes/sec (seq):     {} writes/s".format(throughput_writes_seq))
        print("Useful writes/sec (unr):     {} writes/s".format(throughput_writes_unr))
        print("-"*60)
        print("-"*60)
        print("--- AMAT ANALYSIS (Equation 2) ---")
        print("Miss penalty (write cost):   {} us".format(miss_penalty_us))
        print("Baseline AMAT:               {} us (hit time=0, miss rate=100%)".format(round(amat_baseline, 2)))
        print("Sequential ATTC AMAT:        {} us".format(round(amat_seq, 2)))
        print("ILP Unrolled ATTC AMAT:      {} us".format(round(amat_unr, 2)))
        print("Total write cost (baseline): {} us".format(round(total_write_cost_baseline, 2)))
        print("Total write cost (seq):      {} us".format(round(total_write_cost_seq, 2)))
        print("Total write cost (unr):      {} us".format(round(total_write_cost_unr, 2)))
        print("Write time saved (seq):      {} us".format(round(write_time_saved_seq, 2)))
        print("Write time saved (unr):      {} us".format(round(write_time_saved_unr, 2)))
        print("--- BENCHMARK WORKLOAD ---")
        print("Workload type:               Application benchmark (real DHT22 + LDR)")
        print("Environment:                 Indoor stable room, 600s fixed duration")
        print("Enhancement factor s (ILP):  {}x (seq / unr decision time)".format(s_ilp))
        print("Fraction enhanced P (seq):   {}".format(round(P_seq, 6)))
        print("Fraction enhanced P (unr):   {}".format(round(P_unr, 6)))
        print("="*60)

        buzzer()
        running = False
        break
