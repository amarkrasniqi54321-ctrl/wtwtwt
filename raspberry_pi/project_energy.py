"""Scenario projection using only historical Luka energy coefficients."""
import argparse
import json

HOURS = 144
BASELINE_BACKGROUND_WH = 262.86
BASELINE_SENSOR_J = 3.79 * 3600 / 259200
BASELINE_CAMERA_J = 7.03 * 3600 / 8640
OPTIMIZED_BACKGROUND_WH = 192.86
OPTIMIZED_SENSOR_J = 0.092838
OPTIMIZED_PI_BLOCK_J = 55.848094
PI_BLOCK_SECONDS = 34.72
OPTIMIZED_PERIOD_SECONDS = 20 + 0.334625

def project(pi_blocks, sensor_events=25493):
    if pi_blocks < 0 or sensor_events < 0:
        raise ValueError("counts must be non-negative")
    baseline = BASELINE_BACKGROUND_WH + (25920 * BASELINE_SENSOR_J + 288 * BASELINE_CAMERA_J) / 3600
    # Pi block energy already includes overlapping sensing; remove an estimated
    # number of those events from the stand-alone sensing term.
    overlap = min(sensor_events, pi_blocks * PI_BLOCK_SECONDS / OPTIMIZED_PERIOD_SECONDS)
    optimized = OPTIMIZED_BACKGROUND_WH + ((sensor_events - overlap) * OPTIMIZED_SENSOR_J + pi_blocks * OPTIMIZED_PI_BLOCK_J) / 3600
    return {"type": "model_projection_not_measurement", "hours": HOURS,
            "baseline_wh": baseline, "optimized_wh": optimized,
            "pi_activity_blocks": pi_blocks, "sensor_events": sensor_events,
            "estimated_overlapping_sensor_events": overlap,
            "saving_wh": baseline - optimized,
            "saving_percent": 100 * (baseline - optimized) / baseline}

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pi-blocks", type=int, required=True)
    p.add_argument("--sensor-events", type=int, default=25493)
    a = p.parse_args()
    print(json.dumps(project(a.pi_blocks, a.sensor_events), indent=2))
