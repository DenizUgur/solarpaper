import os
import gzip
import json
import struct
import pickle
import requests
import numpy as np
import dateutil.parser
import concurrent.futures
from datetime import datetime, timedelta

from astropy.time import Time
from astropy import units as u
from poliastro.util import time_range
from poliastro.bodies import Sun
from poliastro.twobody import Orbit
from poliastro.twobody.sampling import EpochsArray
from poliastro.core.angles import D_to_nu, E_to_nu, F_to_nu, M_to_D, M_to_E, M_to_F

from config import *


class OrbitElement:
    """
    header
        jd_valid_until double
    format
        spkid 8 bytes
        name 32 bytes
        kind char
        kind > 6
            neo bit
            pha bit
        kind < 6
            distance_r float
        kind < 7
            center 8 bytes
        phy_bit bit
        phy_bit == 1
            radius_r float
        tr_dur uint
        size  uint
        JDTDB size * double
        X     size * double
        Y     size * double
    """

    def __init__(self, metadata):
        self.__dict__.update(metadata)

    @staticmethod
    def from_text(metadata, text):
        orbit = OrbitElement(metadata)

        data = []
        flag = False
        for line in text.split("\n"):
            if "$$SOE" in line:
                flag = True
                continue

            if "$$EOE" in line:
                break

            if flag:
                data.append(line.split(",")[:-1])

        data = np.array(data)
        data = data[:, [0, 2, 3]]
        data = data.astype(float)

        orbit.JDTDB = data[:, 0]
        orbit.X = data[:, 1]
        orbit.Y = data[:, 2]

        return orbit

    @staticmethod
    def from_csv(metadata, jdtdb, x, y):
        orbit = OrbitElement(metadata)
        orbit.JDTDB = np.array(jdtdb)
        orbit.X = np.array(x)
        orbit.Y = np.array(y)
        return orbit

    @staticmethod
    def encode(fp, orbit, kind):
        fp.write(struct.pack("8s", orbit.spkid.encode("utf-8")))
        fp.write(struct.pack("32s", orbit.name.encode("utf-8")))

        k_i = Kind.index(kind)
        fp.write(struct.pack("b", k_i))

        if k_i > 6:
            fp.write(struct.pack("c", bytes([orbit.neo])))
            fp.write(struct.pack("c", bytes([orbit.pha])))
        if k_i < 6:
            fp.write(struct.pack("f", orbit.distance_ratio))
        if k_i < 7:
            fp.write(struct.pack("8s", orbit.center.encode("utf-8")))

        phy_bit = hasattr(orbit, "radius_ratio")
        fp.write(struct.pack("c", bytes([phy_bit])))

        if phy_bit:
            fp.write(struct.pack("f", orbit.radius_ratio))

        fp.write(struct.pack("I", int(orbit.trail_duration)))
        fp.write(struct.pack("I", len(orbit.X)))
        [fp.write(struct.pack("d", x)) for x in orbit.JDTDB]
        [fp.write(struct.pack("d", x)) for x in orbit.X]
        [fp.write(struct.pack("d", x)) for x in orbit.Y]

    @staticmethod
    def decode(fp):
        # Check if there is data
        if fp.read(1) != b"":
            fp.seek(-1, os.SEEK_CUR)
        else:
            raise EOFError

        # Skip header
        if fp.tell() == 0:
            jd = struct.unpack("d", fp.read(8))[0]
            print(f"SSO file valid until JD {jd}")

        # Check if there is data
        spkid = fp.read(8).decode("utf-8").strip("\x00")
        name = fp.read(32).decode("utf-8").strip("\x00")
        k_i = struct.unpack("b", fp.read(1))[0]

        neo = None
        pha = None
        center = None
        distance_ratio = None
        if k_i > 6:
            neo = struct.unpack("c", fp.read(1))[0] == b"\x01"
            pha = struct.unpack("c", fp.read(1))[0] == b"\x01"
        if k_i < 6:
            distance_ratio = struct.unpack("f", fp.read(4))[0]
        if k_i < 7:
            center = fp.read(8).decode("utf-8").strip("\x00")

        phy_bit = struct.unpack("c", fp.read(1))[0] == b"\x01"

        radius_ratio = None
        if phy_bit:
            radius_ratio = struct.unpack("f", fp.read(4))[0]

        trail_duration = struct.unpack("I", fp.read(4))[0]
        size = struct.unpack("I", fp.read(4))[0]
        JDTDB = [struct.unpack("d", fp.read(8))[0] for _ in range(size)]
        X = [struct.unpack("d", fp.read(8))[0] for _ in range(size)]
        Y = [struct.unpack("d", fp.read(8))[0] for _ in range(size)]

        return OrbitElement.from_csv(
            {
                "spkid": spkid,
                "name": name,
                "kind": Kind.from_index(k_i),
                "trail_duration": trail_duration,
                **(
                    {"neo": neo, "pha": pha}
                    if k_i > 6
                    else {
                        "center": center,
                        **({"distance_ratio": distance_ratio} if k_i < 6 else {}),
                        **({"radius_ratio": radius_ratio} if phy_bit else {}),
                    }
                ),
            },
            JDTDB,
            X,
            Y,
        )


