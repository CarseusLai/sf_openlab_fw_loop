You are fixing the firmware of an Arduino Nano 33 BLE Sense Rev2. The sketch is in the current folder.

A user reported this problem (in Chinese):

{ticket}

Rules:
- Change only `app.cpp`. Do not touch `report.h` or `report.cpp`: they drive the LED and report what the board does, and the board is judged by what they report.
- Make the smallest change that fixes the reported problem. Do not rewrite or reformat other code.
- You cannot compile, flash or run anything here. After you finish, the board is flashed and a person tests it.

When you are done, reply with one sentence in Traditional Chinese saying what was wrong and what you changed.
