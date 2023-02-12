from enum import Enum
from copy import deepcopy
from functools import lru_cache
from datetime import datetime, timedelta, timezone


class Kind(Enum):
    sun_and_planets = "sun_and_planets"
    jovian_satellites = "jovian_satellites"
    saturian_satellites = "saturian_satellites"
    uranian_satellites = "uranian_satellites"
    neptunian_satellites = "neptunian_satellites"
    other_satellites = "other_satellites"
    spacecrafts = "spacecrafts"
    comets = "comets"
    neo_asteroids = "neo-asteroids"
    imb_asteroids = "imb-asteroids"
    mba_asteroids = "mba-asteroids"

    @staticmethod
    def is_sb(kind):
        return kind in [
            Kind.comets,
            Kind.neo_asteroids,
            Kind.imb_asteroids,
            Kind.mba_asteroids,
        ]

    @staticmethod
    def is_mb(kind):
        return not Kind.is_sb(kind) and kind != Kind.spacecrafts

    @staticmethod
    def is_satellite(kind):
        return kind in [
            Kind.jovian_satellites,
            Kind.saturian_satellites,
            Kind.uranian_satellites,
            Kind.neptunian_satellites,
            Kind.other_satellites,
        ]

    @staticmethod
    def index(kind):
        return [
            Kind.sun_and_planets,
            Kind.jovian_satellites,
            Kind.saturian_satellites,
            Kind.uranian_satellites,
            Kind.neptunian_satellites,
            Kind.other_satellites,
            Kind.spacecrafts,
            Kind.comets,
            Kind.neo_asteroids,
            Kind.imb_asteroids,
            Kind.mba_asteroids,
        ].index(kind)

    @staticmethod
    def from_index(index):
        return [
            k
            for k in [
                Kind.sun_and_planets,
                Kind.jovian_satellites,
                Kind.saturian_satellites,
                Kind.uranian_satellites,
                Kind.neptunian_satellites,
                Kind.other_satellites,
                Kind.spacecrafts,
                Kind.comets,
                Kind.neo_asteroids,
                Kind.imb_asteroids,
                Kind.mba_asteroids,
            ]
        ][index]


"""
prop: dict <- Time range and other props for each kind
    span: timedelta <- Time span [post hook -> adds file validity]
    stop: datetime <- Stop time
    step: int <- Time step (hours) [post-hook -> int minutes]
    center: str <- Center object id
    enabled: bool <- Whether to enable this (default to True)
    trail_duration: timedelta <- Trail duration (default to span) [post-hook -> int total seconds]
object_properties: dict <- Time range and other props for each object
    default: prop <- Default time range for all objects
    objects: <- Objects time range
        <kind key>: <- Kind time range
            default: prop <- Default time range for *this* kind
            individual: <- Individual time range for *this* kind
                <object id>: prop <- Object time range
NOTE: Horizons API has a limit of 90024 data points per request
"""

FILE_VALIDITY = timedelta(weeks=1)

object_properties = {
    "default": {
        "span": timedelta(days=365),
        "stop": datetime.utcnow() + FILE_VALIDITY,
        "step": timedelta(days=1),
        "center": "10",
        "enabled": True,
    },
    "objects": {
        Kind.sun_and_planets: {
            "individual": {
                "199": {
                    "span": timedelta(days=88),
                    "step": timedelta(hours=6),
                },
                "299": {
                    "span": timedelta(days=224),
                    "step": timedelta(hours=12),
                },
                "399": {
                    "step": timedelta(hours=12),
                },
                "499": {
                    "span": timedelta(days=686),
                    "step": timedelta(hours=12),
                },
                "599": {
                    "span": timedelta(days=4333),
                    "step": timedelta(days=7),
                    "enabled": False,
                },
                "699": {
                    "span": timedelta(days=10759),
                    "step": timedelta(days=7),
                    "enabled": False,
                },
                "799": {
                    "span": timedelta(days=30685),
                    "step": timedelta(days=14),
                    "enabled": False,
                },
                "899": {
                    "span": timedelta(days=60190),
                    "step": timedelta(days=21),
                    "enabled": False,
                },
            },
        },
        Kind.jovian_satellites: {
            "default": {
                "center": "599",
                "span": timedelta(days=60),
                "step": timedelta(days=1),
                "enabled": False,
            },
        },
        Kind.saturian_satellites: {
            "default": {
                "center": "699",
                "span": timedelta(days=60),
                "step": timedelta(days=1),
                "enabled": False,
            },
        },
        Kind.uranian_satellites: {
            "default": {
                "center": "799",
                "span": timedelta(days=60),
                "step": timedelta(days=1),
                "enabled": False,
            },
        },
        Kind.neptunian_satellites: {
            "default": {
                "center": "899",
                "span": timedelta(days=60),
                "step": timedelta(days=1),
                "enabled": False,
            },
        },
        Kind.other_satellites: {
            "default": {
                "span": timedelta(days=60),
                "step": timedelta(days=1),
                "center": "999",
            },
            "individual": {
                "301": {
                    "span": timedelta(days=27),
                    "step": timedelta(hours=1),
                    "center": "399",
                    "trail_duration": timedelta(days=7),
                },
                "401": {
                    "span": timedelta(hours=8),
                    "step": timedelta(minutes=15),
                    "center": "499",
                    "trail_duration": timedelta(hours=2),
                },
                "402": {
                    "span": timedelta(hours=30),
                    "step": timedelta(minutes=15),
                    "center": "499",
                    "trail_duration": timedelta(hours=8),
                },
            },
        },
        Kind.spacecrafts: {
            "default": {
                "span": timedelta(days=60),
                "step": timedelta(hours=1),
            },
        },
        Kind.comets: {
            "default": {
                "span": timedelta(days=180),
                "step": timedelta(days=1),
            },
        },
        Kind.neo_asteroids: {
            "default": {
                "span": timedelta(days=60),
                "step": timedelta(days=1),
            },
        },
        Kind.imb_asteroids: {
            "default": {
                "span": timedelta(days=30),
                "step": timedelta(days=1),
            },
        },
        Kind.mba_asteroids: {
            "default": {
                "span": timedelta(days=30),
                "step": timedelta(days=1),
            },
        },
    },
}


def build_props(kind, spkid):
    if kind not in object_properties["objects"]:
        return object_properties["default"]

    if "individual" not in object_properties["objects"][kind]:
        return {
            **object_properties["default"],
            **object_properties["objects"][kind]["default"],
        }

    if spkid not in object_properties["objects"][kind]["individual"]:
        if "default" not in object_properties["objects"][kind]:
            return object_properties["default"]
        return {
            **object_properties["default"],
            **object_properties["objects"][kind]["default"],
        }

    if "default" not in object_properties["objects"][kind]:
        return {
            **object_properties["default"],
            **object_properties["objects"][kind]["individual"][spkid],
        }

    return {
        **object_properties["default"],
        **object_properties["objects"][kind]["default"],
        **object_properties["objects"][kind]["individual"][spkid],
    }


@lru_cache(maxsize=None)
def get_object_props(kind, spkid):
    props = deepcopy(build_props(kind, spkid))

    # Add default values
    if "trail_duration" not in props:
        props["trail_duration"] = props["span"]
    if "enabled" not in props:
        props["enabled"] = True

    # Post-hook
    props["span"] += FILE_VALIDITY
    props["trail_duration"] = props["trail_duration"].total_seconds()
    props["step"] = int(props["step"].total_seconds() / 60)

    return props
