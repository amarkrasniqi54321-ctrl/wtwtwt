#pragma once

#include <stdbool.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int raw;
    int millivolts;
    /* -1 until physical dry/wet calibration has been confirmed. */
    int normalized;
    bool calibration_confirmed;
} soil_moisture_reading_t;

esp_err_t soil_moisture_init(int dry_raw, int wet_raw,
                             bool calibration_confirmed);
esp_err_t soil_moisture_read(soil_moisture_reading_t *reading);
int soil_moisture_normalize(int raw, int dry_raw, int wet_raw);

#ifdef __cplusplus
}
#endif
