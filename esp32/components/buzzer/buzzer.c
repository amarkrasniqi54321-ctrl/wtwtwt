#include "buzzer.h"

#include <stdbool.h>

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_check.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#define BUZZER_FREQUENCY_HZ 2000
#define BUZZER_DUTY_10_BIT  512U
#define BEEP_ON_MS          180U
#define BEEP_OFF_MS         220U
#define MAX_BEEP_COUNT      10

static const char *TAG = "buzzer";
static bool s_initialized;

static esp_err_t set_tone(bool enabled)
{
    ESP_RETURN_ON_FALSE(s_initialized, ESP_ERR_INVALID_STATE, TAG,
                        "buzzer_init() was not called");
    ESP_RETURN_ON_ERROR(
        ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0,
                      enabled ? BUZZER_DUTY_10_BIT : 0),
        TAG, "Could not set LEDC duty");
    return ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
}

esp_err_t buzzer_init(void)
{
    if (s_initialized) {
        return ESP_OK;
    }
    ESP_RETURN_ON_FALSE(GPIO_IS_VALID_OUTPUT_GPIO(CONFIG_SMART_PLANT_BUZZER_GPIO),
                        ESP_ERR_INVALID_ARG, TAG,
                        "configured buzzer GPIO cannot drive an output");

    const ledc_timer_config_t timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_10_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = BUZZER_FREQUENCY_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_RETURN_ON_ERROR(ledc_timer_config(&timer), TAG,
                        "Could not configure LEDC timer");

    const ledc_channel_config_t channel = {
        .gpio_num = CONFIG_SMART_PLANT_BUZZER_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0,
        .flags.output_invert = 0,
    };
    ESP_RETURN_ON_ERROR(ledc_channel_config(&channel), TAG,
                        "Could not configure LEDC channel");
    s_initialized = true;
    ESP_LOGI(TAG, "LEDC ready: GPIO%d, %d Hz, 50%% duty while active",
             CONFIG_SMART_PLANT_BUZZER_GPIO, BUZZER_FREQUENCY_HZ);
    return ESP_OK;
}

esp_err_t buzzer_beep(int count)
{
    ESP_RETURN_ON_FALSE(count > 0 && count <= MAX_BEEP_COUNT,
                        ESP_ERR_INVALID_ARG, TAG,
                        "beep count must be from 1 to %d", MAX_BEEP_COUNT);

    for (int i = 0; i < count; ++i) {
        ESP_RETURN_ON_ERROR(set_tone(true), TAG, "Could not start tone");
        vTaskDelay(pdMS_TO_TICKS(BEEP_ON_MS));
        ESP_RETURN_ON_ERROR(set_tone(false), TAG, "Could not stop tone");
        if (i + 1 < count) {
            vTaskDelay(pdMS_TO_TICKS(BEEP_OFF_MS));
        }
    }
    return ESP_OK;
}

esp_err_t buzzer_stop(void)
{
    ESP_RETURN_ON_FALSE(s_initialized, ESP_ERR_INVALID_STATE, TAG,
                        "buzzer_init() was not called");
    return ledc_stop(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, 0);
}
