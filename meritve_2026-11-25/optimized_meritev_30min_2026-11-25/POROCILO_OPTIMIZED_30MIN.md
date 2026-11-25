# PECD Smart Plant — 30-minutna OPTIMIZED meritev (Možnost A — bench način brez izklopa Pi-ja)

- **Datum in čas (UTC):** `2026-11-25T16:32:19Z` – `2026-11-25T17:02:49Z` (`17:32:19` – `18:02:49` CET)
- **`run_id`:** `20261125T163219Z-f1ecb6`
- **Repozitorij / commit:** `https://github.com/luka1222424/wtwtwt` (`296d6f2`) + enaka lokalna popravka (`dht11.c` in `camera_capture.py`) kot pri 30-minutni `BASELINE` meritvi
- **Način delovanja:**
  - **ESP32:** produkcijski `OPTIMIZED` profil (`20 s` timer deep sleep, `normal = 90` ciklov / ~30 min, `stable = 360` ciklov / ~120 min, RTC ohranjanje stanja, adaptivna `CAMERA_POLICY`, `GPIO26` wake pulz)
  - **Raspberry Pi:** `PI_SHUTDOWN_AFTER_INITIAL_CYCLE=0 TEST_DURATION_SECONDS=1830 ./run_optimized.sh` (uradni bench način brez samodejnega izklopa Pi-ja, da ostane SSH dostop in neprekinjeno beleženje `optimized-esp.log`)
- **Kalibracija senzorja tal (GPIO34):** `CONFIG_SMART_PLANT_SOIL_DRY_RAW=1246`, `CONFIG_SMART_PLANT_SOIL_WET_RAW=2390`, `CONFIG_SMART_PLANT_SOIL_CALIBRATED=y` (identična kot pri `BASELINE`)

## Preverjeni rezultati

| Metrika | Vrednost |
| --- | --- |
| **UART meritve (ESP32 → Pi `/dev/serial0`)** | **89 / 89** (`sequence 127..215`, **0 izgubljenih paketov**) |
| **DHT11 veljavnost (`GPIO4`)** | **89 / 89 (100 %)** — temperatura `21.9 / 22.07 / 22.2 °C`, vlaga `55.0 / 58.39 / 61.0 %` |
| **Senzor tal veljavnost (`GPIO34`)** | **89 / 89 (100 %)** — normalizirano `779 / 798.1 / 810` (`/1000`), surovi ADC `2138 / 2159.7 / 2173` |
| **ESP32 deep-sleep cikli (`optimized-esp.log`)** | **90** `Timer wake` bujenj, **90** `Entering timer deep sleep` prehodov (`7121` vrstic, 650 KB) |
| **Adaptivna `CAMERA_POLICY` & `PI_WAKE_REQUEST`** | **90** ocen politike, **1** načrtovani wake zahtevek: `2026-11-25T16:50:59.746530Z` (`seq=181`, `reason=scheduled_30m`, `result=ESP_OK`); vztrajen alarm ni budil Pi-ja ob vsakem vzorcu |
| **Alarmi / buzzer (`GPIO25`)** | **6** sprožitev pravila 1 (`air_humidity > 50`, cooldown `300 s`): `seq 136, 151, 166, 181, 196, 211` |
| **CSI kamera (`imx708`, `picamera2`)** | **1 / 1 uspešna fotografija** (`111,7 KB` ob `16:32:20Z`, zajem `2,62 s`) |
| **ONNX klasifikacija listov** | **1 / 1 uspešna** (`70,76 ms`, `CPUExecutionProvider`): `unhealthy` (`healthy=0.0019`, `unhealthy=0.9981`) |
| **Raspberry Pi stabilnost** | `throttled=0x0`, `43.3 °C`, `RUN_COMPLETE`, čisti zaključek |

## Priložene datoteke v tej mapi

- `test_events.csv` — vseh 89 časovno označenih `OPTIMIZED` meritev v CSV obliki
- `events_log.txt` — celoten JSONL dnevnik dogodkov na Pi-ju
- `runtime_optimized.log` — izpis procesa na Raspberry Pi-ju (`RUN_MARKER` → `RUN_COMPLETE`)
- `optimized-esp.log` — celoten ESP32 USB serijski dnevnik s časovnimi žigi gostitelja (`7121` vrstic: `Timer wake`, `CAMERA_POLICY`, `PI_WAKE_REQUEST`, `Entering timer deep sleep`)
- `images/` — zajeta fotografija lista (`plant_20261125T163220_199687Z.jpg`)
- `commit.txt` & `service-journal.txt` — revizija kode in systemd zapis
