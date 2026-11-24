#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "buzzer.h"
#include "camera_policy.h"
#include "dht11.h"
#include "esp_check.h"
#include "esp_attr.h"
#include "esp_err.h"
#include "esp_idf_version.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "monitoring.h"
#include "measurement_output.h"
#include "raspberry_pi_wake.h"
#include "sdkconfig.h"
#include "soil_moisture.h"

#ifndef CONFIG_SMART_PLANT_SOIL_CALIBRATED
#define CONFIG_SMART_PLANT_SOIL_CALIBRATED 0
#endif

#define SOIL_MOISTURE_GPIO 34
#define ALERT_GAP_MS       300U
#define OPTIMIZED_STATE_MAGIC 0x53504C55UL /* "SPLT" */
#if CONFIG_SMART_PLANT_MODE_BASELINE
#define OPERATING_MODE "BASELINE"
#else
#define OPERATING_MODE "OPTIMIZED"
#endif

static const char *TAG = "smart_plant";

extern const char embedded_rules_start[]
    asm("_binary_smart_plant_rules_start");
extern const char embedded_rules_end[]
    asm("_binary_smart_plant_rules_end");

typedef struct {
    monitoring_measurements_t measurements;
    esp_err_t air_error;
    esp_err_t soil_error;
    bool soil_raw_valid;
    int soil_raw;
    int soil_millivolts;
    bool soil_calibration_confirmed;
} sensor_sample_t;

#if CONFIG_SMART_PLANT_MODE_OPTIMIZED
/* RTC slow memory survives timer deep sleep, but deliberately does not survive
 * cold boot or an unexpected reset. The latter starts a fresh experiment
 * rather than replaying a stale Pi wake request. */
typedef struct {
    uint32_t sequence;
    uint64_t timestamp_ms;
    bool air_valid;
    float air_temperature_c;
    float air_humidity_percent;
    esp_err_t air_error;
    bool soil_raw_valid;
    int soil_raw;
    int soil_millivolts;
    bool soil_valid;
    int soil_humidity_normalized;
    esp_err_t soil_error;
} optimized_retained_measurement_t;

typedef struct {
    uint32_t magic;
    camera_policy_t camera_policy;
    uint32_t sequence;
    uint64_t elapsed_ms;
    optimized_retained_measurement_t last_measurement;
    int rule_ids[MONITORING_MAX_RULES];
    bool rule_active[MONITORING_MAX_RULES];
    uint64_t rule_last_alert_ms[MONITORING_MAX_RULES];
} optimized_rtc_state_t;

RTC_DATA_ATTR static optimized_rtc_state_t s_optimized_state;

/* ESP-IDF 6.1 retains the singular API required by the lab procedure but
 * marks it deprecated in favour of a bitmask API. A timer is the only enabled
 * wake source here, so the singular result remains unambiguous. */
static esp_sleep_wakeup_cause_t optimized_wakeup_cause(void)
{
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
    const esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
#pragma GCC diagnostic pop
    return cause;
}

static bool optimized_timer_wakeup(void)
{
    return esp_reset_reason() == ESP_RST_DEEPSLEEP &&
           optimized_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER;
}

static void optimized_state_initialize(void)
{
    if (optimized_timer_wakeup() &&
        s_optimized_state.magic == OPTIMIZED_STATE_MAGIC) {
        ESP_LOGI(TAG,
                 "Timer wake: retained cycle=%lu sequence=%lu last=%lu at %llu ms",
                 (unsigned long)s_optimized_state.camera_policy.since_wake,
                 (unsigned long)s_optimized_state.sequence,
                 (unsigned long)s_optimized_state.last_measurement.sequence,
                 (unsigned long long)s_optimized_state.elapsed_ms);
        return;
    }

    const esp_reset_reason_t reset_reason = esp_reset_reason();
    const esp_sleep_wakeup_cause_t wake_cause = optimized_wakeup_cause();
    memset(&s_optimized_state, 0, sizeof(s_optimized_state));
    s_optimized_state.magic = OPTIMIZED_STATE_MAGIC;
    ESP_LOGW(TAG,
             "Fresh optimized state: reset_reason=%d wakeup_cause=%d",
             (int)reset_reason, (int)wake_cause);
}

static void optimized_restore_rule_state(monitoring_ruleset_t *ruleset)
{
    for (size_t i = 0; i < ruleset->count; ++i) {
        for (size_t j = 0; j < MONITORING_MAX_RULES; ++j) {
            if (s_optimized_state.rule_ids[j] == ruleset->rules[i].id) {
                ruleset->rules[i].active = s_optimized_state.rule_active[j];
                ruleset->rules[i].last_alert_us =
                    (int64_t)s_optimized_state.rule_last_alert_ms[j] * 1000LL;
                break;
            }
        }
    }
}

