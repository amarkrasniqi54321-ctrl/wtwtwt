#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_err.h"
#include "monitoring.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SMART_PLANT_SERIAL_PREFIX "SMARTPLANT_JSON:"
#define SMART_PLANT_SERIAL_PROTOCOL "smart-plant-serial-v1"
#define SMART_PLANT_UART_PORT UART_NUM_2
#define SMART_PLANT_UART_TX_GPIO GPIO_NUM_17
#define SMART_PLANT_UART_RX_GPIO GPIO_NUM_16
#define SMART_PLANT_UART_BAUD_RATE 115200
#define SMART_PLANT_BASELINE_INTERVAL_MS 20000U
#define SMART_PLANT_SERIAL_LINE_MAX 1024U

typedef struct {
    const char *mode;
    uint32_t sequence;
    int64_t uptime_ms;
    uint32_t sampling_interval_ms;
    monitoring_measurements_t measurements;
    esp_err_t air_error;
    bool soil_raw_valid;
    int soil_raw;
    int soil_millivolts;
    esp_err_t soil_error;
    bool soil_calibration_confirmed;
    int triggered_rules[MONITORING_MAX_RULES];
    size_t triggered_rule_count;
} measurement_output_record_t;

/** Configure dedicated UART2 on GPIO17 TX and GPIO16 RX. */
esp_err_t measurement_output_init(void);

/** Format one validated, newline-terminated machine-readable record. */
esp_err_t measurement_output_format_json(
    const measurement_output_record_t *record,
    char *line, size_t line_capacity, size_t *line_length);

/** Write one machine-readable JSON record to dedicated UART2. */
esp_err_t measurement_output_write(const measurement_output_record_t *record);

#ifdef __cplusplus
}
#endif
