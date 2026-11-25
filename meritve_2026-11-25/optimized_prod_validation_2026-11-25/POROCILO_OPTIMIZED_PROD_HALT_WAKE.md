# Poročilo: OPTIMIZED produkcijska strojna validacija (`HALT → GPIO wake → boot → capture → ONNX → HALT`)

**Datum izvedbe:** 2026-11-25 (`18:23 UTC` – `19:23 UTC` / `19:23 CET` – `20:23 CET`)  
**Strojna oprema:** ESP32-WROOM-32 (`COM4` na zunanjem Windows PC za neprekinjen zajem) + Raspberry Pi 4 Model B Rev 1.5 (`pecd-al`, stalno napajan tudi v HALT) + CSI kamera `imx708`  
**Git commit (osnova):** `296d6f263b17e3c549f89f1956170d3d928ae2dc` (ohranjeni popravki DHT11, kamere `2304x1296` + WirePlumber in kalibracije prsti `DRY=1246`, `WET=2390`)  
**Monsoon:** ni bil na voljo (profil električne moči ni zajet).

---

## 1. Potrjena produkcijska konfiguracija (brez sprememb algoritma ali intervalov)

- **Produkcijski samodejni izklop Pi:** `PI_SHUTDOWN_AFTER_INITIAL_CYCLE=1` prek uradne storitve `smartplant-optimized.service` (`--mode optimized --serial-device /dev/serial0 ... --shutdown-after-initial-cycle`), nameščene z `./install_optimized_power_service.sh` iz `/home/pecd-al/wtwtwt/raspberry_pi`.
- **Raspberry Pi 4 EEPROM (`sudo rpi-eeprom-config` in `vcgencmd bootloader_config`):**
  - `WAKE_ON_GPIO=1`
  - `POWER_OFF_ON_HALT=0`
  - `BOOT_UART=0`
- **Boot konfiguracija (`/boot/firmware/config.txt`):** `enable_uart=1`, brez konfliktnega `dtoverlay=gpio-shutdown`, `/dev/serial0 -> ttyS0`.
- **Sudoers (`/etc/sudoers.d/smartplant-poweroff`):** `pecd-al ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff`.
- **ESP32 firmware (nespremenjen):** `OPTIMIZED`, `20 s` timer deep sleep, `normal = 90` ciklov, `stable = 360` ciklov, nespremenjeni pragovi (`RH > 50 %`, `T < 15 °C`, `soil < 300/1000`), kalibracija `DRY_RAW=1246`, `WET_RAW=2390`, `CALIBRATED=y`.
- **Ožičenje GPIO wake in UART2:** `ESP32 GPIO26 → Pi GPIO3 (pin 5)`, `ESP32 GND → Pi GND (pin 6)`, `ESP32 GPIO17 (TX2) → Pi GPIO15 (RX, pin 10)`, `ESP32 GPIO16 (RX2) → Pi GPIO14 (TX, pin 8)`.
- **Neprekinjeno zajemanje ESP32 logov:** ESP32 USB/UART0 je bil ves čas priključen na zunanji Windows računalnik (`COM4`, 115200 baud, UTC časovni žigi v `optimized-esp.log`), zato HALT stanja Raspberry Pi niso prekinila beleženja.

---

## 2. Povzetek PASS / FAIL po zahtevanih korakih

