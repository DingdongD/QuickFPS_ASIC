cmake_minimum_required(VERSION 3.16)
project(quickfps_host LANGUAGES CXX)

add_executable(quickfps_preprocess
    quickfps_preprocess.cpp
    rapl_energy.cpp
)

target_compile_features(quickfps_preprocess PRIVATE cxx_std_17)
target_compile_options(quickfps_preprocess PRIVATE
    -Wall
    -Wextra
    -Wpedantic
    -Wconversion
    -Wshadow
)
