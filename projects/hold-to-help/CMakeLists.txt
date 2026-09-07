cmake_minimum_required(VERSION 3.20)
project(hold-to-help VERSION 0.1.0 LANGUAGES NONE)
option(BUILD_WAYLAND "Build the layer-shell-qt bridge for Sway/Wayland" ON)
if(BUILD_WAYLAND)
    enable_language(CXX)
else()
    set(CMAKE_INSTALL_LIBDIR "lib" CACHE PATH "Library directory (unused for X11-only builds)")
endif()
include(GNUInstallDirs)
find_package(Python3 3.11 COMPONENTS Interpreter REQUIRED)
if(BUILD_WAYLAND)
    add_subdirectory(native)
endif()
install(PROGRAMS bin/hold-to-help DESTINATION ${CMAKE_INSTALL_BINDIR})
install(DIRECTORY hold_to_help DESTINATION ${CMAKE_INSTALL_DATADIR}/hold-to-help
    FILES_MATCHING PATTERN "*.py" PATTERN "__pycache__" EXCLUDE)
install(FILES data/io.github.spaceghost.HoldToHelp.desktop
    DESTINATION ${CMAKE_INSTALL_DATADIR}/applications)
install(FILES data/hold-to-help.1 DESTINATION ${CMAKE_INSTALL_MANDIR}/man1)
install(FILES LICENSE DESTINATION ${CMAKE_INSTALL_DATADIR}/licenses/hold-to-help)
install(FILES README.md CHANGELOG.md examples/config.toml examples/profiles.json
    DESTINATION ${CMAKE_INSTALL_DOCDIR})
include(CTest)
if(BUILD_TESTING)
    add_test(NAME python-tests
        COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -v)
    set_tests_properties(python-tests PROPERTIES WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        ENVIRONMENT "QT_QPA_PLATFORM=offscreen;PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR};PYTHONDONTWRITEBYTECODE=1")
endif()
