cmake_minimum_required(VERSION 3.16)
project(quickfps_event_sim LANGUAGES CXX)

add_library(quickfps_event_sim SHARED quickfps_event_sim.cpp)
target_compile_features(quickfps_event_sim PRIVATE cxx_std_17)
target_compile_options(
    quickfps_event_sim
    PRIVATE
        -O3
        -Wall
        -Wextra
        -Wpedantic
        -ffp-contract=off
)
set_target_properties(
    quickfps_event_sim
    PROPERTIES
        OUTPUT_NAME quickfps_event_sim
        POSITION_INDEPENDENT_CODE ON
)
