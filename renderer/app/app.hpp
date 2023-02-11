#include <map>
#include <ctime>
#include <vector>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <blend2d.h>
#include <algorithm>
#include <sys/stat.h>
#include <curl/curl.h>
#include <boost/iostreams/device/file.hpp>
#include <boost/iostreams/filtering_stream.hpp>
#include <boost/iostreams/filter/gzip.hpp>

using namespace std;
namespace io = boost::iostreams;

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
        in.read(spkid, 8);
        in.read(name, 32);
        in.read((char *)&kind, 1);

        if (kind > 6)
        {
            in.read(&neo, 1);
            in.read(&pha, 1);
        }
        if (kind < 6)
            in.read((char *)&distance_ratio, 4);
        if (kind < 7)
            in.read(center, 8);

        in.read(&phy_bit, 1);
        if (phy_bit)
            in.read((char *)&radius_ratio, 4);

        in.read((char *)&trail_duration, 4);
        in.read((char *)&size, 4);

        jdtdb.resize(size);
        x.resize(size);
        y.resize(size);

        in.read((char *)jdtdb.data(), size * 8);
        in.read((char *)x.data(), size * 8);
        in.read((char *)y.data(), size * 8);

        return *this;
    };
};

double jd_from_now(unsigned int difference)
{
    time_t now = time(0) - difference;
    tm *ltm = localtime(&now);
    int year = 1900 + ltm->tm_year;
    int month = 1 + ltm->tm_mon;
    int day = ltm->tm_mday;
    int hour = ltm->tm_hour;
    int minute = ltm->tm_min;
    int second = ltm->tm_sec;

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