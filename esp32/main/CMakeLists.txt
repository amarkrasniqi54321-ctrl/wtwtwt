idf_component_register(
    SRCS
        "main.c"
        "dht11.c"
        "measurement_output.c"
        "raspberry_pi_wake.c"
    INCLUDE_DIRS "."
    PRIV_REQUIRES
        buzzer
        soil_moisture
        monitoring
        esp_driver_gpio
        esp_driver_uart
        esp_pm
        esp_hw_support
        esp_system
        esp_timer
)

# Embed the editable text rules into flash. At this project stage, changing
# configuration.txt requires rebuilding and flashing the ESP32 firmware.
target_add_binary_data(
    ${COMPONENT_LIB}
    "${PROJECT_DIR}/config/configuration.txt"
    TEXT
    RENAME_TO "smart_plant_rules"
)
