cmake_minimum_required(VERSION 3.30)
project(app C CXX)

# Some basics, set accordingly to your needs.
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS "-Wall -Wextra")

if(CMAKE_BUILD_TYPE STREQUAL "Debug")
  set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -g -O0")
else()
  set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3")
endif()

# Your application target.
add_executable(app app.cpp app.hpp)

# Set output name.
set_target_properties(app PROPERTIES OUTPUT_NAME "solarpaper")

# Add Blend2D dependency to your application. The dependency
# should provide everything needed - include paths, libraries,
# compiler flags, and compiler definitions.
target_link_libraries(app blend2d)

# Add Boost dependency to your application.
find_package(Boost REQUIRED COMPONENTS iostreams)

# Find Curl.
find_package(CURL REQUIRED)

if(Boost_FOUND AND CURL_FOUND)
  target_include_directories(app PRIVATE ${Boost_INCLUDE_DIRS} ${CURL_INCLUDE_DIR})
  target_link_libraries(app ${Boost_LIBRARIES} curl)
endif()

# Install the application to the 'bin' directory.
install(TARGETS app DESTINATION bin)