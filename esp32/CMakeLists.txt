cmake_minimum_required(VERSION 3.16)

# This firmware stage contains only the three local devices and rule engine.
# Wi-Fi, Raspberry Pi and camera functionality are intentionally excluded.
set(COMPONENTS main buzzer soil_moisture monitoring)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(pecd_smart_plant)
