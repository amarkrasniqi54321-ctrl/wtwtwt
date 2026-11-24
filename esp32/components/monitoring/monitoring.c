#include "monitoring.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void set_error(char *error, size_t error_size,
                      size_t line_number, const char *message)
{
    if (error != NULL && error_size > 0) {
        snprintf(error, error_size, "line %u: %s",
                 (unsigned)line_number, message);
    }
}

static char *trim(char *text)
{
    while (isspace((unsigned char)*text)) {
        ++text;
    }
    char *end = text + strlen(text);
    while (end > text && isspace((unsigned char)end[-1])) {
        *--end = '\0';
    }
    return text;
}

static bool parse_metric(const char *name, monitoring_metric_t *metric)
{
    if (strcmp(name, "air_humidity") == 0) {
        *metric = MONITORING_METRIC_AIR_HUMIDITY;
    } else if (strcmp(name, "air_temperature") == 0) {
        *metric = MONITORING_METRIC_AIR_TEMPERATURE;
    } else if (strcmp(name, "soil_humidity") == 0) {
        *metric = MONITORING_METRIC_SOIL_HUMIDITY;
    } else {
        return false;
    }
    return true;
}

static bool parse_operator(const char *name, monitoring_operator_t *comparison)
{
    if (strcmp(name, "<") == 0) {
        *comparison = MONITORING_OP_LT;
    } else if (strcmp(name, "<=") == 0) {
        *comparison = MONITORING_OP_LE;
    } else if (strcmp(name, ">") == 0) {
        *comparison = MONITORING_OP_GT;
    } else if (strcmp(name, ">=") == 0) {
        *comparison = MONITORING_OP_GE;
    } else if (strcmp(name, "==") == 0) {
        *comparison = MONITORING_OP_EQ;
    } else if (strcmp(name, "!=") == 0) {
        *comparison = MONITORING_OP_NE;
    } else {
        return false;
    }
    return true;
}

static esp_err_t parse_line(char *line, size_t line_number,
                            monitoring_ruleset_t *ruleset,
                            char *error, size_t error_size)
{
    char metric_name[32] = {0};
    char operator_name[3] = {0};
    int id = 0;
    float threshold = 0.0f;
    int consumed = 0;
    const int fields = sscanf(line, " %d : %31s %2s %f %n",
                              &id, metric_name, operator_name,
                              &threshold, &consumed);
    if (fields != 4) {
        set_error(error, error_size, line_number,
                  "expected '<id>: <metric> <operator> <threshold>'");
        return ESP_ERR_INVALID_ARG;
    }
    char *remainder = trim(line + consumed);
    if (*remainder != '\0' && *remainder != '#') {
        set_error(error, error_size, line_number,
                  "unexpected text after threshold");
        return ESP_ERR_INVALID_ARG;
    }
    if (id < 1 || id > 10) {
        set_error(error, error_size, line_number,
                  "rule id/beep count must be from 1 to 10");
        return ESP_ERR_INVALID_ARG;
    }
    if (!isfinite(threshold)) {
        set_error(error, error_size, line_number,
                  "threshold must be finite");
        return ESP_ERR_INVALID_ARG;
    }
    for (size_t i = 0; i < ruleset->count; ++i) {
        if (ruleset->rules[i].id == id) {
            set_error(error, error_size, line_number, "duplicate rule id");
            return ESP_ERR_INVALID_ARG;
        }
    }
    if (ruleset->count >= MONITORING_MAX_RULES) {
        set_error(error, error_size, line_number, "too many rules");
        return ESP_ERR_NO_MEM;
    }

    monitoring_rule_t *rule = &ruleset->rules[ruleset->count];
    if (!parse_metric(metric_name, &rule->metric)) {
        set_error(error, error_size, line_number, "unknown metric");
        return ESP_ERR_INVALID_ARG;
    }
    if (!parse_operator(operator_name, &rule->comparison)) {
        set_error(error, error_size, line_number, "unsupported comparison operator");
        return ESP_ERR_INVALID_ARG;
    }
    rule->id = id;
    rule->threshold = threshold;
    ruleset->count++;
    return ESP_OK;
}

