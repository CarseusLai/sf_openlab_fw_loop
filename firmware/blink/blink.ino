// Toolchain smoke test: proves compile -> upload -> serial read works end to end.

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  // The USB CDC port only carries data once the host opens it, so wait for it.
  while (!Serial) {
  }
  Serial.println("READY,blink");
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(250);
  digitalWrite(LED_BUILTIN, LOW);
  delay(250);
}