class Horizons:
    API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
    SUPPORT_API_URL = "https://ssd.jpl.nasa.gov/api/horizons_support.api"

    def __init__(self):
        pass

    def calculate_ratios(self, buffer):
        """
        This function only accepts major bodies and their satellites
        """
        with open("../data/physical.json", "r") as fp:
            physical_properties = json.load(fp)

        for orbits in buffer.values():
            # Group orbits by center
            centers = {}
            for orbit in orbits:
                if orbit.center not in centers:
                    centers[orbit.center] = []
                centers[orbit.center].append(orbit)

            # Calculate radius ratio for each center
            for orbits in centers.values():
                # Normalize radius
                radiuses = set(
                    [
                        physical_properties[o.spkid]["radius"]
                        for o in orbits
                        if o.spkid in physical_properties
                    ]
                )
                radiuses.update(
                    set(
                        [
                            physical_properties[o.center]["radius"]
                            for o in orbits
                            if o.center != "10" and o.spkid in physical_properties
                        ]
                    )
                )

                min_r = min(radiuses)
                max_r = max(radiuses)

                for orbit in [o for o in orbits if o.spkid in physical_properties]:
                    setattr(
                        orbit,
                        "radius_ratio",
                        (physical_properties[orbit.spkid]["radius"] - min_r)
                        / (max_r - min_r),
                    )

                # Calculate distance from center
                D = [np.sqrt(o.X**2 + o.Y**2).max() for o in orbits]
                min_distance = min(D)
                max_distance = max(D)

                if max_distance == min_distance:
                    setattr(orbits[0], "distance_ratio", 0)
                    continue

                for orbit, d in zip(orbits, D):
                    setattr(
                        orbit,
                        "distance_ratio",
                        (d - min_distance) / (max_distance - min_distance),
                    )

        return buffer

    def jd_valid_until(self):
        return Horizons._dt_to_jd(object_properties["default"]["stop"])

    @staticmethod
    def _dt_to_jd(dt):
        year = dt.year
        month = dt.month
        day = dt.day
        hour = dt.hour
        minute = dt.minute
        second = dt.second

        a = (14 - month) // 12
        y = year + 4800 - a
        m = month + 12 * a - 3
        julian = (
            day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
        )
        fraction = (hour - 12) / 24.0 + minute / 1440.0 + second / 86400.0
        julian += fraction
        return julian

    def get_available_objects(self):
        self.objects = {
            Kind.sun_and_planets: self.__get_support(
                list="planets", kind=Kind.sun_and_planets
            ),
            Kind.jovian_satellites: self.__get_support(
                list="js", kind=Kind.jovian_satellites
            ),
            Kind.saturian_satellites: self.__get_support(
                list="ss", kind=Kind.saturian_satellites
            ),
            Kind.uranian_satellites: self.__get_support(
                list="us", kind=Kind.uranian_satellites
            ),
            Kind.neptunian_satellites: self.__get_support(
                list="us", kind=Kind.neptunian_satellites
            ),
            Kind.other_satellites: self.__get_support(
                list="os", kind=Kind.other_satellites
            ),
            Kind.spacecrafts: self.__get_support(
                list="spacecraft", kind=Kind.spacecrafts
            ),
        }
        return self.objects

    def __get_support(self, **kwargs):
        params = {"www": "1", "time-span": "1", "list": kwargs["list"]}

        response = requests.get(Horizons.SUPPORT_API_URL, params=params)

        if response.status_code != 200:
            raise Exception("Error: %s" % response.text)

        data = response.json()["list"][0]["list"]

        def __check_valid(data):
            spkid = data["id"]
            cdmin = data["cd_min"]
            cdmax = data["cd_max"]
            op = get_object_props(kwargs["kind"], spkid)

            flag_start = False
            flag_end = False

            if "9999" in cdmin:
                flag_start = True

            if "9999" in cdmax:
                flag_end = True

            if flag_start and flag_end:
                return True

            if not flag_start:
                _cdmin = dateutil.parser.parse(cdmin)
                if _cdmin < op["stop"]:
                    flag_start = True

            if not flag_end:
                _cdmax = dateutil.parser.parse(cdmax)
                if _cdmax > op["stop"]:
                    flag_end = True

            return flag_start and flag_end

        def __fix_start(data):
            spkid = data["id"]
            cdmin = data["cd_min"]
            op = get_object_props(kwargs["kind"], spkid)

            span = op["stop"] - op["span"]

            if "9999" in cdmin:
                return span

            first_available = dateutil.parser.parse(cdmin)
            if first_available > span:
                return first_available + timedelta(seconds=1)
            return span

        return {
            d["id"]: {
                "name": d["name"],
                "start": __fix_start(d),
            }
            for d in data
            if d["id"] != "10" and __check_valid(d)
        }

    def __get(self, spkid, kind):
        # Search the spkid in the objects
        op = get_object_props(kind, spkid)

        starts = [op["stop"] - op["span"]]
        if spkid in self.objects[kind]:
            starts.append(self.objects[kind][spkid]["start"])
        start = max(starts)

        params = {
            "format": "text",
            "COMMAND": spkid,
            "OBJ_DATA": "NO",
            "MAKE_EPHEM": "YES",
            "EPHEM_TYPE": "VECTORS",
            "CENTER": "500@%s" % op["center"],
            "START_TIME": "'%s'" % start.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "STOP_TIME": "'%s'" % op["stop"].strftime("%Y-%m-%d %H:%M:%S.%f"),
            "STEP_SIZE": "'%d MINUTES'" % op["step"],
            "VEC_TABLE": "2",
            "VEC_CORR": "NONE",
            "VEC_DELTA_T": "NO",
            "VEC_LABELS": "NO",
            "OUT_UNITS": "AU-D",
            "REF_PLANE": "ECLIPTIC",
            "REF_SYSTEM": "ICRF",
            "CSV_FORMAT": "YES",
        }

        # Special case for Pluto's moons
        if op["center"] == "999":
            return None

        response = requests.get(Horizons.API_URL, params=params)

        if response.status_code != 200:
            raise Exception("[%d] SPKID: %s" % (response.status_code, spkid))

        if "Insufficient ephemeris data" in response.text:
            return None

        metadata = {
            "spkid": spkid,
            "name": self.objects[kind][spkid]["name"],
            "center": op["center"],
            "trail_duration": op["trail_duration"],
        }

        try:
            return OrbitElement.from_text(metadata, response.text)
        except Exception:
            os.mkdir("../error") if not os.path.exists("../error") else None
            with open(f"../error/{spkid}.log", "w") as f:
                f.write(response.text)
            raise Exception("[PARSE-ERROR] SPKID: %s" % spkid)

    def __ma_to_nu(self, ecc, M):
        # https://github.com/poliastro/poliastro/issues/1013#issuecomment-688782758
        ecc, M = ecc.value, M.to(u.rad).value
        if ecc < 1:
            M = (M + np.pi) % (2 * np.pi) - np.pi
            return E_to_nu(M_to_E(M, ecc), ecc)
        elif ecc == 1:
            return D_to_nu(M_to_D(M))
        else:
            return F_to_nu(M_to_F(M, ecc), ecc)

    def __calculate(self, spkid, kind):
        # Search the spkid in the objects
        op = get_object_props(kind, spkid)

        ephem = self.objects[kind][spkid]["ephem"]
        metadata = self.objects[kind][spkid]
        metadata["trail_duration"] = op["trail_duration"]
        del metadata["ephem"]

        start = op["stop"] - op["span"]
        end = op["stop"]
        periods = int(op["span"].total_seconds() / 60 / op["step"])

        a = ephem["a"] << u.AU
        e = ephem["e"] << u.one
        i = ephem["i"] << u.deg
        om = ephem["om"] << u.deg
        w = ephem["w"] << u.deg
        ma = ephem["ma"] << u.deg
        nu = self.__ma_to_nu(e, ma) << u.deg
        epoch = ephem["epoch"] << u.day

        orb = Orbit.from_classical(
            Sun, a, e, i, om, w, nu, epoch=Time(epoch, format="jd", scale="tdb")
        )

        epochs = time_range(start=start, end=end, periods=periods)
        ephem = orb.to_ephem(strategy=EpochsArray(epochs))

        r, v = ephem.rv()
        r = r.to(u.AU)
        v = v.to(u.AU / u.day)

        jdtdb = np.array(Time(epochs, format="jd", scale="tdb").jd)
        X = np.array(r[:, 0])
        Y = np.array(r[:, 1])

        return OrbitElement.from_csv(metadata, jdtdb, X, Y)

    def run(self, spkid, kind, as_completed):
        if not isinstance(spkid, list):
            raise Exception("SPKID must be a list")

        local = Kind.is_sb(kind)
        print(f"{'Calculating' if local else 'Getting'} {kind.value} ({len(spkid)})...")

        # Initialize
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=8 if local else 2
        ) as executor:
            futures = []
            for s in spkid:
                op = get_object_props(kind, s)
                if op["enabled"] is False:
                    continue

                if local:
                    futures.append(executor.submit(self.__calculate, s, kind))
                else:
                    futures.append(executor.submit(self.__get, s, kind))

            if len(futures) == 0:
                print("No jobs to run, skipping...")
                return

            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result is not None:
                    as_completed(result, kind)


