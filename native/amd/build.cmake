# Native AMD execution is optional: ordinary Apple/ORT builds do not acquire
# ROCm dependencies. Both platforms use the same graph and HIP kernels.
set(AJI_AMD_SOURCE_DIR "${CMAKE_CURRENT_LIST_DIR}")
set(AJI_AMD_ARCHITECTURES "gfx1201" CACHE STRING "HIP GPU architectures; RX 9070 XT = gfx1201")
if(NOT WIN32)
  set(CMAKE_HIP_ARCHITECTURES "${AJI_AMD_ARCHITECTURES}")
  # Compiler variables must be established in directory scope, not a function.
  enable_language(HIP)
endif()
function(aji_add_amd_executor target)
  if(NOT WIN32)
    set_target_properties(${target} PROPERTIES HIP_ARCHITECTURES "${AJI_AMD_ARCHITECTURES}")
  endif()
  find_package(hip CONFIG REQUIRED)
  find_path(AJI_MIGRAPHX_INCLUDE migraphx/migraphx.h
    HINTS "${MIGRAPHX_ROOT}/include" "${ROCM_PATH}/include" /opt/rocm/include REQUIRED)
  find_library(AJI_MIGRAPHX_C_LIBRARY NAMES migraphx_c
    HINTS "${MIGRAPHX_ROOT}/lib" "${ROCM_PATH}/lib" /opt/rocm/lib REQUIRED)
  target_sources(${target} PRIVATE "${AJI_AMD_SOURCE_DIR}/exec_migraphx.cpp")
  target_include_directories(${target} PRIVATE "${AJI_MIGRAPHX_INCLUDE}" "${AJI_AMD_SOURCE_DIR}")
  target_compile_definitions(${target} PRIVATE AJI_NATIVE_AMD=1 __HIP_PLATFORM_AMD__=1)
  target_link_libraries(${target} PRIVATE "${AJI_MIGRAPHX_C_LIBRARY}" hip::host)
  # CMake's HIP language is not supported with every Windows generator. The
  # HIP SDK compiler produces a COFF object that MSVC can link directly.
  if(WIN32)
    find_program(AJI_HIP_COMPILER NAMES clang++ amdclang++
      HINTS "${ROCM_PATH}/bin" "${ROCM_PATH}/lib/llvm/bin"
            "$ENV{HIP_PATH}/bin" "$ENV{HIP_PATH}/lib/llvm/bin" REQUIRED NO_DEFAULT_PATH)
    set(arch_flags)
    foreach(arch IN LISTS AJI_AMD_ARCHITECTURES)
      list(APPEND arch_flags "--offload-arch=${arch}")
    endforeach()
    set(obj "${CMAKE_CURRENT_BINARY_DIR}/aji_hip_kernels.obj")
    add_custom_command(OUTPUT "${obj}"
      COMMAND "${AJI_HIP_COMPILER}" -x hip -std=c++17 -O3 -ffp-contract=off
        ${arch_flags} --hip-path=${ROCM_PATH} --rocm-path=${ROCM_PATH}
        -D__HIP_PLATFORM_AMD__=1 -I "${ROCM_PATH}/include"
        -c "${AJI_AMD_SOURCE_DIR}/hip_kernels.hip" -o "${obj}"
      DEPENDS "${AJI_AMD_SOURCE_DIR}/hip_kernels.hip" "${AJI_AMD_SOURCE_DIR}/hip_kernels.h"
      VERBATIM)
    set_source_files_properties("${obj}" PROPERTIES EXTERNAL_OBJECT TRUE GENERATED TRUE)
    target_sources(${target} PRIVATE "${obj}")
  else()
    add_library(aji_hip_kernels OBJECT "${AJI_AMD_SOURCE_DIR}/hip_kernels.hip")
    set_target_properties(aji_hip_kernels PROPERTIES HIP_ARCHITECTURES "${AJI_AMD_ARCHITECTURES}"
      POSITION_INDEPENDENT_CODE ON HIP_STANDARD 17)
    target_compile_options(aji_hip_kernels PRIVATE -O3 -ffp-contract=off)
    target_sources(${target} PRIVATE $<TARGET_OBJECTS:aji_hip_kernels>)
  endif()
endfunction()
