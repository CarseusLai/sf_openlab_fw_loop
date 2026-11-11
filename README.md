# 板子說了才算 — AI 修韌體，由板子判定

> AIPOST OPEN LAB AI Build Challenge 2026 參賽作品。設計：[docs/2026-10-31-design.md](docs/2026-10-31-design.md)｜開發紀錄：[docs/2026-10-31-plan.md](docs/2026-10-31-plan.md)

AI 說它修好了 bug，這句話不算數。

這個作品讓 AI 修一塊 Arduino 板子的韌體，改好的程式**燒進真的板子**，由人照語音提示搖晃、翻面，再由**板子自己回報的事件**、照人事先寫好的檢查判定修好沒有。判定沒過，就帶著板子給的原因，換一個更強的 AI 重修。

## 一輪實錄

`runs/20261109-175133-b4`，用狀態網頁的按鈕觸發，整輪約 2 分鐘：

| 步驟 | 誰 | 結果 |
|---|---|---|
| 使用者回報 | — | 「我搖一下板子，燈閃完之後常常就一直亮著……我沒有把板子翻面。」 |
| 第 1 次修 | MixRoute Smart Routing → `gemini-3.5-flash-lite`，2.4 秒 | 「閃爍結束時 LED 狀態計算錯誤」，改了閃燈的奇偶判斷 |
| 判定 | 板子 | ❌ 沒過：「第 2 步：燈預期 OFF，實際 ON」 |
| 第 2 次修 | `claude-sonnet-5-5`，15.6 秒，收到上一次的改動和板子的回報 | 找到真正原因：翻面判斷沒有防抖（`FACE_HOLD_MS = 0`），搖晃時被誤判成翻面 |
| 判定 | 板子 | ✅ 通過（6 個步驟全過） |

第一個 AI 修的是症狀，第二個修的是原因。光看程式碼分不出誰對，板子分得出來。

### 4 個 bug 的實測（2026-11-10～11，都從狀態網頁觸發）

| bug | 第 1 次：Smart Routing | 第 2 次：`claude-sonnet-5-5` | 板子最後判定 |
|---|---|---|---|
| b1 | `gemini-3.5-flash-lite` 改錯閃燈奇偶 → ❌ 燈只亮 2 次 | 改對 | ✅ |
| b2 | `gemini-3.5-flash-lite` 把門檻改成 4.0 g，說是「照註解改」（程式裡沒有這行註解）→ ❌ 輕輕搖到 3.2 g 燈沒閃 | 引用板子量到的 3.2 g，改回 2.5 g | ✅ |
| b3 | `gemini-3.5-flash-lite` 一次改對 → ✅ | 不需要 | ✅ |
| b4 | `gemini-3.5-flash-lite` 只修症狀 → ❌（上表） | 找到防抖問題 | ✅ |

便宜模型 4 個修好 1 個，另外 3 個由板子判定沒過、升級後修好。4 輪合計約 19,000 tokens。

## 為什麼可以信任板子的判定

改程式的 AI 有可能「作弊」，例如讓韌體自己印出「燈亮了」。下面幾層就是為了讓這件事做不到：

- **AI 只能改 `app.cpp`**。燈只能透過 `report.cpp` 控制，事件也只能由它回報；`report.*`、`base.ino`、`app.h` 是鎖住的。
- **燒錄前先過閘門**（[loop/gate.py](loop/gate.py)）：`app.cpp` 新加的程式碼不准出現 `Serial`／`printf`（偽造回報）、`digitalWrite` 等直接控燈、`IMU`（干擾動作見證）、新的 `#include`、組合語言或直接存取暫存器；改動上限 20 行；鎖住的檔必須跟基準版一模一樣。被擋下的改動不會燒進板子。
- **動作見證**：讀加速度的是鎖住的 `base.ino`，只要板子被晃動就回報 `MOTION,<最大 g 值>`，不經過 AI 改的程式。所以判定分得出「人有搖、韌體沒反應」（FAIL）和「人根本沒動」（請重做，不算誰的錯）。
- **燒進去的就是你看到的程式**：編譯後逐一比對編譯資料夾裡的副本和硬碟上的原始碼，不一致就不燒錄。開發時真的遇過 arduino-cli 沿用過期的編譯產物，板子不動卻每 2.8 秒報一次假動作。
- **驗收由人寫**（`bugs/<id>/check.json`），放在 AI 的工作區之外，AI 讀不到也改不到。

## 硬體

- Arduino Nano 33 BLE Sense Rev2（用板上的 BMI270 加速度計和橘色 LED）
- 能傳資料的 USB 線
- 有喇叭的 Windows 電腦（提示用語音念，需要 `Microsoft Hanhan Desktop` 台灣中文語音）

## 安裝（Windows）

