# 板子說了才算 — AI 修韌體閉環（草稿）

> OPEN LAB AI Build Challenge 2026 參賽作品，開發中。設計：[docs/2026-10-31-design.md](docs/2026-10-31-design.md)｜計畫：[docs/2026-10-31-plan.md](docs/2026-10-31-plan.md)

## 硬體

- Arduino Nano 33 BLE Sense Rev2
- 能傳資料的 USB 線

## 安裝（Windows）

1. 下載 [arduino-cli](https://github.com/arduino/arduino-cli/releases) 1.5.1，放到 PATH 裡，或把 `ARDUINO_CLI` 環境變數設成 `arduino-cli.exe` 的完整路徑
2. 安裝核心和函式庫：

   ```
   arduino-cli core update-index
   arduino-cli core install arduino:mbed_nano@4.6.0
   arduino-cli lib install Arduino_BMI270_BMM150@1.2.4
   ```

3. Python 3.10 以上：`pip install pyserial`

## 確認工具鏈能動

接上板子，一行指令完成編譯、燒錄、讀序列埠：

```
python loop/flash_check.py firmware/blink
```

成功時會印出：

```
PASS: READY,blink on COM9 via COM3 (compile 4.7s, upload 7.8s, total 12.9s)
```

COM 號碼依電腦而定。板子有兩個 COM 號碼：一般執行時一個（上例 COM9），燒錄模式一個（上例 COM3），程式靠 USB 的 VID/PID 自動找，不用手動指定。
