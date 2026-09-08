# SPDX-License-Identifier: GPL-3.0-or-later
cmake_minimum_required(VERSION 3.16)
project(superhold-layer-shell VERSION 0.1.0 LANGUAGES CXX)

include(GNUInstallDirs)
find_package(Qt6 6.10 REQUIRED COMPONENTS Gui)
find_package(LayerShellQt 6.6 REQUIRED)

add_library(superhold-layer-shell SHARED layer_shell_bridge.cpp)
target_compile_features(superhold-layer-shell PRIVATE cxx_std_17)
target_compile_options(superhold-layer-shell PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(superhold-layer-shell PRIVATE Qt6::Gui LayerShellQt::Interface)
set_target_properties(superhold-layer-shell PROPERTIES
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES)
install(TARGETS superhold-layer-shell
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}/superhold)
