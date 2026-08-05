cmake_minimum_required(VERSION 3.16)
project(quickfps_bucket_scheduler LANGUAGES CXX)

add_library(quickfps_bucket_scheduler SHARED quickfps_bucket_scheduler.cpp)
target_compile_features(quickfps_bucket_scheduler PRIVATE cxx_std_17)
target_compile_options(
    quickfps_bucket_scheduler
    PRIVATE
        -Wall
        -Wextra
        -Wpedantic
        -Werror
        -ffp-contract=off
)
set_target_properties(
    quickfps_bucket_scheduler
    PROPERTIES
        OUTPUT_NAME quickfps_bucket_scheduler
        POSITION_INDEPENDENT_CODE ON
)
