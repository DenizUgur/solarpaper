#include "app.hpp"

// Global variables
int width = 3840;
int height = 2160;
float zoom = 1.1;
float scale[2] = {16 * (1 / zoom), 9 * (1 / zoom)}; // x and y, in AU
float moon_offset[2] = {30 * zoom, 50 * zoom};      // min and max, in pixels
map<string, Orbit> major_body_orbits;

string cache_path;
string sso_file_name;
string download_url = "https://denizugur.dev/solarpaper/orbits.sso.gz";

// Download the orbits.sso.gz data if needed
int download_data()
{
    CURL *curl_handle;
    FILE *sso_fp;

    cout << "Downloading the data file..." << endl;

    curl_global_init(CURL_GLOBAL_ALL);

    /* init the curl session */
    curl_handle = curl_easy_init();

    /* set URL to get here */
    curl_easy_setopt(curl_handle, CURLOPT_URL, download_url.c_str());

    /* Switch on full protocol/debug output while testing */
    curl_easy_setopt(curl_handle, CURLOPT_VERBOSE, 0L);

    /* disable progress meter, set to 0L to enable it */
    curl_easy_setopt(curl_handle, CURLOPT_NOPROGRESS, 1L);

    /* send all data to this function  */
    auto write_data = [](void *buffer, size_t size, size_t nmemb, void *userp) -> size_t
    {
        return fwrite(buffer, size, nmemb, (FILE *)userp);
    };

    curl_easy_setopt(curl_handle, CURLOPT_WRITEFUNCTION, write_data);

    /* open the file */
    sso_fp = fopen((cache_path + sso_file_name).c_str(), "wb");
    if (sso_fp)
    {
        /* write the page body to this file handle */
        curl_easy_setopt(curl_handle, CURLOPT_WRITEDATA, sso_fp);

        /* get it! */
        CURLcode ret = curl_easy_perform(curl_handle);

        if (ret != CURLE_OK)
        {
            cerr << "Failed to download data file: " << curl_easy_strerror(ret) << endl;
            return 1;
        }

        /* close the header file */
        fclose(sso_fp);
    }
    else
    {
        cerr << "Failed to open file for writing: " << cache_path + sso_file_name << endl;
        return 1;
    }

    /* cleanup curl stuff */
    curl_easy_cleanup(curl_handle);

    curl_global_cleanup();

    return 0;
}

// Scale input coordinates to image coordinates
int coord_to_point(float x, float y, BLPoint &p)
{
    int sx = x * (width / scale[0]) + (width / 2);
    int sy = height - (y * (height / scale[1]) + (height / 2));

    p = BLPoint(sx, sy);
    return sx < 0 || sx > width || sy < 0 || sy > height;
}

