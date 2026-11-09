// Locked module: the only code that may drive the LED or print events.
// The host check reads these lines to decide whether a fix works, so the AI
// fixing app.cpp must never be able to change what gets reported.
#pragma once
#include <Arduino.h>

void report_begin(const char *firmware_id);  // waits for the host, then prints READY,<id>
void report_event(const char *name);         // EVT,<ms>,<name>
void report_led(bool on);                    // sets the LED and prints EVT,<ms>,LED,ON|OFF
void report_motion(float peak_g);            // EVT,<ms>,MOTION,<peak g>; called by base.ino only