class SBDB:
    API_URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"

    def __init__(self):
        self.default_params = {
            "fields": "spkid,full_name,neo,pha,a,e,i,om,w,ma,epoch",
            "full-prec": "true",
            # "limit": "100",
        }

    def __return(self, data):
        orbits = {}
        for d in data:
            # Check if all elements have data
            if not all(d[4:]):
                print(f"Missing data for #{d[0]}, skipping...")
                continue

            metadata = {
                "spkid": str(d[0]),
                "name": d[1].strip(),
                "neo": d[2] == "Y",
                "pha": d[3] == "Y",
            }

            ephem = {
                "a": float(d[4]),
                "e": float(d[5]),
                "i": float(d[6]),
                "om": float(d[7]),
                "w": float(d[8]),
                "ma": float(d[9]),
                "epoch": float(d[10]),
            }
            orbits[str(d[0])] = {
                **metadata,
                "ephem": ephem,
            }

        return orbits

    def get_comets(self, **kwargs):
        # https://www.spacereference.org/
        sbclass = ["ETc", "HTC", "HYP", "COM"]
        sbcdata = {
            "AND": [
                f"tp|LT|{Horizons._dt_to_jd(datetime.now() + timedelta(days=10 * 365))}",
                f"tp|GT|{Horizons._dt_to_jd(datetime.now() - timedelta(days=10 * 365))}",
            ]
        }

        params = {
            # "sb-ns": "n",  # Numbered status,`u` for unnumbered, empty for all
            "sb-kind": "c",  # Kind of object, `c` for comet, `a` for asteroid, empty for all
            # "sb-group": "neo", # Group, `neo` for near earth objects, `pha` for potentially hazardous objects, empty for all
            "sb-sat": "false",  # Satellite, `true` for limit results to small-bodies with at least one known satellite.
            "sb-xfrag": "1",  # Fragment, `true` for exclude all comet fragments (if any) from results.
            "sb-class": ",".join(sbclass),
            "sb-cdata": json.dumps(sbcdata, separators=(",", ":")).replace(" ", ""),
            **self.default_params,
        }

        response = requests.get(SBDB.API_URL, params=params)

        if response.status_code != 200:
            raise Exception("Error: %s" % response.text)

        data = response.json()["data"]
        return self.__return(data)

    def get_asteroids(self, **kwargs):
        # https://www.spacereference.org/
        # NOTE: IEO, ATE, APO, and AMO can be considered Near Earth
        # NOTE: IMB and MBA can be considered Main Belt
        sbcdata = {}
        sbclass = [
            "IEO",
            "ATE",
            "APO",
            "AMO",
            "IMB",
            "MBA",
        ]

        if "aclass" in kwargs:
            if kwargs["aclass"] == "neo":
                sbclass = [
                    "IEO",
                    "ATE",
                    "APO",
                    "AMO",
                ]
                sbcdata = {
                    "AND": [
                        "diameter|GE|2.0",
                    ]
                }
            elif kwargs["aclass"] == "imb":
                sbclass = ["IMB"]
                sbcdata = {
                    "AND": [
                        "diameter|GT|0",
                    ]
                }
            elif kwargs["aclass"] == "mba":
                sbclass = ["MBA"]
                sbcdata = {
                    "AND": [
                        "diameter|GE|10",
                    ]
                }

        params = {
            "sb-ns": "n",  # Numbered status,`u` for unnumbered, empty for all
            "sb-kind": "a",  # Kind of object, `c` for comet, `a` for asteroid, empty for all
            # "sb-group": "neo", # Group, `neo` for near earth objects, `pha` for potentially hazardous objects, empty for all
            "sb-sat": "false",  # Satellite, `true` for limit results to small-bodies with at least one known satellite.
            "sb-xfrag": "true",  # Fragment, `true` for exclude all comet fragments (if any) from results.
            "sb-class": ",".join(sbclass),
            "sb-cdata": json.dumps(sbcdata, separators=(",", ":")).replace(" ", ""),
            **self.default_params,
        }

        response = requests.get(SBDB.API_URL, params=params)

        if response.status_code != 200:
            raise Exception("Error: %s" % response.text)

        data = response.json()["data"]
        return self.__return(data)