void draw_orbit(Orbit orbit, BLContext ctx, double jd_now)
{
    // If the orbit is for a moon, add the major body orbit
    if (orbit.kind <= KIND_MB && strcmp(orbit.center, "10") != 0)
    {
        // Get the major body orbit
        auto major_body = major_body_orbits.find(orbit.center);
        if (major_body == major_body_orbits.end())
        {
            cerr << "Major body " << orbit.center << " not found" << endl;
            return;
        }

        // Skip non major sattellites
        if (!orbit.phy_bit && orbit.radius_ratio < 0.1)
            return;

        // calculate max of x and y
        double max_x = 0;
        double max_y = 0;
        for (unsigned int i = 0; i < orbit.size; i++)
        {
            if (orbit.x[i] > max_x)
                max_x = abs(orbit.x[i]);
            if (orbit.y[i] > max_y)
                max_y = abs(orbit.y[i]);
        }

        // calculate the scale ratio
        double normalized_offset = moon_offset[0] + (moon_offset[1] - moon_offset[0]) * orbit.distance_ratio;
        double ratio_xy[2] = {
            (normalized_offset / (width / scale[0])) / max_x,
            (normalized_offset / (height / scale[1])) / max_y,
        };

        // Find the last point of the major body given current jd
        unsigned int major_body_last_point = 0;
        for (unsigned int i = 0; i < major_body->second.size; i++)
        {
            if (major_body->second.jdtdb[i] > jd_now)
                break;
            major_body_last_point = i;
        }

        // calculate the offset
        for (unsigned int i = 0; i < orbit.size; i++)
        {
            orbit.x[i] *= ratio_xy[0];
            orbit.y[i] *= ratio_xy[1];
            orbit.x[i] += major_body->second.x[major_body_last_point];
            orbit.y[i] += major_body->second.y[major_body_last_point];
        }
    }

    // Draw the orbit
    BLPath path;
    BLPoint p_first;
    BLPoint p_last;
    bool p_last_out_of_bounds = false;

    unsigned int p_first_index = 0;
    unsigned int p_last_index = 0;

    double trail_start = jd_from_now(orbit.trail_duration);
    double trail_end = jd_now;

    // Find the first point including the fraction of the orbit
    for (p_first_index = 0; p_first_index < orbit.size; p_first_index++)
    {
        // Loop until we find the point after the trail start
        if (orbit.jdtdb[p_first_index] >= trail_start)
        {
            if (p_first_index == 0)
            {
                BLPoint p;
                coord_to_point(orbit.x[0], orbit.y[0], p);
                path.moveTo(p);
                p_first = p;
                break;
            }

            // Calculate the fraction of the orbit to draw
            double fraction = (trail_start - orbit.jdtdb[p_first_index - 1]) / (orbit.jdtdb[p_first_index] - orbit.jdtdb[p_first_index - 1]);

            // Calculate the first point to draw
            BLPoint p_prev, p, p_now;
            coord_to_point(orbit.x[p_first_index - 1], orbit.y[p_first_index - 1], p_prev);
            coord_to_point(orbit.x[p_first_index], orbit.y[p_first_index], p_now);

            if (fraction >= 0)
                p = BLPoint(p_prev.x + (p_now.x - p_prev.x) * fraction, p_prev.y + (p_now.y - p_prev.y) * fraction);
            else
                p = p_prev;

            // If the first point is out of bounds, continue until we find a point in bounds
            bool p_prev_out_of_bounds = p_prev.x < 0 || p_prev.x > width || p_prev.y < 0 || p_prev.y > height;
            bool p_out_of_bounds = p.x < 0 || p.x > width || p.y < 0 || p.y > height;
            bool p_now_out_of_bounds = p_now.x < 0 || p_now.x > width || p_now.y < 0 || p_now.y > height;

            // If we are coming from inside but going out, and the next point is out, moveTo p
            if (p_out_of_bounds && !p_prev_out_of_bounds && p_now_out_of_bounds)
            {
                path.moveTo(p);
                p_first = p;
                break;
            }

            // If we are coming from outside but going in, and the next point is out, moveTo p
            if (p_out_of_bounds && p_prev_out_of_bounds && !p_now_out_of_bounds)
            {
                path.moveTo(p);
                p_first = p;
                break;
            }

            // If p oob but p_now not OR p not oob, moveTo p
            if (!p_out_of_bounds)
            {
                path.moveTo(p);
                p_first = p;
                break;
            }
        }
    }

    // If first point is not found, return
    if (p_first.x == 0 && p_first.y == 0)
        return;

    // Find the last point including the fraction of the orbit, if kind is not IMB or MBA draw the whole orbit
    for (p_last_index = p_first_index; p_last_index < orbit.size; p_last_index++)
    {
        // Loop until we find the point after the trail end
        if (orbit.jdtdb[p_last_index] >= trail_end)
        {
            // Calculate the fraction of the orbit to draw
            double fraction = (trail_end - orbit.jdtdb[p_last_index - 1]) / (orbit.jdtdb[p_last_index] - orbit.jdtdb[p_last_index - 1]);

            // Calculate the last point to draw
            BLPoint p_prev, p, p_now;
            coord_to_point(orbit.x[p_last_index - 1], orbit.y[p_last_index - 1], p_prev);
            coord_to_point(orbit.x[p_last_index], orbit.y[p_last_index], p_now);

            if (fraction >= 0)
                p = BLPoint(p_prev.x + (p_now.x - p_prev.x) * fraction, p_prev.y + (p_now.y - p_prev.y) * fraction);
            else
                p = p_prev;

            // If the last point is out of bounds
            p_last_out_of_bounds = p.x < 0 || p.x > width || p.y < 0 || p.y > height;
            p_last = p;

            if (orbit.kind < IMB_ASTEROIDS)
                path.lineTo(p);
            break;
        }

        coord_to_point(orbit.x[p_last_index], orbit.y[p_last_index], p_last);

        if (orbit.kind < IMB_ASTEROIDS)
            path.lineTo(p_last);
    }

    // Set the color of the orbit
    BLRgba32 color = BLRgba32(0x7FFFFFFF);
    if (strcmp(orbit.spkid, "199") == 0)
        color = BLRgba32(0xFF463734);
    else if (strcmp(orbit.spkid, "299") == 0)
        color = BLRgba32(0xFF762F1F);
    else if (strcmp(orbit.spkid, "399") == 0 || strcmp(orbit.center, "399") == 0)
        color = BLRgba32(0xFF495E2B);
    else if (strcmp(orbit.spkid, "499") == 0 || strcmp(orbit.center, "499") == 0)
        color = BLRgba32(0xFF932C0C);
    else if (strcmp(orbit.spkid, "599") == 0 || strcmp(orbit.center, "599") == 0)
        color = BLRgba32(0xFFBA946D);
    else if (strcmp(orbit.spkid, "699") == 0 || strcmp(orbit.center, "699") == 0)
        color = BLRgba32(0xFF8C5197);
    else if (strcmp(orbit.spkid, "799") == 0 || strcmp(orbit.center, "799") == 0)
        color = BLRgba32(0xFF4D4D4D);
    else if (strcmp(orbit.spkid, "899") == 0 || strcmp(orbit.center, "899") == 0)
        color = BLRgba32(0xFF9D9D9D);

    if (orbit.kind == SPACECRAFTS)
        color = BLRgba32(0xFFFFBF00);
    else if (orbit.kind == KIND_COMET)
        color = BLRgba32(0x55AAC8AA);
    else if (orbit.kind == NEO_ASTEROIDS)
        color = BLRgba32(0x7F88412D);
    else if (orbit.kind == IMB_ASTEROIDS)
        color = BLRgba32(0xFF659ABE);
    else if (orbit.kind == MBA_ASTEROIDS)
        color = BLRgba32(0xFF1A4969);

    BLRgba32 color_orbit = color;
    color_orbit.setA(orbit.kind < 6 ? 0xFF : color.a() * 0.5);

    BLCompOp comp_op = BL_COMP_OP_DST_OVER;
    if (orbit.kind <= KIND_MB)
        comp_op = BL_COMP_OP_SRC_OVER;

    ctx.setCompOp(comp_op);
    ctx.setStrokeWidth((orbit.kind <= KIND_MB ? (orbit.kind == SUN_AND_PLANETS ? 3 : 2) : 1.5) * zoom);
    ctx.setStrokeStartCap(BL_STROKE_CAP_ROUND);
    ctx.setStrokeEndCap(BL_STROKE_CAP_BUTT);

    // Add a gradient to the comet and NEO orbits
    if (orbit.kind == KIND_COMET || orbit.kind == NEO_ASTEROIDS)
    {
        BLRgba32 color_orbit_transparent = color_orbit;
        color_orbit_transparent.setA(0x00);

        BLGradient linear(BLLinearGradientValues(p_first.x, p_first.y, p_last.x, p_last.y));
        linear.addStop(0.0, color_orbit_transparent);
        linear.addStop(0.75, color_orbit);
        linear.addStop(1.0, color_orbit);
        ctx.setStrokeStyle(linear);
    }
    else
        ctx.setStrokeStyle(color_orbit);

    ctx.strokePath(path);

    // Draw end point if last point is visible
    if (p_last_out_of_bounds)
        return;

    ctx.setCompOp(comp_op);
    ctx.setFillStyle(color);
    if (orbit.kind <= KIND_MB)
    {
        // Planets and sattelites have one circle
        float size = strcmp(orbit.center, "10") == 0 ? 6 : 4;
        size *= (orbit.phy_bit ? 1 + (orbit.radius_ratio) : 0.2);
        size *= zoom;
        ctx.fillCircle(p_last.x, p_last.y, size);
    }
    else
    {
        float size = 5 * zoom;

        // IMB and MBA asteroids have one circle
        if (orbit.kind >= IMB_ASTEROIDS)
        {
            ctx.fillCircle(p_last.x, p_last.y, size / 2);
            return;
        }

        ctx.setStrokeWidth(size);
        ctx.setStrokeStyle(color);

        // draw line over last n points for all other types
        int n = 4;
        BLPoint p;
        BLPath path;

        path.moveTo(p_last);
        for (unsigned int i = p_last_index - 1; i > p_last_index - n && i >= 0; i--)
        {
            if (coord_to_point(orbit.x[i], orbit.y[i], p))
                continue;

            path.lineTo(p);
        }
        ctx.strokePath(path);
    }
}

