# PECD Smart Plant — 30-minutna produkcijska BASELINE meritev

- **Datum in čas (UTC):** `2026-11-25T14:56:06Z` – `2026-11-25T15:26:36Z` (`15:56:06` – `16:26:36` CET)
- **`run_id`:** `20261125T145606Z-eb1858`
- **Repozitorij / commit:** `https://github.com/luka1222424/wtwtwt` (`296d6f2`) + lokalni popravek stabilnega zajema za `imx708` (`2304x1296`) in odprto-kolektorskega protokola v `dht11.c`
- **Način delovanja:** `BASELINE` (ESP32 brez deep sleep, fiksni interval `20 s`, Raspberry Pi neprekinjeno aktiven, kamera na `1800 s` / 30 min, trajanje `1830 s` za zajem obeh fotografij pri `t=0` in `t=30 min`)
- **Kalibracija senzorja tal (GPIO34):** `CONFIG_SMART_PLANT_SOIL_DRY_RAW=1246`, `CONFIG_SMART_PLANT_SOIL_WET_RAW=2390`, `CONFIG_SMART_PLANT_SOIL_CALIBRATED=y`

## Preverjeni rezultati

| Metrika | Vrednost |
| --- | --- |
| **UART meritve (ESP32 → Pi `/dev/serial0`)** | **92 / 92** (`sequence 11..102`, **0 izgubljenih paketov**) |
| **DHT11 veljavnost (`GPIO4`)** | **92 / 92 (100 %)** — temperatura `22.2 / 22.41 / 22.8 °C`, vlaga `55.0 / 56.90 / 59.0 %` |
| **Senzor tal veljavnost (`GPIO34`)** | **92 / 92 (100 %)** — normalizirano `576 / 643.8 / 679` (`/1000`), surovi ADC `1906 / 1983.1 / 2023` |
| **Alarmi / buzzer (`GPIO25`)** | **6** sprožitev pravila 1 (`air_humidity > 50`, cooldown `300 s`): `seq 16, 32, 47, 62, 77, 93` |
| **CSI kamera (`imx708`, `picamera2`)** | **2 / 2 uspešni fotografiji** (`135 KB` ob `14:56:07Z`, `115 KB` ob `15:26:07Z`; zajem `2.53 s` in `2.62 s`) |
| **ONNX klasifikacija listov** | **2 / 2 uspešni** (`72.45 ms` in `71.36 ms`, `CPUExecutionProvider`): obe `unhealthy` (`0.9998` in `0.9156`) |
| **Raspberry Pi stabilnost** | `throttled=0x0` (brez padca napetosti), `44.3 °C`, `RUN_COMPLETE`, čisti zaključek |

## Priložene datoteke v tej mapi

- `test_events.csv` — vseh 92 časovno označenih meritev v CSV obliki
- `events_log.txt` — celoten JSONL dnevnik dogodkov (meritve, kamera, ONNX, alarmi, zagon/zaključek)
- `runtime_baseline.log` — izpis procesa na Raspberry Pi-ju (`RUN_MARKER` → `RUN_COMPLETE`)
- `baseline-esp.log` — celoten ESP32 USB serijski dnevnik s časovnimi žigi gostitelja (`7042` vrstic)
- `images/` — obe zajeti fotografiji lista (`plant_20261125T145607_743266Z.jpg` in `plant_20261125T152607_743407Z.jpg`)
- `commit.txt` — Git commit SHA
- `service-journal.txt` — systemd dnevnik maskirane storitve `smartplant-optimized.service`
