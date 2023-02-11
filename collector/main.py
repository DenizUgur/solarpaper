import os
import gzip
import random
import argparse
import matplotlib.pyplot as plt
from horizons import Database, OrbitElement

if __name__ == "__main__":
    # parse args
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--invalidate-cache",
        action="store_true",
        help="Invalidate the cache and download all data again",
    )
    parser.add_argument(
        "--update-db",
        action="store_true",
        help="Update the database with the latest data",
    )
    parser.add_argument(
        "--exclude-indexes",
        nargs="+",
        type=int,
        default=[],
        help="Exclude the indexes from the database",
    )
    parser.add_argument(
        "--cache-path",
        type=str,
        default=os.getenv("HOME") + "/.cache/solarpaper",
        help="Path to the cache directory",
    )
    args = parser.parse_args()

    # Initialize SSO file location
    if not os.path.exists(args.cache_path):
        os.makedirs(args.cache_path, 0o755, exist_ok=True)
    sso_path = args.cache_path + "/orbits.sso.gz"

    # Update the database
    if args.update_db:
        # Initialize the database
        db = Database(args.cache_path, invalidate_cache=args.invalidate_cache)
        # Get the list of objects
        objects = db.list_objects()
        # Remove excluded objects
        for i in sorted(args.exclude_indexes, reverse=True):
            del objects[i]

        # Update the objects
        db.update(objects)
        # Exit
        exit(0)

    # Read the database
    orbits: OrbitElement = []
    with gzip.open(sso_path, "rb") as fp:
        while True:
            try:
                orbits.append(OrbitElement.decode(fp))
            except EOFError:
                break

    # Print the number of orbits
    print(f"Number of orbits: {len(orbits)}")

    # Generate random colors
    color = [
        "#" + "".join([random.choice("0123456789ABCDEF") for _ in range(6)])
        for _ in range(len(orbits))
    ]

    # Plot the orbit
    plt.style.use("dark_background")

    for i, orbit in enumerate(orbits):
        # Connect to the center
        if hasattr(orbit, "center") and orbit.center != "10":
            ci = -1
            for j, o in enumerate(orbits):
                if o.spkid == orbit.center:
                    ci = j
                    break
            orbit.X += orbits[ci].X[-1]
            orbit.Y += orbits[ci].Y[-1]

        # Orbit
        plt.plot(orbit.X, orbit.Y, c=color[i])

        # Last position
        plt.scatter(orbit.X[-1], orbit.Y[-1], c=color[i])

    # Sun
    plt.plot(0, 0, "yo", label="Sun", markersize=15)

    plt.axis("equal")
    plt.legend(loc="upper right", fontsize=12)
    plt.tight_layout()
    plt.show()
