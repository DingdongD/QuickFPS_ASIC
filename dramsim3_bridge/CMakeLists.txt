cmake_minimum_required(VERSION 3.16)
project(quickfps_dramsim3_bridge LANGUAGES CXX)

include(FetchContent)

# Pin the official UMD simulator used by the QuickFPS paper evaluation flow.
# This is deliberately a GitHub link rather than a vendored source copy.
set(THERMAL OFF CACHE BOOL "Disable DRAMsim3 thermal solver" FORCE)
set(CMD_TRACE OFF CACHE BOOL "Disable DRAM command trace" FORCE)
set(ADDR_TRACE OFF CACHE BOOL "Disable DRAM address trace" FORCE)
FetchContent_Declare(
    dramsim3_external
    GIT_REPOSITORY https://github.com/umd-memsys/DRAMsim3.git
    GIT_TAG 29817593b3389f1337235d63cac515024ab8fd6e
    GIT_SHALLOW FALSE
)
FetchContent_MakeAvailable(dramsim3_external)

# The upstream project uses directory-scoped relative include paths.  When it
# is embedded through FetchContent those paths are not propagated reliably to
# all generators, so attach the source directories explicitly to the official
# target without modifying or vendoring its sources.
target_include_directories(
    dramsim3
    PUBLIC
        ${dramsim3_external_SOURCE_DIR}/src
        ${dramsim3_external_SOURCE_DIR}/ext/headers
)
set_target_properties(dramsim3 PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_library(quickfps_dramsim3_bridge SHARED quickfps_dramsim3_bridge.cpp)
target_link_libraries(quickfps_dramsim3_bridge PRIVATE dramsim3)
target_include_directories(
    quickfps_dramsim3_bridge
    PRIVATE
        ${dramsim3_external_SOURCE_DIR}/src
        ${dramsim3_external_SOURCE_DIR}/ext/headers
)
target_compile_features(quickfps_dramsim3_bridge PRIVATE cxx_std_17)
target_compile_options(quickfps_dramsim3_bridge PRIVATE -Wall -Wextra -Wpedantic)
set_target_properties(
    quickfps_dramsim3_bridge PROPERTIES
    OUTPUT_NAME quickfps_dramsim3_bridge
    POSITION_INDEPENDENT_CODE ON
)
