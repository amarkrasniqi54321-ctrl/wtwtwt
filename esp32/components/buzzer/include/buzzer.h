#pragma once

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t buzzer_init(void);
esp_err_t buzzer_beep(int count);
esp_err_t buzzer_stop(void);

#ifdef __cplusplus
}
#endif
