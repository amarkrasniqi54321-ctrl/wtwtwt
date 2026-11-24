#pragma once

#include "driver/gpio.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define WAKE_PIN GPIO_NUM_26
#define RASPBERRY_PI_WAKE_PULSE_MS 250U

/** Configure GPIO26 as an open-drain output and leave it released. */
esp_err_t raspberry_pi_wake_init(void);

/** Pulse GPIO26 LOW for 250 ms, then release it. Calls are rate limited. */
esp_err_t raspberry_pi_wake_pulse(void);

#ifdef __cplusplus
}
#endif