static void optimized_save_rule_state(const monitoring_ruleset_t *ruleset)
{
    for (size_t i = 0; i < MONITORING_MAX_RULES; ++i) {
        s_optimized_state.rule_ids[i] = 0;
        s_optimized_state.rule_active[i] = false;
        s_optimized_state.rule_last_alert_ms[i] = 0;
    }
    for (size_t i = 0; i < ruleset->count; ++i) {
        s_optimized_state.rule_ids[i] = ruleset->rules[i].id;
        s_optimized_state.rule_active[i] = ruleset->rules[i].active;
        s_optimized_state.rule_last_alert_ms[i] =
            ruleset->rules[i].last_alert_us > 0
                ? (uint64_t)(ruleset->rules[i].last_alert_us / 1000LL)
                : 0;
    }
}

static void optimized_save_measurement(const measurement_output_record_t *record)
{
    optimized_retained_measurement_t *saved =
        &s_optimized_state.last_measurement;
    saved->sequence = record->sequence;
    saved->timestamp_ms = (uint64_t)record->uptime_ms;
    saved->air_valid = record->measurements.air_valid;
    saved->air_temperature_c = record->measurements.air_temperature_c;
    saved->air_humidity_percent = record->measurements.air_humidity_percent;
    saved->air_error = record->air_error;
    saved->soil_raw_valid = record->soil_raw_valid;
    saved->soil_raw = record->soil_raw;
    saved->soil_millivolts = record->soil_millivolts;
    saved->soil_valid = record->measurements.soil_valid;
    saved->soil_humidity_normalized =
        record->measurements.soil_humidity_normalized;
    saved->soil_error = record->soil_error;
}

static void optimized_enter_deep_sleep(void)
{
    const uint64_t interval_us =
        (uint64_t)CONFIG_SMART_PLANT_OPTIMIZED_MIN_INTERVAL_S * 1000000ULL;
    ESP_ERROR_CHECK(esp_sleep_enable_timer_wakeup(interval_us));
    ESP_LOGI(TAG, "Entering timer deep sleep for %d second(s)",
             CONFIG_SMART_PLANT_OPTIMIZED_MIN_INTERVAL_S);
    esp_deep_sleep_start();
}
#endif

static esp_err_t load_configuration(monitoring_ruleset_t *ruleset)
{
    const size_t length =
        (size_t)(embedded_rules_end - embedded_rules_start);
    char error[128];
    const esp_err_t err = monitoring_rules_parse(
        embedded_rules_start, length, ruleset, error, sizeof(error));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Invalid configuration.txt: %s", error);
        return err;
    }

    ESP_LOGI(TAG, "Loaded %u alert rule(s) from configuration.txt",
             (unsigned)ruleset->count);
    return ESP_OK;
}

static void log_dht11_error(esp_err_t err)
{
    if (err == ESP_ERR_TIMEOUT) {
        ESP_LOGE(TAG,
                 "DHT11 did not respond on GPIO%d; check power, DATA and pull-up",
                 CONFIG_SMART_PLANT_DHT11_GPIO);
    } else if (err == ESP_ERR_INVALID_CRC) {
        ESP_LOGE(TAG, "DHT11 checksum failed; air reading discarded");
    } else if (err == ESP_ERR_INVALID_RESPONSE) {
        ESP_LOGE(TAG, "DHT11 returned invalid data; air reading discarded");
    } else {
        ESP_LOGE(TAG, "DHT11 read failed: %s", esp_err_to_name(err));
    }
}

static void read_air(sensor_sample_t *sample)
{
    dht11_reading_t reading = {0};
    const esp_err_t err = dht11_read(&reading);
    sample->air_error = err;
    if (err != ESP_OK) {
        log_dht11_error(err);
        return;
    }

    sample->measurements.air_valid = true;
    sample->measurements.air_temperature_c = reading.temperature_c;
    sample->measurements.air_humidity_percent = reading.humidity_percent;
    ESP_LOGI(TAG, "Air temperature: %.1f C", (double)reading.temperature_c);
    ESP_LOGI(TAG, "Air humidity: %.1f %%RH", (double)reading.humidity_percent);
}