1. 下載 [arduino-cli](https://github.com/arduino/arduino-cli/releases) 1.5.1，放到 PATH，或把環境變數 `ARDUINO_CLI` 設成 `arduino-cli.exe` 的完整路徑。
2. 安裝核心和函式庫：

   ```
   arduino-cli core update-index
   arduino-cli core install arduino:mbed_nano@4.6.0
   arduino-cli lib install Arduino_BMI270_BMM150@1.2.4
   ```

3. Python 3.10 以上：`pip install pyserial`
4. MixRoute：在 repo 根目錄建立 `.env`（已列在 `.gitignore`），放兩行：

   ```
   MIXROUTE_API_KEY=一般的 key
   MIXROUTE_ROUTE_KEY=Smart Routing 路由的 key
   ```

   路由在 [console.mixroute.ai/smart-route](https://console.mixroute.ai/smart-route) 建立，三個等級設為 Simple＝`gemini-3.5-flash-lite`、Complex＝`claude-sonnet-5-5`、Ultra＝`claude-opus-5-5`。用 `python loop/mixroute.py names` 確認兩行都讀得到（只印名稱，不印 key）。

## 怎麼跑

接上板子之後：

| 想做什麼 | 指令 |
|---|---|
| 確認工具鏈（編譯＋燒錄＋讀序列埠） | `python loop/flash_check.py firmware/blink` |
| **狀態網頁**，按按鈕挑一個 bug 跑一輪（即時顯示板子回報的事件和搖了幾 g） | `python loop/web.py`，打開 http://127.0.0.1:8765 |
| 不開網頁，直接跑一輪 | `python loop/run.py b4`（預設 `--fixer mixroute --ladder auto,claude-sonnet-5-5`） |
| 只驗收現在的韌體（不修） | `python loop/check.py bugs/b4/check.json firmware/base` |
| 單元測試（不用板子） | `python -m pytest tests` |

板子有兩個 COM 號碼：一般執行時一個，燒錄模式一個。程式靠 USB 的 VID/PID 自動找，不用手動指定。

每一輪的紀錄存在 `runs/<時間>-<bug>/`：`status.json`（每一關的結果、秒數、模型、token）、`fix<N>.diff`（每一層 AI 改了什麼）；網頁觸發的輪次另有輸出記錄 `runs/web-runs.log`。

## 埋好的 bug

| bug | 使用者看到的現象 | 埋在哪裡 |
|---|---|---|
| b1 | 搖一下只閃 2 下 | 閃燈步數少 2 |
| b2 | 怎麼搖都沒反應 | 門檻單位寫錯（m/s² 當成 g） |
| b3 | 燈亮著時搖一下，閃完就熄了 | 閃完沒有回到原本的狀態 |
| b4 | 搖完燈常常一直亮著 | 症狀在閃燈，原因在翻面判斷沒有防抖 |

新增 bug：在 `bugs/<id>/` 放 `bug.patch`（對 `firmware/base/app.cpp`）、`ticket.md`（白話描述）、`check.json`（每一步要念的提示、觸發事件、預期的燈狀態或事件數；觸發設成 `MOTION` 並加 `"peak": [低, 高]`，可以要求這一步的搖晃力道落在範圍內，搖太輕或太重會念出量到的 g 值、請人再搖一次。b2 用這招抓「門檻設太高、只有用力搖才會過」的修法）。`python loop/make_variant.py <id>` 產生有 bug 的版本。

## AI 怎麼用在這個作品裡

- **作品本身**：修 bug 走 MixRoute API。第一次用 Smart Routing（`model: "auto"`，由平台依請求選等級），板子判定沒過就換 `claude-sonnet-5-5`，並附上上一次改了什麼、板子怎麼說。另保留 Claude Code（`--fixer claude-code`，只給讀寫檔的工具、不給 shell）。
- **開發過程**：程式、韌體、測試和文件是在 Claude Code 協助下寫成，每一步都在實機上驗證；量測數據（靜止 1.01 g、用力搖 > 4 g、編譯時間等）來自實際讀數。

## 限制

- 只支援 Nano 33 BLE Sense Rev2，只在 Windows 上測過。
- 驗收要有人照提示搖晃、翻面；動作見證只能偵測晃動（> 1.5 g），翻面時如果晃動不大，「人沒動」和「韌體沒反應」會被當成「請重做」。
- 閘門用關鍵字比對，擋的是已知的作弊方式，不是證明程式沒問題；對錯由板子判定。
- 板子只驗得到檢查有測的東西。b2 原本只測「用力搖」，門檻改成 4.0 g 的錯誤修法也會過；加了「輕輕搖」這一步才抓到。檢查寫得好不好，仍然要靠人。
- AI 附的說明不一定是真的（見上表 b2），所以判定只看板子，不看 AI 怎麼說。
- 埋的 bug 是刻意做的，每個只改一行；真實的 bug 不一定這麼單純。
- 只修一次約 1 分多鐘，升級一次約 2–3 分鐘；其中約 30–60 秒是編譯和燒錄。

## 第三方來源

- [arduino-cli](https://github.com/arduino/arduino-cli)、Arduino Mbed OS Nano Boards 核心（`arduino:mbed_nano`）
- [Arduino_BMI270_BMM150](https://github.com/arduino-libraries/Arduino_BMI270_BMM150)（原始碼標頭為 LGPL 2.1），內含 Bosch 的 BMI270／BMM150 Sensor API
- [pySerial](https://github.com/pyserial/pyserial)
- [MixRoute API](https://mixroute.ai/docs)（Elite Cloud）
- Windows 內建語音合成（System.Speech）

各元件依其專案的授權使用。
