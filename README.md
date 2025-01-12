# Solar Paper

[![Collect Orbit Data](https://github.com/DenizUgur/solarpaper/actions/workflows/collect.yml/badge.svg)](https://github.com/DenizUgur/solarpaper/actions/workflows/collect.yml) [![Render the Solar System](https://github.com/DenizUgur/solarpaper/actions/workflows/render.yml/badge.svg)](https://github.com/DenizUgur/solarpaper/actions/workflows/render.yml) [![Test](https://github.com/DenizUgur/solarpaper/actions/workflows/test.yml/badge.svg)](https://github.com/DenizUgur/solarpaper/actions/workflows/test.yml)

Solar Paper is a project that aims to illustrate the current state of the solar system as close as possible.

## Latest Render (daily)

:link: Accesible at https://denizugur.github.io/solarpaper/latest/solarpaper.png

![Solar Paper](https://denizugur.github.io/solarpaper/latest/solarpaper.png)

## How it works

List of objects being displayed are given below.

- Sun
- Planets
  - Mercury
  - Venus
  - Earth
  - Mars
- Moons
  - Luna (Earth)
  - Phobos (Mars)
  - Deimos (Mars)
- Spacecrafts
  - SpaceX Roadster
  - OSIRIS-REx
  - Parker Solar Probe
- Asteroids
- Comets

> Note: **Except** for the Sun and moons, everything is displayed accurately to scale.

The project is divided into two parts. The first part is the data collection. The data is collected from [NASA's JPL HORIZONS](https://ssd.jpl.nasa.gov/?horizons) and [NASA's JPL Small-Body Database](https://ssd.jpl.nasa.gov/sbdb.cgi). The collector script processes these data and generates a special file (called SSO) that contains all the data needed to draw the objects.

> Asteroid and comet trajectories are calculated using [Poliastro](https://docs.poliastro.space/en/stable/). Using the data from Small-Body Database, a two-body problem is solved to get the trajectory of the object.

The second part is the drawing. The drawing is done using [Blend2D](https://blend2d.com/). The SSO file is read and the objects are drawn on the screen.

## Installation

This project is available via [Homebrew](https://brew.sh/). You can install it by running the following command:

```bash
brew install denizugur/tap/solarpaper
```

## Building

Since the data acquisition is done over GitHub Actions, you don't need to run the collector script. However, if you want to run it, you can do so by running the following command:

```bash
cd ./collector
pip install poetry
poetry install
poetry run python main.py --update-db
```

This creates a cache folder at `~/.cache/solarpaper` and generates the SSO file at `~/.cache/solarpaper/orbits.sso.gz`.

To run the renderer, you need to install [CMake](https://cmake.org/). The C++ program uses Boost, cURL, and Blend2D. You can install these libraries following the instructions on their websites. After installing the dependencies, you can run the following commands:

```bash
cd ./renderer
mkdir build
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/app/solarpaper
```

This creates a PNG file at `<SP_CACHE_PATH>/output<OUTPUT_SUFFIX>.png`. Check the table below for the environment variables.

| Environment Variable |      Default Value       |                                Description                                 |
| :------------------: | :----------------------: | :------------------------------------------------------------------------: |
|    SP_CACHE_PATH     |   ~/.cache/solarpaper    | This variable sets the location for the output image and SSO file location |
|    OUTPUT_SUFFIX     | current time (`time(0)`) | This variable sets the suffix for the file name before the file extension  |

## License

This project is licensed under the GPL-3 License. See the [LICENSE](LICENSE) file for details.
