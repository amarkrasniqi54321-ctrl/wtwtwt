# Smart Plant Monitoring

**Current evaluation:** [Mathematical calculations, original measurement inventory, design, implementation and adaptive comparison](docs/MATHEMATICAL_CALCULATIONS.md). [Reproduction script and all numerical outputs](evaluation/).

**Start here: [Complete project handoff](docs/HANDOFF.md).**

Final active BASELINE and OPTIMIZED ESP32/Pi implementation, scripts, tests and technical documentation. Both firmware modes share one source tree with separate build profiles.

- [ESP32 firmware](esp32/)
- [Raspberry Pi application and running scripts](raspberry_pi/)
- [Lab runbook](docs/LAB_RUNBOOK.md)
- [Hardware wiring](esp32/docs/WIRING.md)
- [Adaptive specification](docs/ADAPTIVE_SCENARIO.md)
- [Energy model](docs/ENERGY_RESULTS.md)

Prior validation of the runtime implementation passed 40 tests and both firmware builds. Physical validation remains pending. Historical energy coefficients are used for conditional projections, not new measured results. Third-party model/image licenses and attribution are included in raspberry_pi/leaf_classifier/.
