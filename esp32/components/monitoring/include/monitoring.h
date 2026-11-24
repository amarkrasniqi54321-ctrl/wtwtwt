#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MONITORING_MAX_RULES 10

typedef enum {
    MONITORING_METRIC_AIR_HUMIDITY,
    MONITORING_METRIC_AIR_TEMPERATURE,
    MONITORING_METRIC_SOIL_HUMIDITY,
} monitoring_metric_t;

typedef enum {
    MONITORING_OP_LT,
    MONITORING_OP_LE,
    MONITORING_OP_GT,
    MONITORING_OP_GE,
    MONITORING_OP_EQ,
    MONITORING_OP_NE,
} monitoring_operator_t;

typedef struct {
    int id;
    monitoring_metric_t metric;
    monitoring_operator_t comparison;
    float threshold;
    bool active;
    int64_t last_alert_us;
} monitoring_rule_t;

typedef struct {
    monitoring_rule_t rules[MONITORING_MAX_RULES];
    size_t count;
} monitoring_ruleset_t;

typedef struct {
    bool air_valid;
    float air_temperature_c;
    float air_humidity_percent;
    bool soil_valid;
    int soil_humidity_normalized;
} monitoring_measurements_t;

typedef enum {
    MONITORING_RULE_INACTIVE,
    MONITORING_RULE_ACTIVE_NO_ALERT,
    MONITORING_RULE_ALERT_NEW,
    MONITORING_RULE_ALERT_COOLDOWN,
    MONITORING_RULE_READING_MISSING,
} monitoring_rule_result_t;

esp_err_t monitoring_rules_parse(const char *text, size_t length,
                                 monitoring_ruleset_t *ruleset,
                                 char *error, size_t error_size);
monitoring_rule_result_t monitoring_rule_evaluate(
    monitoring_rule_t *rule,
    const monitoring_measurements_t *measurements,
    int64_t now_us,
    int64_t cooldown_us);

#ifdef __cplusplus
}
#endif
