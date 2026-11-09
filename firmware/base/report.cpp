#include "report.h"

static bool led_state = false;

void report_begin(const char *firmware_id) {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  Serial.begin(115200);
  // The CDC port only carries data once the host opens it; a READY sent earlier is lost.
  while (!Serial) {
  }
  Serial.print("READY,");
  Serial.println(firmware_id);
}

void report_event(const char *name) {
  Serial.print("EVT,");
  Serial.print(millis());
  Serial.print(",");
  Serial.println(name);
}

void report_motion(float peak_g) {
  Serial.print("EVT,");
  Serial.print(millis());
  Serial.print(",MOTION,");
  Serial.println(peak_g, 2);
}

void report_led(bool on) {
  if (on == led_state) {
    return;  // only real changes count as events
  }
  led_state = on;
  digitalWrite(LED_BUILTIN, on ? HIGH : LOW);
  Serial.print("EVT,");
  Serial.print(millis());
  Serial.println(on ? ",LED,ON" : ",LED,OFF");
}
