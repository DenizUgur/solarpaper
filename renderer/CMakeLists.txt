cmake_minimum_required(VERSION 3.19)
project(renderer)

# Enable Blend2D static build.
set(BLEND2D_STATIC TRUE)

add_subdirectory(blend2d)
add_subdirectory(app)
