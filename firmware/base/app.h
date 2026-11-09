#pragma once

void app_setup();
// fresh: x, y, z hold a new accelerometer sample in g (read by base.ino).
void app_loop(bool fresh, float x, float y, float z, unsigned long now);
