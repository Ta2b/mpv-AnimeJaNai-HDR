cmake_minimum_required(VERSION 3.16)
project(animejanai_vulkan LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
find_package(Vulkan REQUIRED)
find_package(OpenMP REQUIRED)
set(NCNN_VULKAN ON CACHE BOOL "" FORCE)
set(NCNN_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(NCNN_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(NCNN_BUILD_BENCHMARK OFF CACHE BOOL "" FORCE)
set(NCNN_BUILD_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory("${NCNN_SOURCE}" ncnn)
file(GLOB shaders "${RIFE_SOURCE}/src/*.comp")
foreach(shader ${shaders})
  get_filename_component(name "${shader}" NAME_WE)
  set(header "${CMAKE_CURRENT_BINARY_DIR}/${name}.comp.hex.h")
  add_custom_command(OUTPUT "${header}" COMMAND ${CMAKE_COMMAND}
    -DSHADER_SRC=${shader} -DSHADER_COMP_HEADER=${header}
    -P "${RIFE_SOURCE}/src/generate_shader_comp_header.cmake" DEPENDS "${shader}")
  list(APPEND shader_headers "${header}")
endforeach()
# Recent NCNN Vulkan uses pack1/pack4; the old optional pack8 switch was removed.
file(READ "${RIFE_SOURCE}/src/warp.cpp" warp)
string(REPLACE "opt.use_shader_pack8" "false /* NCNN Vulkan pack8 removed */" warp "${warp}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/warp-compatible.cpp" "${warp}")
# Keep the pinned upstream checkout untouched. The adapter retains the exact
# preprocessing shader and inference graph; only prepared input lifetimes change.
find_program(PATCH_EXECUTABLE patch)
if(NOT PATCH_EXECUTABLE)
  message(FATAL_ERROR "The RIFE input-cache adapter requires the patch utility")
endif()
file(SHA256 "${RIFE_SOURCE}/src/rife.cpp" rife_cpp_sha)
file(SHA256 "${RIFE_SOURCE}/src/rife.h" rife_h_sha)
if(NOT rife_cpp_sha STREQUAL "375beadc59ca08a4f925baa16378f46cfffdf34e752a5392732d1f9d9c78c339"
   OR NOT rife_h_sha STREQUAL "785386d7d63c28f09f74fa1e3c6e0e7ae84e8a7efd15b7f68d238d578aad1298")
  message(FATAL_ERROR "RIFE cache adapter expects upstream a7532fc3f9f8f008cd6eecd6f2ffe2a9698e0cf7")
endif()
set(rife_cache_dir "${CMAKE_CURRENT_BINARY_DIR}/rife-cache")
file(MAKE_DIRECTORY "${rife_cache_dir}")
configure_file("${RIFE_SOURCE}/src/rife.cpp" "${rife_cache_dir}/rife.cpp" COPYONLY)
configure_file("${RIFE_SOURCE}/src/rife.h" "${rife_cache_dir}/rife.h" COPYONLY)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/rife-v4-cache.patch")
execute_process(COMMAND "${PATCH_EXECUTABLE}" --batch --fuzz=0 -p1
  -i "${CMAKE_CURRENT_SOURCE_DIR}/rife-v4-cache.patch"
  WORKING_DIRECTORY "${rife_cache_dir}" RESULT_VARIABLE patch_result)
if(NOT patch_result EQUAL 0)
  message(FATAL_ERROR "Cannot apply the RIFE cache adapter")
endif()
# tiles.cpp of the shared engine: the test that tells a held drawing from a new picture.
add_library(aji_vulkan SHARED aji_vulkan.cpp "${AJI_SOURCE}/src/aji_conf.cpp"
  "${CMAKE_CURRENT_SOURCE_DIR}/../linux-ort/tiles.cpp"
  "${rife_cache_dir}/rife.cpp" "${CMAKE_CURRENT_BINARY_DIR}/warp-compatible.cpp" ${shader_headers})
target_include_directories(aji_vulkan PRIVATE "${rife_cache_dir}"
  "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/../linux-ort" "${AJI_SOURCE}/src" "${RIFE_SOURCE}/src"
  "${CMAKE_CURRENT_BINARY_DIR}")
target_link_libraries(aji_vulkan PRIVATE ncnn Vulkan::Vulkan OpenMP::OpenMP_CXX)
add_executable(animejanai-vulkan-test smoke.cpp)
target_link_libraries(animejanai-vulkan-test PRIVATE aji_vulkan)
set_target_properties(animejanai-vulkan-test PROPERTIES BUILD_RPATH "$ORIGIN")
install(TARGETS aji_vulkan animejanai-vulkan-test DESTINATION .)
