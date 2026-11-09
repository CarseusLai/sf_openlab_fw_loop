// Locked: owns the IMU and reports any motion by itself, so the host can tell
// "the person moved the board" apart from "the firmware noticed it".
#include <Arduino_BMI270_BMM150.h>
#include "app.h"
#include "report.h"

static const float MOTION_START_G = 1.5f;   // picking the board up stays below this
static const float MOTION_END_G = 1.2f;
static const unsigned long MOTION_QUIET_MS = 300;

static bool moving = false;
static float motion_peak = 0;
static bool quiet = false;
static unsigned long quiet_since = 0;

static void watch_motion(float g, unsigned long now) {
  if (!moving) {
    if (g > MOTION_START_G) {
      moving = true;
      motion_peak = g;
      quiet = false;
    }
    return;
  }
  if (g > motion_peak) motion_peak = g;
  if (g >= MOTION_END_G) {
    quiet = false;
    return;
  }
  if (!quiet) {
    quiet = true;
    quiet_since = now;
  } else if (now - quiet_since >= MOTION_QUIET_MS) {
    report_motion(motion_peak);
    moving = false;
  }
}

void setup() {
  report_begin("base");
  if (!IMU.begin()) {
    report_event("ERR_IMU");
  }
  app_setup();
}

void loop() {
  unsigned long now = millis();
  float x = 0, y = 0, z = 0;
  bool fresh = IMU.accelerationAvailable() && IMU.readAcceleration(x, y, z);
  if (fresh) {
    watch_motion(sqrtf(x * x + y * y + z * z), now);
  }
  app_loop(fresh, x, y, z, now);
}
