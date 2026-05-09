"""
Origin–destination pairs aligned with upstream train-ticket seed data.

References (repo train-ticket):
- ts-travel-service/.../travel/init/InitData.java — G/D trips: route stations like shanghai, suzhou.
- ts-travel2-service/.../travel2/init/InitData.java — Z/T/K trips: e.g. shanghai, nanjing.

Use the same strings as Route.stations in ts-route-service / admin Route List (lowercase, no spaces).
TravelServiceImpl matches start/end with route.getStations().indexOf(...); display
names from ts-station-service (e.g. \"Shang Hai\") will NOT match unless normalized — see
utils.normalize_route_station_name and atomic_queries payload handling.
"""

from typing import Callable, List, Optional, Tuple

from utils import normalize_place_pair

# (startPlace, endPlace) semantics for POST .../travelservice/trips/left (JSON keys: startPlace, endPlace)
SEED_HIGH_SPEED_PLACE_PAIRS: List[Tuple[str, str]] = [
    ("shanghai", "suzhou"),
    ("suzhou", "shanghai"),
]

# Same for POST .../travel2service/trips/left (TripInfo in ts-common)
SEED_NORMAL_PLACE_PAIRS: List[Tuple[str, str]] = [
    ("shanghai", "nanjing"),
    ("nanjing", "shanghai"),
]

# For travel-plan / exploratory queries (union of both services' typical OD)
SEED_PLACE_PAIRS_ALL: List[Tuple[str, str]] = (
    SEED_HIGH_SPEED_PLACE_PAIRS + SEED_NORMAL_PLACE_PAIRS
)


def first_non_empty_trips(
    query_fn: Callable[..., Optional[list]],
    pairs: List[Tuple[str, str]],
    headers: dict,
    departure_time: str,
) -> Tuple[Optional[Tuple[str, str]], Optional[list]]:
    """Try each seed pair until query_fn returns a non-empty list.

    Returns (place_pair, trip_ids). On failure returns (None, None) — unpack as
    ``pair, trip_ids = ...`` then check ``if not pair or not trip_ids`` (do not
    unpack pair into (start, end) when pair may be None).
    """
    for pair in pairs:
        npair = normalize_place_pair(pair)
        trip_ids = query_fn(place_pair=npair, headers=headers, departure_time=departure_time)
        if trip_ids:
            return npair, trip_ids
    return None, None