esp_err_t monitoring_rules_parse(const char *text, size_t length,
                                 monitoring_ruleset_t *ruleset,
                                 char *error, size_t error_size)
{
    if (text == NULL || ruleset == NULL || length == 0 || length > 4096) {
        set_error(error, error_size, 0, "invalid or empty configuration");
        return ESP_ERR_INVALID_ARG;
    }

    memset(ruleset, 0, sizeof(*ruleset));
    size_t line_number = 0;
    size_t offset = 0;
    while (offset < length) {
        ++line_number;
        size_t line_length = 0;
        while (offset + line_length < length &&
               text[offset + line_length] != '\n' &&
               text[offset + line_length] != '\0') {
            ++line_length;
        }
        if (line_length >= 160) {
            set_error(error, error_size, line_number, "line is too long");
            return ESP_ERR_INVALID_SIZE;
        }
        char line[160];
        memcpy(line, text + offset, line_length);
        line[line_length] = '\0';
        char *content = trim(line);
        if (*content != '\0' && *content != '#') {
            const esp_err_t err = parse_line(content, line_number, ruleset,
                                             error, error_size);
            if (err != ESP_OK) {
                return err;
            }
        }
        offset += line_length;
        if (offset < length && text[offset] != '\0') {
            ++offset;
        } else if (offset < length) {
            break;
        }
    }

    if (ruleset->count == 0) {
        set_error(error, error_size, 0, "configuration contains no rules");
        return ESP_ERR_INVALID_ARG;
    }
    if (error != NULL && error_size > 0) {
        error[0] = '\0';
    }
    return ESP_OK;
}

static bool compare(float value, monitoring_operator_t comparison, float threshold)
{
    switch (comparison) {
    case MONITORING_OP_LT:
        return value < threshold;
    case MONITORING_OP_LE:
        return value <= threshold;
    case MONITORING_OP_GT:
        return value > threshold;
    case MONITORING_OP_GE:
        return value >= threshold;
    case MONITORING_OP_EQ:
        return fabsf(value - threshold) < 0.0001f;
    case MONITORING_OP_NE:
        return fabsf(value - threshold) >= 0.0001f;
    default:
        return false;
    }
}

monitoring_rule_result_t monitoring_rule_evaluate(
    monitoring_rule_t *rule,
    const monitoring_measurements_t *measurements,
    int64_t now_us,
    int64_t cooldown_us)
{
    if (rule == NULL || measurements == NULL) {
        return MONITORING_RULE_READING_MISSING;
    }

    bool valid = false;
    float value = 0.0f;
    switch (rule->metric) {
    case MONITORING_METRIC_AIR_HUMIDITY:
        valid = measurements->air_valid;
        value = measurements->air_humidity_percent;
        break;
    case MONITORING_METRIC_AIR_TEMPERATURE:
        valid = measurements->air_valid;
        value = measurements->air_temperature_c;
        break;
    case MONITORING_METRIC_SOIL_HUMIDITY:
        valid = measurements->soil_valid;
        value = (float)measurements->soil_humidity_normalized;
        break;
    }
    if (!valid) {
        /* A communication failure is not evidence that the condition cleared.
         * Preserve state so a recovered sensor cannot bypass the cooldown. */
        return MONITORING_RULE_READING_MISSING;
    }

    const bool active_now = compare(value, rule->comparison, rule->threshold);
    if (!active_now) {
        rule->active = false;
        return MONITORING_RULE_INACTIVE;
    }
    if (!rule->active) {
        rule->active = true;
        rule->last_alert_us = now_us;
        return MONITORING_RULE_ALERT_NEW;
    }
    if (cooldown_us > 0 && now_us - rule->last_alert_us >= cooldown_us) {
        rule->last_alert_us = now_us;
        return MONITORING_RULE_ALERT_COOLDOWN;
    }
    return MONITORING_RULE_ACTIVE_NO_ALERT;
}
