// Behaviour under test: shake -> 3 quick blinks, turn face down -> lamp toggles.
// Thresholds come from firmware/calibrate (2026-11-02): rest 1.01 g, pick up or
// put down under 1.5 g, a hard shake over 4 g.
#include <Arduino.h>
#include "app.h"
#include "report.h"

static const float SHAKE_G = 2.5f;
static const unsigned long SHAKE_REFRACTORY_MS = 600;
static const int BLINKS = 3;
static const unsigned long BLINK_MS = 150;
static const float FACE_G = 0.7f;
static const unsigned long FACE_HOLD_MS = 300;

static bool lamp_on = false;

static unsigned long last_shake_ms = 0;
static bool shaken_once = false;

static int blink_steps_left = 0;  // each blink is two steps: on, then off
static unsigned long blink_step_ms = 0;

static bool face_down = false;
static unsigned long face_candidate_since = 0;
static bool face_candidate = false;

static void start_blinks(unsigned long now) {
  blink_steps_left = BLINKS * 2;
  blink_step_ms = now;
  report_led(true);
}

static void run_blinks(unsigned long now) {
  if (blink_steps_left == 0 || now - blink_step_ms < BLINK_MS) {
    return;
  }
  blink_step_ms = now;
  blink_steps_left--;
  if (blink_steps_left == 0) {
    report_led(lamp_on);  // back to whatever the lamp was before the shake
  } else {
    report_led(blink_steps_left % 2 == 0);
  }
}

static void check_shake(float g, unsigned long now) {
  if (g < SHAKE_G) {
    return;
  }
  if (shaken_once && now - last_shake_ms < SHAKE_REFRACTORY_MS) {
    return;
  }
  shaken_once = true;
  last_shake_ms = now;
  report_event("SHAKE");
  start_blinks(now);
}

static void check_face(float z, unsigned long now) {
  bool looks_down = face_down ? !(z > FACE_G) : (z < -FACE_G);
  if (looks_down == face_down) {
    face_candidate = false;
    return;
  }
  if (!face_candidate) {
    face_candidate = true;
    face_candidate_since = now;
    return;
  }
  if (now - face_candidate_since < FACE_HOLD_MS) {
    return;
  }
  face_candidate = false;
  face_down = looks_down;
  report_event(face_down ? "FACE_DOWN" : "FACE_UP");
  if (face_down) {
    lamp_on = !lamp_on;
    if (blink_steps_left == 0) {
      report_led(lamp_on);
    }
  }
}

void app_setup() {
}

void app_loop(bool fresh, float x, float y, float z, unsigned long now) {
  if (fresh) {
    check_shake(sqrtf(x * x + y * y + z * z), now);
    check_face(z, now);  // face up (components on top) reads z = +1.01 g (firmware/calibrate)
  }
  run_blinks(now);
}
