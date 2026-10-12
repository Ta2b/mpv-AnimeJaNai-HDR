cmake_minimum_required(VERSION 3.16)
project(animejanai_ort LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
# ORT_ROOT   : an ONNX Runtime package (include/ and lib/). The MIGraphX and OpenVINO execution
#              providers are loaded at run time from the ONNX Runtime build that is installed;
#              a stock package only offers the CPU provider.
# AJI_SOURCE : checkout of the-database/animejanai-inference (configuration parser).
add_library(aji_ort SHARED aji_ort.cpp "${AJI_SOURCE}/src/aji_conf.cpp")
target_include_directories(aji_ort PRIVATE "${ORT_ROOT}/include" "${AJI_SOURCE}/src"
  "${CMAKE_CURRENT_SOURCE_DIR}/../linux-vulkan")
target_link_directories(aji_ort PRIVATE "${ORT_ROOT}/lib")
target_link_libraries(aji_ort PRIVATE onnxruntime)
if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64|amd64")
  target_compile_options(aji_ort PRIVATE -mavx -mf16c)
endif()
add_executable(animejanai-ort-test ort_test.cpp)
target_include_directories(animejanai-ort-test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../linux-vulkan")
target_link_libraries(animejanai-ort-test PRIVATE aji_ort)
if(APPLE)
  # The engine, the test program and ONNX Runtime sit in one folder.
  set_target_properties(aji_ort animejanai-ort-test PROPERTIES BUILD_RPATH "@loader_path;${ORT_ROOT}/lib")
else()
  set_target_properties(aji_ort animejanai-ort-test PROPERTIES BUILD_RPATH "$ORIGIN;${ORT_ROOT}/lib")
endif()