static void read_soil(sensor_sample_t *sample)
{
    soil_moisture_reading_t reading = {0};
    const esp_err_t err = soil_moisture_read(&reading);
    sample->soil_error = err;
    sample->soil_calibration_confirmed =
        CONFIG_SMART_PLANT_SOIL_CALIBRATED;
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Soil ADC read invalid: %s", esp_err_to_name(err));
        return;
    }

    sample->soil_raw_valid = true;
    sample->soil_raw = reading.raw;
    sample->soil_millivolts = reading.millivolts;
    sample->soil_calibration_confirmed = reading.calibration_confirmed;

    if (reading.millivolts >= 0) {
        ESP_LOGI(TAG, "Soil ADC: raw=%d, voltage=%d mV",
                 reading.raw, reading.millivolts);
    } else {
        ESP_LOGI(TAG, "Soil ADC: raw=%d, voltage calibration unavailable",
                 reading.raw);
    }

    if (!reading.calibration_confirmed) {
        ESP_LOGW(TAG,
                 "Soil normalization unavailable: measure dry/wet endpoints; soil alerts remain disabled");
        return;
    }

    sample->measurements.soil_valid = true;
    sample->measurements.soil_humidity_normalized = reading.normalized;
    ESP_LOGI(TAG, "Soil moisture: %d/1000 (0=dry, 1000=wet)",
             reading.normalized);
}

static size_t evaluate_rules(monitoring_ruleset_t *ruleset,
                             const monitoring_measurements_t *measurements,
                             int64_t now_us,
                             int *alert_ids, size_t alert_capacity)
{
    size_t alert_count = 0;
    const int64_t cooldown_us =
        (int64_t)CONFIG_SMART_PLANT_ALERT_COOLDOWN_S * 1000000LL;

    for (size_t i = 0; i < ruleset->count; ++i) {
        monitoring_rule_t *rule = &ruleset->rules[i];
        const monitoring_rule_result_t result = monitoring_rule_evaluate(
            rule, measurements, now_us, cooldown_us);

        if (result == MONITORING_RULE_READING_MISSING) {
            if (rule->metric == MONITORING_METRIC_SOIL_HUMIDITY &&
                !CONFIG_SMART_PLANT_SOIL_CALIBRATED) {
                ESP_LOGW(TAG,
                         "Rule %d skipped: soil calibration is not confirmed",
                         rule->id);
            } else {
                ESP_LOGW(TAG, "Rule %d skipped: required sensor reading is invalid",
                         rule->id);
            }
            continue;
        }

        if (result != MONITORING_RULE_ALERT_NEW &&
            result != MONITORING_RULE_ALERT_COOLDOWN) {
            continue;
        }

        ESP_LOGW(TAG, "Rule %d triggered (%s); playing %d beep(s)",
                 rule->id,
                 result == MONITORING_RULE_ALERT_NEW
                     ? "condition became active"
                     : "cooldown elapsed",
                 rule->id);

        if (alert_count < alert_capacity) {
            alert_ids[alert_count++] = rule->id;
        } else {
            ESP_LOGE(TAG, "Alert buffer is full; rule %d was not queued",
                     rule->id);
        }
    }
    return alert_count;
}

static void play_alerts(const int *alert_ids, size_t alert_count)
{
    for (size_t i = 0; i < alert_count; ++i) {
        const esp_err_t beep_err = buzzer_beep(alert_ids[i]);
        if (beep_err != ESP_OK) {
            ESP_LOGE(TAG, "Buzzer alert failed: %s",
                     esp_err_to_name(beep_err));
        }
        ESP_ERROR_CHECK_WITHOUT_ABORT(buzzer_stop());
        vTaskDelay(pdMS_TO_TICKS(ALERT_GAP_MS));
    }
}

static esp_err_t configure_operating_mode(void)
{
#if CONFIG_SMART_PLANT_MODE_BASELINE
    ESP_LOGW(TAG,
             "Operating mode: BASELINE (fixed 20 s, every sample transmitted, automatic light sleep disabled)");
    return ESP_OK;
#else
    ESP_LOGI(TAG,
             "Operating mode: OPTIMIZED (%d s timer deep sleep, adaptive Pi wake up to %d stable cycle(s))",
             CONFIG_SMART_PLANT_OPTIMIZED_MIN_INTERVAL_S,
             CONFIG_SMART_PLANT_OPTIMIZED_PI_WAKE_CYCLES);
    return ESP_OK;
#endif
}

