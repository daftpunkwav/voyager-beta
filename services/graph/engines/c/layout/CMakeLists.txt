cmake_minimum_required(VERSION 3.16)
project(graph_layout C)

set(CMAKE_C_STANDARD 11)

add_library(graph_layout SHARED layout3d.c)
target_include_directories(graph_layout PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
if(WIN32)
  set_target_properties(graph_layout PROPERTIES PREFIX "" OUTPUT_NAME "graph_layout")
endif()

# 布局加速 CLI；勿与 graph_engine_core 的 MCP 索引引擎 graph-engine 混淆
add_executable(graph-layout-cli layout3d.c)
target_compile_definitions(graph-layout-cli PRIVATE LAYOUT_CLI=1)

install(TARGETS graph_layout graph-layout-cli
  RUNTIME DESTINATION bin
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
)
