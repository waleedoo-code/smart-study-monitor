% load the data
data = readtable('data.csv');

% convert the timestamp to relative time in minutes
% (the raw timestamp is seconds since Pico booted)
t = (data.time - data.time(1)) / 60;  % minutes from start

% --- PLOT 1: all three sensors ---
figure('Name', 'Sensor Data — 8 Hours');

subplot(3,1,1);
plot(t, data.temp, 'r');
title('Temperature');
xlabel('Time (minutes)');
ylabel('°C');
grid on;

subplot(3,1,2);
plot(t, data.humidity, 'b');
title('Humidity');
xlabel('Time (minutes)');
ylabel('%');
grid on;

subplot(3,1,3);
plot(t, data.light, 'Color', [0.8 0.6 0]);
title('Light Level');
xlabel('Time (minutes)');
ylabel('%');
grid on;

% --- PLOT 2: humidity and light together to spot correlation ---
figure('Name', 'Humidity vs Light');
yyaxis left;
plot(t, data.humidity, 'b');
ylabel('Humidity (%)');

yyaxis right;
plot(t, data.light, 'Color', [1 0.6 0]);
ylabel('Light (%)');

title('Humidity and Light over time');
xlabel('Time (minutes)');
grid on;

% --- basic stats ---
fprintf('=== SUMMARY ===\n');
fprintf('Duration: %.1f minutes\n', t(end));
fprintf('Readings: %d\n', height(data));
fprintf('\nTemperature: min=%.1f  max=%.1f  mean=%.2f\n', ...
    min(data.temp), max(data.temp), mean(data.temp));
fprintf('Humidity:    min=%.1f  max=%.1f  mean=%.2f\n', ...
    min(data.humidity), max(data.humidity), mean(data.humidity));
fprintf('Light:       min=%.1f  max=%.1f  mean=%.2f\n', ...
    min(data.light), max(data.light), mean(data.light));