void app_main(void)
{
    ESP_LOGI(TAG, "PECD Smart Plant starting on ESP-IDF %s",
             esp_get_idf_version());
    ESP_LOGI(TAG,
             "GPIOs: buzzer=%d, DHT11=%d, soil AO=%d (ADC1_CH6), Pi wake=%d",
             CONFIG_SMART_PLANT_BUZZER_GPIO,
             CONFIG_SMART_PLANT_DHT11_GPIO,
             SOIL_MOISTURE_GPIO,
             WAKE_PIN);

    if (CONFIG_SMART_PLANT_BUZZER_GPIO == CONFIG_SMART_PLANT_DHT11_GPIO ||
        CONFIG_SMART_PLANT_BUZZER_GPIO == SOIL_MOISTURE_GPIO ||
        CONFIG_SMART_PLANT_DHT11_GPIO == SOIL_MOISTURE_GPIO ||
        CONFIG_SMART_PLANT_BUZZER_GPIO == SMART_PLANT_UART_TX_GPIO ||
        CONFIG_SMART_PLANT_BUZZER_GPIO == SMART_PLANT_UART_RX_GPIO ||
        CONFIG_SMART_PLANT_DHT11_GPIO == SMART_PLANT_UART_TX_GPIO ||
        CONFIG_SMART_PLANT_DHT11_GPIO == SMART_PLANT_UART_RX_GPIO ||
        WAKE_PIN == CONFIG_SMART_PLANT_BUZZER_GPIO ||
        WAKE_PIN == CONFIG_SMART_PLANT_DHT11_GPIO ||
        WAKE_PIN == SOIL_MOISTURE_GPIO ||
        WAKE_PIN == SMART_PLANT_UART_TX_GPIO ||
        WAKE_PIN == SMART_PLANT_UART_RX_GPIO) {
        ESP_LOGE(TAG, "GPIO assignments overlap");
        ESP_ERROR_CHECK(ESP_ERR_INVALID_ARG);
    }

    ESP_ERROR_CHECK(raspberry_pi_wake_init());
    /* GPIO26 stays released at boot. In OPTIMIZED mode it is pulsed only
     * for scheduled checks or newly detected sensor alarms. */
    ESP_ERROR_CHECK(configure_operating_mode());

    /* Initialization order required by the project: buzzer, DHT11, soil. */
    ESP_ERROR_CHECK(buzzer_init());
    ESP_LOGI(TAG, "Buzzer initialized silently; no startup beep is played");
    ESP_ERROR_CHECK(dht11_init((gpio_num_t)CONFIG_SMART_PLANT_DHT11_GPIO));
    ESP_ERROR_CHECK(soil_moisture_init(
        CONFIG_SMART_PLANT_SOIL_DRY_RAW,
        CONFIG_SMART_PLANT_SOIL_WET_RAW,
        CONFIG_SMART_PLANT_SOIL_CALIBRATED));
    ESP_ERROR_CHECK(measurement_output_init());

    monitoring_ruleset_t ruleset = {0};
    ESP_ERROR_CHECK(load_configuration(&ruleset));

#if CONFIG_SMART_PLANT_MODE_OPTIMIZED
    optimized_state_initialize();
    optimized_restore_rule_state(&ruleset);
#endif
    ESP_LOGI(TAG,
             "Serial protocol ready on UART2 GPIO%d TX/GPIO%d RX at %d baud: %s%s",
             SMART_PLANT_UART_TX_GPIO, SMART_PLANT_UART_RX_GPIO,
             SMART_PLANT_UART_BAUD_RATE, SMART_PLANT_SERIAL_PREFIX,
             SMART_PLANT_SERIAL_PROTOCOL);
    ESP_LOGI(TAG, "Alert cooldown=%d second(s)",
             CONFIG_SMART_PLANT_ALERT_COOLDOWN_S);

    uint32_t sequence = 0;
#if CONFIG_SMART_PLANT_MODE_OPTIMIZED
    sequence = s_optimized_state.sequence;
#endif
    while (true) {
#if CONFIG_SMART_PLANT_MODE_BASELINE
        const TickType_t baseline_cycle_start = xTaskGetTickCount();
#endif
        sensor_sample_t sample = {
            .air_error = ESP_FAIL,
            .soil_error = ESP_FAIL,
            .soil_millivolts = -1,
            .soil_calibration_confirmed =
                CONFIG_SMART_PLANT_SOIL_CALIBRATED,
        };
        read_air(&sample);
        read_soil(&sample);

#if CONFIG_SMART_PLANT_MODE_BASELINE
        const int64_t rule_now_us = esp_timer_get_time();
#else
        const int64_t rule_now_us =
            (int64_t)s_optimized_state.elapsed_ms * 1000LL;
#endif
        int alert_ids[MONITORING_MAX_RULES] = {0};
        const size_t alert_count = evaluate_rules(
            &ruleset, &sample.measurements, rule_now_us,
            alert_ids, MONITORING_MAX_RULES);

#if CONFIG_SMART_PLANT_MODE_BASELINE
        const int64_t now_us = esp_timer_get_time();
        const uint32_t next_interval_ms = SMART_PLANT_BASELINE_INTERVAL_MS;
#else
        /* ESP timer restarts after deep sleep, so use the RTC timeline. */
        const int64_t now_us = (int64_t)s_optimized_state.elapsed_ms * 1000LL;
        const uint32_t next_interval_ms =
            CONFIG_SMART_PLANT_OPTIMIZED_MIN_INTERVAL_S * 1000U;
#endif

        measurement_output_record_t output = {
            .mode = OPERATING_MODE,
            .sequence = ++sequence,
            .uptime_ms = now_us / 1000LL,
            .sampling_interval_ms = next_interval_ms,
            .measurements = sample.measurements,
            .air_error = sample.air_error,
            .soil_raw_valid = sample.soil_raw_valid,
            .soil_raw = sample.soil_raw,
            .soil_millivolts = sample.soil_millivolts,
            .soil_error = sample.soil_error,
            .soil_calibration_confirmed =
                sample.soil_calibration_confirmed,
            .triggered_rule_count = alert_count,
        };
        for (size_t i = 0; i < alert_count; ++i) {
            output.triggered_rules[i] = alert_ids[i];
        }
#if CONFIG_SMART_PLANT_MODE_OPTIMIZED
        optimized_save_measurement(&output);
#endif
        ESP_ERROR_CHECK_WITHOUT_ABORT(measurement_output_write(&output));

#if CONFIG_SMART_PLANT_MODE_OPTIMIZED
        s_optimized_state.sequence = sequence;
        optimized_save_rule_state(&ruleset);
        uint32_t alarm_mask = 0;
        for (size_t i = 0; i < ruleset.count; ++i) {
            if (ruleset.rules[i].active) alarm_mask |= 1UL << i;
        }
        const bool sensor_fault = !sample.measurements.air_valid || !sample.soil_raw_valid;
        const bool valid = sample.measurements.air_valid && sample.measurements.soil_valid;
        camera_policy_t *policy = &s_optimized_state.camera_policy;
        const camera_decision_t decision = camera_policy_step(
            policy, alarm_mask, valid, sensor_fault,
            CONFIG_SMART_PLANT_OPTIMIZED_PI_NORMAL_CYCLES,
            CONFIG_SMART_PLANT_OPTIMIZED_PI_WAKE_CYCLES);
        ESP_LOGI(TAG, "CAMERA_POLICY sequence=%lu alarm_mask=%lu valid=%d fault=%d stable_cycles=%lu since_wake=%lu interval_cycles=%lu reason=%s",
                 (unsigned long)sequence, (unsigned long)alarm_mask, valid, sensor_fault,
                 (unsigned long)policy->stable_cycles, (unsigned long)policy->since_wake,
                 (unsigned long)decision.interval_cycles, camera_wake_reason(decision.reason));
        if (decision.reason != CAMERA_WAKE_NONE) {
            const esp_err_t err = raspberry_pi_wake_pulse();
            ESP_LOGI(TAG, "PI_WAKE_REQUEST sequence=%lu reason=%s result=%s",
                     (unsigned long)sequence, camera_wake_reason(decision.reason), esp_err_to_name(err));
            camera_policy_complete(policy, err == ESP_OK, CONFIG_SMART_PLANT_OPTIMIZED_PI_NORMAL_CYCLES);
        }
#endif
        play_alerts(alert_ids, alert_count);
#if CONFIG_SMART_PLANT_MODE_OPTIMIZED
        s_optimized_state.elapsed_ms += next_interval_ms;
        optimized_enter_deep_sleep();
#endif

#if CONFIG_SMART_PLANT_MODE_BASELINE
        /* Fixed cadence without catch-up reads that could violate DHT11 timing. */
        const TickType_t baseline_period =
            pdMS_TO_TICKS(SMART_PLANT_BASELINE_INTERVAL_MS);
        const TickType_t baseline_elapsed =
            xTaskGetTickCount() - baseline_cycle_start;
        if (baseline_elapsed < baseline_period) {
            vTaskDelay(baseline_period - baseline_elapsed);
        } else {
            ESP_LOGW(TAG,
                     "Baseline cycle overran 20 s; skipping catch-up delay to preserve DHT11 minimum interval");
        }
#endif
    }
}