| Korak | Opis zahteve | Status | Verificirani dokazi |
|---|---|---|---|
| 1 | EEPROM (`WAKE_ON_GPIO=1`, `POWER_OFF_ON_HALT=0`) & `systemd` (`--shutdown-after-initial-cycle`) | **PASS** | `test-config.txt` (`rpi-eeprom-config`, `vcgencmd bootloader_config`, `systemctl cat smartplant-optimized.service`, brez `dtoverlay=gpio-shutdown`) |
| 2 | Začetni zagon Pi → kamera + ONNX → samodejni HALT | **PASS** | `Boot #1` (`run_id=20261125T182908Z-966710`): zajem `2,68 s`, ONNX `281,6 ms` (`unhealthy`), `pi_poweroff_requested`, `pi_reachability_host.log`: `UP_SSH22` (`18:29:32Z`) → `DOWN` (`18:29:35Z`), ping nedosegljiv |
| 3 | ESP32 neodvisno nadaljuje meritve in deep sleep med HALT | **PASS** | `optimized-esp.log`: neprekinjenih **174** deep-sleep ciklov (`18:23:12Z` – `19:22:41Z`), `174/174` veljavnih DHT11, `140/174` veljavnih soil (34 načrtovanih `raw=0` med suhim izvlekom) |
| 4 | Načrtovani GPIO wake (`scheduled_30m`, 90 ciklov) → boot → kamera → ONNX → HALT | **PASS** | ESP32 `18:57:55.103Z` (`seq=148`, `GPIO26 LOW 250 ms`, `reason=scheduled_30m`, `ESP_OK`) → Pi `Boot #2` (`run_id=20261125T182911Z-7ee11b`): zajem `2,63 s` (`plant_20261125T182916_459198Z.jpg`, 117 KB), ONNX `104,0 ms` (`unhealthy`), `pi_poweroff_requested` → HALT |
| 5 | Alarmno sproženi GPIO wake (`alarm_new`) → boot → kamera → ONNX → HALT | **PASS** | ESP32 `19:19:01.013Z` (`seq=210`, `soil=0/1000`, `raw=415`, `Rule 3 triggered`, buzzer 3× pisk, `reason=alarm_new`, `ESP_OK`) → Pi `Boot #5` (`run_id=20261125T182918Z-d690b8`): vizualno potrjena zelena ACT LED + zajem `2,68 s` (`plant_20261125T182924_082333Z.jpg`, 102 KB), ONNX `148,6 ms` (`unhealthy`), `pi_poweroff_requested` → HALT |
| 6 | Dodatno potrjeni dogodkovni wake cikli (`sensor_fault`) | **PASS** | `Boot #3` (`19:07:06Z`, `seq=175`, `run_id=20261125T182913Z-91a38b`) in `Boot #4` (`19:15:36Z`, `seq=200`, `run_id=20261125T182916Z-0f0a96`, vizualno potrjena zelena ACT LED) — oba z uspešnim zajemom, ONNX in `pi_poweroff_requested` |
| 7 | Varen maintenance izstop brez izklopa (`SIGTERM` + `/boot/firmware/smartplant-maintenance`) | **PASS** | `Boot #6` (`19:22:26Z`, `BOOT_ID=102c98cebc744f3e8564c729ef668142`, `run_id=20261125T182921Z-5137bb`): ustavljeno brez `pi_poweroff_requested` |
| 8 | Monsoon profil električne moči | **N/A** | Monsoon ni bil na voljo |

---

## 3. Korelacija vseh 6 zagonov Raspberry Pi z ESP32 wake dogodki

| Zap. | Sprožilec (ESP32 UTC / dogodek) | Pi `run_id` | Fotografija (velikost) | Zajem kamere | ONNX inferenca (`condition`, `unhealthy_score`) | `pi_poweroff_requested` |
|---:|---|---|---|---:|---|:---:|
| 1 | `18:28:59Z` — začetni ročni `sudo reboot` | `20261125T182908Z-966710` | `plant_20261125T182914_040017Z.jpg` (118 KB) | 2,68 s (`success`) | 281,6 ms (`unhealthy`, `0.9941`) | **Da** → HALT |
| 2 | `18:57:55Z` — **`scheduled_30m`** (`seq=148`, 90 ciklov) | `20261125T182911Z-7ee11b` | `plant_20261125T182916_459198Z.jpg` (117 KB) | 2,63 s (`success`) | 104,0 ms (`unhealthy`, `0.9968`) | **Da** → HALT |
| 3 | `19:07:06Z` — `sensor_fault` (`seq=175`, suh izvlek `raw=0`) | `20261125T182913Z-91a38b` | `plant_20261125T182918_966440Z.jpg` (115 KB) | 2,67 s (`success`) | 247,1 ms (`unhealthy`, `0.9995`) | **Da** → HALT |
| 4 | `19:15:36Z` — `sensor_fault` (`seq=200`, suh izvlek `raw=0`) | `20261125T182916Z-0f0a96` | `plant_20261125T182921_521831Z.jpg` (101 KB) | 2,70 s (`success`) | 265,8 ms (`unhealthy`, `0.9692`) | **Da** → HALT |
| 5 | `19:19:01Z` — **`alarm_new`** (`seq=210`, Rule 3 `soil=0/1000`, `raw=415`) | `20261125T182918Z-d690b8` | `plant_20261125T182924_082333Z.jpg` (102 KB) | 2,68 s (`success`) | 148,6 ms (`unhealthy`, `0.9930`) | **Da** → HALT |
| 6 | `19:22:26Z` — vzdrževalni zagon (`BOOT_ID=102c98ce...`) | `20261125T182921Z-5137bb` | `plant_20261125T182926_541405Z.jpg` (111 KB) | 2,64 s (`success`) | prekinjeno s `SIGTERM` (vzdrževanje) | **Ne** (preklicano) |