int main() // int argc, char *argv[]
{
    // Create the image
    BLImage img(width, height, BL_FORMAT_PRGB32);

    // Initialize Blend2D library.
    BLContextCreateInfo info = {};
    info.threadCount = 4;

    // Create the context
    BLContext ctx;
    BLResult result = ctx.begin(img, info);

    if (result != BL_SUCCESS)
    {
        cerr << "Failed to create context" << endl;
        return 1;
    }

    // Clear the image.
    ctx.setCompOp(BL_COMP_OP_SRC_COPY);
    ctx.clearAll();

    // Sun
    BLPoint sun_p;
    coord_to_point(0, 0, sun_p);

    BLCircle sun(sun_p.x, sun_p.y, 30);
    ctx.setCompOp(BL_COMP_OP_SRC_OVER);

    BLGradient radial(
        BLRadialGradientValues(sun_p.x, sun_p.y, sun_p.x, sun_p.y, 30));
    radial.addStop(0.0, BLRgba32(0xFF7F7145));
    radial.addStop(0.5, BLRgba32(0xFF7F7145));
    radial.addStop(1.0, BLRgba32(0xFF0E1020));

    ctx.setFillStyle(radial);
    ctx.fillCircle(sun);

    // Initialize cache path
    sso_file_name = "/orbits.sso.gz";
    if (getenv("SP_CACHE_PATH") != NULL)
        cache_path = getenv("SP_CACHE_PATH");
    else
    {
        cache_path = getenv("HOME");
        cache_path += "/.cache/solarpaper/";
    }

    // Get absolute path
    cache_path = realpath(cache_path.c_str(), NULL);

    // Check if the cache path exists
    struct stat buf;
    if (stat(cache_path.c_str(), &buf) != 0)
    {
        // Create the cache path
        if (mkdir(cache_path.c_str(), 0755) != 0)
        {
            cerr << "Failed to create cache path" << endl;
            return 1;
        }
    }

download_data:
    // Check if the orbits file exists
    if (stat((cache_path + sso_file_name).c_str(), &buf) != 0)
    {
        int ret = download_data();
        if (ret != 0)
            return 1;
    }

    // Read the orbits file
    io::filtering_istream in;
    in.push(io::gzip_decompressor());
    in.push(io::file_source(cache_path + sso_file_name, ios::binary));

    // Read the header
    double jd_valid_until;
    double jd_now = jd_from_now(0);
    in.read((char *)&jd_valid_until, sizeof(double));

    // Check if the file is valid
    if (jd_now > jd_valid_until)
    {
        cerr << "The orbits file is not valid anymore, deleting..." << endl;
        remove((cache_path + sso_file_name).c_str());
        goto download_data;
    }

    while (!in.eof())
    {
        if (in.peek() == EOF)
            break;

        Orbit orbit;
        orbit << in;

        // Add the orbit to the map
        if (orbit.kind <= KIND_MB)
            major_body_orbits.insert(pair<string, Orbit>(orbit.spkid, orbit));

        // Draw the orbits
        draw_orbit(orbit, ctx, jd_now);
    }

    // Draw background
    ctx.setCompOp(BL_COMP_OP_DST_OVER);
    ctx.setFillStyle(BLRgba32(0xFF040404));
    ctx.fillAll();

    // Detach the rendering context from `img`.
    ctx.end();

    // Save the image to a PNG file.
    ostringstream fn;
    fn << cache_path << "/output";

    if (getenv("OUTPUT_SUFFIX") != NULL)
        fn << getenv("OUTPUT_SUFFIX");
    else
        fn << "-" << time(0);

    fn << ".png";
    img.writeToFile(fn.str().c_str());

    return 0;
}