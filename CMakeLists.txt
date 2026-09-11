cmake_minimum_required(VERSION 3.18)
project(dosimeter_core LANGUAGES CXX)

# Set C++20 standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Set OpenCV directory to the found location (we found it in C:/opencv/build/x64/vc16/lib)
set(OpenCV_DIR "C:/opencv/build/x64/vc16/lib" CACHE PATH "OpenCV directory")

# Find OpenCV components
find_package(OpenCV REQUIRED COMPONENTS core imgproc objdetect calib3d)
message(STATUS "OpenCV found: ${OpenCV_VERSION}")

# FetchContent for Eigen3
include(FetchContent)
FetchContent_Declare(
  eigen
  GIT_REPOSITORY https://gitlab.com/libeigen/eigen.git
  GIT_TAG 3.4.0
)
# For Windows, we might need to avoid building tests and examples
set(EIGEN_BUILD_TESTS OFF CACHE INTERNAL "" FORCE)
set(EIGEN_BUILD_PKGCONFIG OFF CACHE INTERNAL "" FORCE)
FetchContent_MakeAvailable(eigen)

# Optimization flags for release
if(CMAKE_BUILD_TYPE STREQUAL "" OR CMAKE_BUILD_TYPE STREQUAL "Release")
  set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -ffast-math -fvisibility=hidden")
endif()

# Include directories
include_directories(${OpenCV_INCLUDE_DIRS} ${Eigen3_INCLUDE_DIRS})

# Library sources
set(LIB_SOURCES
    cpp/Rectifier.cpp
    cpp/DosimeterTypes.hpp
    cpp/ColorimetryUtils.hpp
    cpp/ColorimetryUtils.cpp
    cpp/BadgeEngine.hpp
    cpp/BadgeEngine.cpp
)
if(ANDROID)
    list(APPEND LIB_SOURCES cpp/JNIBridge.cpp)
endif()

# Create shared library
add_library(dosimeter_core SHARED ${LIB_SOURCES})
set_property(TARGET dosimeter_core PROPERTY WINDOWS_EXPORT_ALL_SYMBOLS ON)

# Link libraries
target_link_libraries(dosimeter_core
    ${OpenCV_LIBS}
    Eigen3::Eigen
)

# Set library properties
set_target_properties(dosimeter_core PROPERTIES
    PREFIX "lib"
    VERSION 1.0.0
    SOVERSION 1
)

# Now create the test executable
add_executable(test_engine
  test_engine.cpp
)
target_include_directories(test_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/cpp)

target_link_libraries(test_engine
  dosimeter_core
  ${OpenCV_LIBS}
  Eigen3::Eigen
)

# Post-build step to copy OpenCV DLLs
if(WIN32)
  add_custom_command(TARGET test_engine POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
      "${OpenCV_DIR}/../bin"
      $<TARGET_FILE_DIR:test_engine>
  )
endif()

# Install rules (optional)
install(TARGETS dosimeter_core
        LIBRARY DESTINATION lib
        ARCHIVE DESTINATION lib
)
