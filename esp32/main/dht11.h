#pragma once

#include "driver/gpio.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float temperature_c;
    float humidity_percent;
} dht11_reading_t;

/** Configure the one-wire DHT11 data signal on an input/output-capable GPIO. */
esp_err_t dht11_init(gpio_num_t gpio_num);

/**
 * Read and validate one DHT11 sample.
 *
 * The driver delays for any remaining part of the two-second minimum interval.
 * The function returns
 * ESP_ERR_TIMEOUT for a disconnected/non-responsive sensor,
 * ESP_ERR_INVALID_CRC for a checksum failure, and ESP_ERR_INVALID_RESPONSE
 * for data outside the DHT11 operating range.
 */
esp_err_t dht11_read(dht11_reading_t *reading);

#ifdef __cplusplus
}
#endif
