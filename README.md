# Smart Study Environment Comfort Monitor

A Raspberry Pi Pico H project that monitors temperature, humidity and light, displays environmental readings and a comfort score on an OLED, and provides a focus/break timer with button control and buzzer alerts.

Developed for COM213 Computer Architecture and extended through experiments with software caching, code optimisation, dual-core processing and MATLAB analysis.

## Main Features

- DHT22 temperature and humidity monitoring
- LDR-based relative light measurement
- OLED display showing readings, light classification and comfort score
- Button-controlled focus/break timer
- PWM buzzer notifications
- Adaptive Threshold-TTL Cache (ATTC)
- Sequential and unrolled cache-decision comparisons
- Separate baseline and reduced-interface benchmarks
- MATLAB analysis of recorded sensor data

## Repository Contents

| Folder | Contents |
|---|---|
| `firmware/` | Integrated demonstration with sensors, OLED, timer, button, buzzer and ATTC experiments |
| `benchmarks/` | Separate scripts for baseline measurements and focused performance experiments |
| `analysis/` | MATLAB sensor-data plotting and summary statistics |
| `data/` | CSV sensor readings used for analysis |

## 1. Integrated Firmware

### `firmware/attc_full_demo.py`

Combines the hardware interface and cache experiments in one demonstration.

Core 0 reads the sensors, updates the display and handles the timer. Core 1 evaluates the shared sensor readings using two ATTC implementations:

- **Sequential:** a dictionary-based implementation using separate function calls.
- **Unrolled:** inline checks using separate variables for each sensor.

The program records decision times and cache-update counts for comparison.

### Comfort Score

The score is calculated from temperature, humidity and relative light readings. Penalties are applied as conditions move away from the chosen reference values.

This is a project-defined indicator for comparing study conditions, rather than a validated comfort standard.

### Timer

The button starts, pauses and resumes a focus session. The OLED displays the timer state, and the buzzer signals session transitions.

The uploaded version uses short demonstration settings:

| Setting | Current value |
|---|---|
| Focus period | 10 seconds |
| Break period | 5 seconds |
| Demonstration duration | 60 seconds |

The program prints its summary and exits after the demonstration duration. These settings should be adjusted together for longer sessions.

## 2. Benchmark Scripts

Run each benchmark separately.

### `benchmarks/baseline.py`

Single-core reference implementation that updates the software cache after every successful sensor-reading cycle.

It measures sensor-read and cache-write elapsed times, providing a comparison point for the ATTC versions.

The uploaded baseline uses a 60-second session.

### `benchmarks/attc_simple.py`

Runs the sensor and ATTC experiments without the OLED, timer, button handling or buzzer interface.

It compares the sequential and unrolled decision routines with less application-interface activity. The uploaded version uses a 600-second session.

### `benchmarks/ldr_benchmark.py`

Separate LDR-focused benchmark for examining processing behaviour without including DHT22 temperature and humidity acquisition.

Its results should be interpreted as a separate workload, rather than as the performance of the complete monitor.

## 3. How ATTC Works

ATTC stores accepted sensor values and their update timestamps.

A cached value is updated when either:

1. The new reading differs from the cached value by at least its threshold.
2. The time-to-live expires.

| Parameter | Value |
|---|---|
| Temperature threshold | 0.3 °C |
| Humidity threshold | 1 percentage point |
| Relative light threshold | 2 percentage points |
| Time-to-live | 10 seconds |

Stable readings can therefore skip cache updates, while the TTL ensures periodic refreshes.

ATTC operates on the software cache. Sensor acquisition still occurs at the configured reading interval.

## 4. MATLAB Analysis

### `analysis/plot_sensor_data.m`

Loads the recorded sensor data and produces:

- Separate temperature, humidity and light plots
- A combined humidity/light plot for visual comparison
- Recording duration and number of readings
- Minimum, maximum and mean values for each sensor

Light values are relative percentages derived from the ADC reading, not calibrated lux measurements.

### `data/data.csv`

The analysis expects these column names:

```text
time,temp,humidity,light
```

Time is recorded in seconds and converted into minutes relative to the first reading.

With the CSV stored in `data/`, use this at the start of the MATLAB script:

```matlab
script_folder = fileparts(mfilename('fullpath'));
data = readtable(fullfile(script_folder, '..', 'data', 'data.csv'));
```

The uploaded firmware prints diagnostic output but does not create this CSV automatically. The recorded dataset is supplied separately.

## Hardware and Connections

| Component | Pico connection |
|---|---|
| DHT22 data | GP16 |
| LDR analogue signal | GP26 / ADC0 |
| OLED SDA | GP0 |
| OLED SCL | GP1 |
| Button | GP17, configured with an internal pull-down |
| Buzzer signal | GP18, using PWM |

The OLED interface is configured for a 128 × 64 SSD1306 display.

## Running the Project

### MicroPython

1. Use a Raspberry Pi Pico H running compatible MicroPython firmware.
2. Connect the hardware according to the table above.
3. Install the required `ssd1306.py` OLED driver on the Pico.
4. Copy the selected project script onto the Pico.
5. Open and run it using Thonny or another MicroPython tool.
6. View the OLED interface and serial output.

Run one application or benchmark script at a time. Reset the Pico between benchmark runs to clear any previous background thread.

### MATLAB

1. Download the repository while preserving its folders.
2. Open `analysis/plot_sensor_data.m`.
3. Check that `data/data.csv` contains the recorded readings.
4. Run the script to generate plots and summary statistics.

## Project Results

Earlier ten-minute project benchmarks reported:

| Measurement | Result |
|---|---|
| Baseline cache-update events | 264 |
| ATTC cache-update events | 54 |
| Reduction in cache-update events | Approximately 80% |
| Cache-decision routine speedup from unrolling | Approximately 2.03× |

These figures describe specific earlier benchmark runs. They are not results automatically reproduced by the current 60-second demonstration settings.

The 2.03× figure applies to the cache-decision routine, rather than to the complete monitoring application.

The project also included an extended sensor recording of approximately eight hours, analysed in MATLAB to visualise environmental changes over time.

## Interpreting the Measurements

- Cache-update counts describe software-cache activity.
- Unrolled MicroPython timing comparisons do not directly measure processor instruction-level parallelism.
- Some printed cycle counts, instruction counts, utilisation figures and speedup calculations use assumptions or simplified models.
- Those calculated fields should be treated as educational estimates, rather than direct processor-counter measurements.
- Use matching durations, workloads and hardware conditions when comparing new benchmark runs.
- Sensor timing, display updates, serial printing and thread scheduling can affect results.

## Skills Demonstrated

- Embedded systems and MicroPython
- Sensor integration and analogue data acquisition
- I²C OLED interfacing
- PWM and button-input handling
- Software caching and threshold logic
- Dual-core programming experiments
- Performance measurement and interpretation
- MATLAB data analysis and visualisation