*(Opomba: dodatni `sensor_fault` pulz ob `19:19:22.913Z`, 22 s po `alarm_new`, se je zgodil medtem ko je Pi že izvajal Boot #5 in zato po pričakovanju ni sprožil dodatne slike ali prekinitve, ker `dtoverlay=gpio-shutdown` ni omogočen.)*

---

## 4. Pomembna tehnična opažanja (poštena dokumentacija)

1. **Časovni žigi na Raspberry Pi (`18:29:08Z .. 18:29:21Z`):** Raspberry Pi 4 nima baterijsko podprtega strojnega RTC. Ker `smartplant-optimized.service` teče ob `After=local-fs.target` in zaključi celoten cikel (zajem + ONNX + `systemctl poweroff`) v **~9 sekundah** (hitreje kot se vzpostavita Wi-Fi in NTP `systemd-timesyncd`), Pi ob vsakem zagonu nadaljuje od zadnjega shranjenega sistemskega časa (`18:29:08 → 18:29:11 → 18:29:13 → 18:29:16 → 18:29:18 → 18:29:21`). To hkrati pojasni, zakaj zunanji SSH monitor (`pi_reachability_host.log`) pri zagonih #2–#5 ni ujel TCP/22 (Pi se je izklopil hitreje, kot se je zaključila Wi-Fi/SSH povezava). Natančni realni UTC časovni žigi vseh prebujanj so zabeleženi v zunanjem `optimized-esp.log`.
2. **`journalctl --list-boots` (`boots-list.txt`):** Čeprav mapa `/var/log/journal` obstaja, je bila na Raspberry Pi OS prazna (hrambo dnevnikov čez zagone ima privzeto v RAM-u), zato `boots-list.txt` in `service-journal.txt` vsebujeta samo zadnji vzdrževalni zagon (`BOOT_ID=102c98cebc744f3e8564c729ef668142`), predhodni zagoni #1–#5 pa so trajno in nedvoumno potrjeni s 5 ločenimi `run_id` cikli v `events_log.txt` ter 5 različnimi fotografijami v `images/`.
3. **Senzorski CSV (`test_events.csv` na Pi vs `esp32_host_measurements.csv`):** Pred testom je bil `/dev/serial0` UART2 na Pi potrjen z `UART0_RX_OK` (`seq=42` in `seq=43`). Med samimi produkcijskimi bujenji #1–#5 je bil `/dev/serial0` odprt le **~3,5 s** (`serial_connected` v vseh 6 zagonih), medtem ko ESP32 po oddaji paketa in GPIO26 pulzu takoj zaspi za `20 s`. Zato Pi v 3,5-sekundnem oknu ni prejel novega UART paketa in `test_events.csv` na Pi ni bil ustvarjen (0 vrstic). Vseh **174 realnih senzorskih meritev** iz `optimized-esp.log` je ohranjenih v originalnem dnevniku in pregledno izpisanih v `esp32_host_measurements.csv` (brez kakršnihkoli sintetičnih podatkov).
4. **Windows CP210x gonilnik v `optimized-esp.log`:** Pri prehodu ESP32 v deep sleep Windows gonilnik CP210x občasno ponovi zadnji del vrstice (`second(s)`); dnevnik je shranjen neposredno brez ročnega popravljanja.
