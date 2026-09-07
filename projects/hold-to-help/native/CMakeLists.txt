# SPDX-License-Identifier: GPL-3.0-or-later
cmake_minimum_required(VERSION 3.16)
project(hold-to-help-layer-shell VERSION 0.1.0 LANGUAGES CXX)

include(GNUInstallDirs)
find_package(Qt6 6.10 REQUIRED COMPONENTS Gui)
find_package(LayerShellQt 6.6 REQUIRED)

add_library(hold-to-help-layer-shell SHARED layer_shell_bridge.cpp)
target_compile_features(hold-to-help-layer-shell PRIVATE cxx_std_17)
target_compile_options(hold-to-help-layer-shell PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(hold-to-help-layer-shell PRIVATE Qt6::Gui LayerShellQt::Interface)
set_target_properties(hold-to-help-layer-shell PROPERTIES
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES)
install(TARGETS hold-to-help-layer-shell
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}/hold-to-help)
