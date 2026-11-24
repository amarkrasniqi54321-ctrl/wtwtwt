#include "raspberry_pi_wake.h"

#include <stdbool.h>

#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

static const char *TAG = "pi_wake";
static bool s_initialized;
static bool s_has_pulsed;
#if CONFIG_SMART_PLANT_MODE_OPTIMIZED
static int64_t s_last_pulse_us;
#endif

esp_err_t raspberry_pi_wake_init(void)
{
    if (s_initialized) {
        return ESP_OK;
    }

    ESP_RETURN_ON_FALSE(GPIO_IS_VALID_OUTPUT_GPIO(WAKE_PIN),
                        ESP_ERR_INVALID_ARG, TAG,
                        "GPIO%d cannot drive the Raspberry Pi wake signal",
                        WAKE_PIN);

    /* Preload the output latch HIGH before enabling output: in open-drain
     * mode HIGH means released, never actively driven to 3.3 V. */
    ESP_RETURN_ON_ERROR(gpio_set_level(WAKE_PIN, 1), TAG,
                        "Could not preload the released wake level");

    const gpio_config_t config = {
        .pin_bit_mask = 1ULL << WAKE_PIN,
        .mode = GPIO_MODE_OUTPUT_OD,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&config), TAG,
                        "Could not configure GPIO%d as open-drain", WAKE_PIN);
    ESP_RETURN_ON_ERROR(gpio_set_level(WAKE_PIN, 1), TAG,
                        "Could not release the wake signal");

    s_initialized = true;
    ESP_LOGI(TAG, "Raspberry Pi wake signal ready and released on GPIO%d",
             WAKE_PIN);
    return ESP_OK;
}

esp_err_t raspberry_pi_wake_pulse(void)
{
    ESP_RETURN_ON_ERROR(raspberry_pi_wake_init(), TAG,
                        "Could not initialize Raspberry Pi wake signal");

#if CONFIG_SMART_PLANT_MODE_OPTIMIZED
    const int64_t now_us = esp_timer_get_time();
    const int64_t cooldown_us =
        (int64_t)CONFIG_SMART_PLANT_PI_WAKE_COOLDOWN_S * 1000000LL;
    if (s_has_pulsed && now_us - s_last_pulse_us < cooldown_us) {
        ESP_LOGI(TAG, "Wake pulse suppressed by %d second cooldown",
                 CONFIG_SMART_PLANT_PI_WAKE_COOLDOWN_S);
        return ESP_OK;
    }
#endif

    ESP_LOGI(TAG, "Raspberry Pi wake pulse: GPIO%d LOW for %u ms",
             WAKE_PIN, (unsigned)RASPBERRY_PI_WAKE_PULSE_MS);
    ESP_RETURN_ON_ERROR(gpio_set_level(WAKE_PIN, 0), TAG,
                        "Could not assert the wake signal");
    vTaskDelay(pdMS_TO_TICKS(RASPBERRY_PI_WAKE_PULSE_MS));
    ESP_RETURN_ON_ERROR(gpio_set_level(WAKE_PIN, 1), TAG,
                        "Could not release the wake signal after the pulse");

#if CONFIG_SMART_PLANT_MODE_OPTIMIZED
    s_last_pulse_us = esp_timer_get_time();
#endif
    s_has_pulsed = true;
    ESP_LOGI(TAG, "Raspberry Pi wake signal released on GPIO%d", WAKE_PIN);
    return ESP_OK;
}
