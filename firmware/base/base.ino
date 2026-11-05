#include "app.h"
#include "report.h"

void setup() {
  report_begin("base");
  app_setup();
}

void loop() {
  app_loop();
}