class Database:
    def __init__(self, cache_path, invalidate_cache=False):
        self.horizons = Horizons()
        self.sbdb = SBDB()
        self.cache_path = cache_path

        # Database file
        self.fp = gzip.open(f"{self.cache_path}/orbits.sso.gz", "wb")

        # Buffer for ratio calculation
        self.buffer = {}

        if os.path.exists(f"{self.cache_path}/objects.pgz"):
            lm = os.path.getmtime(f"{self.cache_path}/objects.pgz")
            now = datetime.now().timestamp()
            if now - lm > 604_800:  # 1 week
                invalidate_cache = True

        # Check if we have the data
        if os.path.exists(f"{self.cache_path}/objects.pgz") and not invalidate_cache:
            with gzip.open(f"{self.cache_path}/objects.pgz", "rb") as f:
                self.objects = pickle.load(f)
        else:
            self.__populate()

        self.horizons.objects = self.objects

        # Set the SSO header
        self.fp.write(struct.pack("d", self.horizons.jd_valid_until()))

    def __del__(self):
        self.fp.close()

    def __populate(self):
        self.objects = self.horizons.get_available_objects()
        self.objects[Kind.comets] = self.sbdb.get_comets(kind=Kind.comets)
        self.objects[Kind.neo_asteroids] = self.sbdb.get_asteroids(
            aclass="neo", kind=Kind.neo_asteroids
        )
        self.objects[Kind.imb_asteroids] = self.sbdb.get_asteroids(
            aclass="imb", kind=Kind.imb_asteroids
        )
        self.objects[Kind.mba_asteroids] = self.sbdb.get_asteroids(
            aclass="mba", kind=Kind.mba_asteroids
        )

        with gzip.open(f"{self.cache_path}/objects.pgz", "w") as f:
            pickle.dump(self.objects, f)

    def list_objects(self):
        return [k for k in Kind]

    def update(self, kinds):
        if not isinstance(kinds, list):
            raise Exception("kinds must be a list")

        if len(kinds) == 0:
            raise Exception("kinds must have at least one element")

        add_to_buffer = (
            lambda o, k: self.buffer.__setitem__(k, [o])
            if k not in self.buffer
            else self.buffer[k].append(o)
        )

        if Kind.sun_and_planets in kinds:
            self.horizons.run(
                list(self.objects[Kind.sun_and_planets].keys()),
                Kind.sun_and_planets,
                add_to_buffer,
            )

        # if any of the kinds is satellite but sun_and_planets is not in the list
        if (
            any([k for k in kinds if Kind.is_satellite(k)])
            and Kind.sun_and_planets not in kinds
        ):
            raise Exception("You must update sun_and_planets as well")

        for kind in [k for k in kinds if Kind.is_satellite(k)]:
            objects = self.objects[kind]
            self.horizons.run(
                list(objects.keys()),
                kind,
                add_to_buffer,
            )

        # Calculate the ratios
        print("Calculating ratios...")
        calculated = self.horizons.calculate_ratios(self.buffer)

        # Flush the buffer
        print("Flushing buffer...")
        [OrbitElement.encode(self.fp, o, k) for k, v in calculated.items() for o in v]
        del self.buffer
        del calculated

        # Update the rest
        for kind in [k for k in kinds if Kind.is_sb(k)]:
            objects = self.objects[kind]
            self.horizons.run(
                list(objects.keys()),
                kind,
                lambda o, k: OrbitElement.encode(self.fp, o, k),
            )
