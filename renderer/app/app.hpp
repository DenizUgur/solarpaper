#include <map>
#include <ctime>
#include <vector>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <blend2d.h>
#include <algorithm>
#include <sys/stat.h>
#include <filesystem>
#include <curl/curl.h>
#include <boost/iostreams/device/file.hpp>
#include <boost/iostreams/filtering_stream.hpp>
#include <boost/iostreams/filter/gzip.hpp>

using namespace std;
namespace io = boost::iostreams;
namespace fs = std::filesystem;

enum Kind
{
    SUN_AND_PLANETS = 0,
    JOVIAN_SATELLITES = 1,
    SATURIAN_SATELLITES = 2,
    URANIAN_SATELLITES = 3,
    NEPTUNIAN_SATELLITES = 4,
    OTHER_SATELLITES = 5,
    SPACECRAFTS = 6,
    COMETS = 7,
    NEO_ASTEROIDS = 8,
    IMB_ASTEROIDS = 9,
    MBA_ASTEROIDS = 10,

    // Limits
    KIND_MB = 5,       // <=
    KIND_COMET = 7,    // ==
    KIND_ASTEROID = 8, // >=
};

static void read_assert(istream &in, char *buffer, int size)
{
    in.read(buffer, size);
    if (in.gcount() != size)
    {
        cerr << "Error reading file" << endl;
        exit(1);
    }
}

struct Orbit
{
    char spkid[8];
    char name[32];
    Kind kind;
    char neo = 0;
    char pha = 0;
    float distance_ratio;
    char center[8] = "10";
    char phy_bit;
    float radius_ratio;
    unsigned int trail_duration;
    unsigned int size;
    vector<double> jdtdb;
    vector<double> x;
    vector<double> y;

    Orbit operator<<(istream &in)
    {
        read_assert(in, spkid, 8);
        read_assert(in, name, 32);
        read_assert(in, (char *)&kind, sizeof(unsigned int));

        if (kind > 6)
        {
            read_assert(in, &neo, sizeof(char));
            read_assert(in, &pha, sizeof(char));
        }
        if (kind < 6)
            read_assert(in, (char *)&distance_ratio, sizeof(float));
        if (kind < 7)
            read_assert(in, center, 8);

        read_assert(in, &phy_bit, sizeof(char));
        if (phy_bit)
            read_assert(in, (char *)&radius_ratio, sizeof(float));

        read_assert(in, (char *)&trail_duration, sizeof(unsigned int));
        read_assert(in, (char *)&size, sizeof(unsigned int));

        jdtdb.resize(size);
        x.resize(size);
        y.resize(size);

        read_assert(in, (char *)jdtdb.data(), size * sizeof(double));
        read_assert(in, (char *)x.data(), size * sizeof(double));
        read_assert(in, (char *)y.data(), size * sizeof(double));

        return *this;
    };
};

double jd_from_now(unsigned int difference)
{
    // Get the current UTC time
    time_t now = time(0) - difference;
    tm *utm = gmtime(&now);

    int year = 1900 + utm->tm_year;
    int month = 1 + utm->tm_mon;
    int day = utm->tm_mday;
    int hour = utm->tm_hour;
    int minute = utm->tm_min;
    int second = utm->tm_sec;

    int a = (14 - month) / 12;
    int y = year + 4800 - a;
    int m = month + 12 * a - 3;
    double julian = day + (153 * m + 2) / 5 + 365 * y + y / 4 - y / 100 + y / 400 - 32045;
    double fraction = (hour - 12) / 24.0 + minute / 1440.0 + second / 86400.0;
    julian += fraction;

    return julian;
}

static size_t write_data(void *ptr, size_t size, size_t nmemb, void *stream)
{
    size_t written = fwrite(ptr, size, nmemb, (FILE *)stream);
    return written;
}