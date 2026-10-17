cmake_minimum_required(VERSION 3.16)
project(animejanai_ort LANGUAGES CXX)
option(AJI_NATIVE_AMD "Build the native MIGraphX + HIP executor (ROCm SDK required)" OFF)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
# ORT_ROOT   : an ONNX Runtime package (include/ and lib/). The MIGraphX and OpenVINO execution
#              providers are loaded at run time from the ONNX Runtime build that is installed;
#              a stock package only offers the CPU provider.
# AJI_SOURCE : checkout of the-database/animejanai-inference (configuration parser).
#
# One library on every platform. The core (aji_ort.cpp) and the ONNX Runtime executor are built
# everywhere; on macOS the Core ML and Metal executors of native/apple are added.
set(ENGINE_SOURCES aji_ort.cpp tiles.cpp ajm.cpp mlpatch.cpp pixel_workers.cpp exec_ort.cpp cpu_activations.cpp exec_ref.cpp onnx_flow.cpp rife_flow_cache.cpp "${AJI_SOURCE}/src/aji_conf.cpp")
if(APPLE)
  enable_language(OBJCXX)
  list(APPEND ENGINE_SOURCES ../apple/exec_coreml.mm ../apple/exec_metal.mm ../apple/nv12_import_probe.mm)
  set_source_files_properties(../apple/exec_coreml.mm ../apple/exec_metal.mm ../apple/nv12_import_probe.mm PROPERTIES
    COMPILE_FLAGS "-fobjc-arc -Wno-deprecated-declarations")
endif()
add_library(aji_ort SHARED ${ENGINE_SOURCES})
target_include_directories(aji_ort PRIVATE "${ORT_ROOT}/include" "${AJI_SOURCE}/src"
  "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/../linux-vulkan")
target_link_directories(aji_ort PRIVATE "${ORT_ROOT}/lib")
find_package(Threads REQUIRED)
target_link_libraries(aji_ort PRIVATE onnxruntime Threads::Threads)
if(AJI_NATIVE_AMD)
  if(APPLE)
    message(FATAL_ERROR "The native AMD executor targets Windows/Linux")
  endif()
  add_library(aji_migraphx_rgb SHARED ${ENGINE_SOURCES})
  target_include_directories(aji_migraphx_rgb PRIVATE "${ORT_ROOT}/include" "${AJI_SOURCE}/src"
    "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/../linux-vulkan")
  target_link_directories(aji_migraphx_rgb PRIVATE "${ORT_ROOT}/lib")
  target_link_libraries(aji_migraphx_rgb PRIVATE onnxruntime Threads::Threads)
  include(../amd/build.cmake)
  aji_add_amd_executor(aji_migraphx_rgb)
  set_target_properties(aji_migraphx_rgb PROPERTIES BUILD_RPATH "$ORIGIN;${ORT_ROOT}/lib;${ROCM_PATH}/lib"
    INSTALL_RPATH "$ORIGIN;/opt/rocm/lib")
endif()
if(APPLE)
  target_link_libraries(aji_ort PRIVATE "-framework Foundation" "-framework CoreML" "-framework CoreVideo"
    "-framework Accelerate" "-framework Metal" "-framework MetalPerformanceShaders"
    "-framework MetalPerformanceShadersGraph")
endif()
if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64|amd64")
  if(MSVC)
    target_compile_options(aji_ort PRIVATE /arch:AVX)
    if(TARGET aji_migraphx_rgb)
      target_compile_options(aji_migraphx_rgb PRIVATE $<$<COMPILE_LANGUAGE:CXX>:/arch:AVX>)
    endif()
  else()
    target_compile_options(aji_ort PRIVATE -mavx -mf16c)
    if(TARGET aji_migraphx_rgb)
      target_compile_options(aji_migraphx_rgb PRIVATE $<$<COMPILE_LANGUAGE:CXX>:-mavx;-mf16c>)
    endif()
  endif()
endif()
add_executable(animejanai-ort-test ort_test.cpp)
target_include_directories(animejanai-ort-test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../linux-vulkan")
target_link_libraries(animejanai-ort-test PRIVATE aji_ort)
# Tile plans, "unchanged" test and Core ML size patch: no model, no GPU.
add_executable(animejanai-tiles-test tiles_test.cpp tiles.cpp ajm.cpp mlpatch.cpp)
target_include_directories(animejanai-tiles-test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
add_executable(animejanai-pixel-workers-test pixel_workers_test.cpp pixel_workers.cpp)
target_link_libraries(animejanai-pixel-workers-test PRIVATE Threads::Threads)
if(APPLE)
  # The engine, the test program and ONNX Runtime sit in one folder.
  set_target_properties(aji_ort animejanai-ort-test PROPERTIES BUILD_RPATH "@loader_path;${ORT_ROOT}/lib")
else()
  set_target_properties(aji_ort animejanai-ort-test PROPERTIES BUILD_RPATH "$ORIGIN;${ORT_ROOT}/lib")
endif()
