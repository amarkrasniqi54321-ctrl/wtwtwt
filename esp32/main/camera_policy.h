#pragma once
#include <stdbool.h>
#include <stdint.h>

/* State survives deep sleep in RTC memory. First scheduled check is normal. */
typedef struct {
    uint32_t since_wake;
    uint32_t stable_cycles;
    uint32_t previous_alarm_mask;
    bool previous_fault;
    bool has_requested;
} camera_policy_t;
typedef enum { CAMERA_WAKE_NONE, CAMERA_WAKE_ALARM, CAMERA_WAKE_FAULT,
               CAMERA_WAKE_NORMAL, CAMERA_WAKE_STABLE } camera_wake_reason_t;
typedef struct {
    camera_wake_reason_t reason;
    uint32_t interval_cycles;
} camera_decision_t;

static inline camera_decision_t camera_policy_step(camera_policy_t *s,
    uint32_t alarm_mask, bool valid, bool sensor_fault, uint32_t normal, uint32_t stable)
{
    if (s->since_wake < UINT32_MAX) ++s->since_wake;
    if (valid && alarm_mask == 0) {
        if (s->stable_cycles < stable) ++s->stable_cycles;
    } else {
        s->stable_cycles = 0;
    }
    const bool extended = s->has_requested && s->stable_cycles >= normal;
    camera_decision_t d = {CAMERA_WAKE_NONE, extended ? stable : normal};
    if ((alarm_mask & ~s->previous_alarm_mask) != 0)
        d.reason = CAMERA_WAKE_ALARM;
    else if (sensor_fault && !s->previous_fault)
        d.reason = CAMERA_WAKE_FAULT;
    else if (s->since_wake >= d.interval_cycles)
        d.reason = extended ? CAMERA_WAKE_STABLE : CAMERA_WAKE_NORMAL;
    s->previous_alarm_mask = alarm_mask;
    s->previous_fault = sensor_fault;
    return d;
}
static inline void camera_policy_complete(camera_policy_t *s, bool success, uint32_t normal)
{
    if (success) {
        s->since_wake = 0;
        s->has_requested = true;
    } else {
        s->since_wake = normal;
        s->stable_cycles = 0;
    }
}
static inline const char *camera_wake_reason(camera_wake_reason_t reason)
{
    switch (reason) {
    case CAMERA_WAKE_ALARM: return "alarm_new";
    case CAMERA_WAKE_FAULT: return "sensor_fault";
    case CAMERA_WAKE_NORMAL: return "scheduled_30m";
    case CAMERA_WAKE_STABLE: return "scheduled_120m";
    default: return "none";
    }
}
