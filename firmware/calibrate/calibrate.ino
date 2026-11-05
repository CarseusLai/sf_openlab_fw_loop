// Prints the loudest mic sample and the largest acceleration seen in each 200 ms window,
// so the shake and clap thresholds of the base firmware come from measurements.
#include <Arduino_BMI270_BMM150.h>
#include <PDM.h>

static short pdm_buf[512];
static volatile int mic_peak = 0;
static volatile int mic_samples = 0;

static void on_pdm() {
  int n = PDM.available();
  PDM.read(pdm_buf, n);
  mic_samples += n / 2;
  for (int i = 0; i < n / 2; i++) {
    int v = abs(pdm_buf[i]);
    if (v > mic_peak) mic_peak = v;
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {
  }
  if (!IMU.begin()) {
    Serial.println("ERR,imu");
  }
  PDM.onReceive(on_pdm);
  if (!PDM.begin(1, 16000)) {
    Serial.println("ERR,pdm");
  }
  Serial.println("READY,calibrate");
}

void loop() {
  static unsigned long window_start = 0;
  static float max_g = 0;
  static float x, y, z;
  if (IMU.accelerationAvailable() && IMU.readAcceleration(x, y, z)) {
    float g = sqrtf(x * x + y * y + z * z);
    if (g > max_g) max_g = g;
  }
  if (millis() - window_start >= 200) {
    noInterrupts();
    int peak = mic_peak;
    int samples = mic_samples;
    mic_peak = 0;
    mic_samples = 0;
    interrupts();
    Serial.print("CAL,");
    Serial.print(millis());
    Serial.print(",");
    Serial.print(max_g, 2);
    Serial.print(",");
    Serial.print(peak);
    Serial.print(",");
    Serial.print(samples);
    Serial.print(",");
    Serial.print(x, 2);
    Serial.print(",");
    Serial.print(y, 2);
    Serial.print(",");
    Serial.println(z, 2);
    max_g = 0;
    window_start = millis();
  }
}
