"""
Origin–destination pairs aligned with upstream train-ticket seed data.

References (repo train-ticket):
- ts-travel-service/.../travel/init/InitData.java — G/D trips: route stations like shanghai, suzhou.
- ts-travel2-service/.../travel2/init/InitData.java — Z/T/K trips: e.g. shanghai, nanjing.

Use the same strings as Route.stations in ts-route-service / admin Route List (lowercase, no spaces).
Many pairs below may return no trips for a given service/date; first_non_empty_trips tries in order until one hits.

TravelServiceImpl matches start/end with route.getStations().indexOf(...); display
names from ts-station-service will NOT match unless normalized — see
utils.normalize_route_station_name and atomic_queries payload handling.
"""

from typing import Callable, List, Optional, Tuple

from utils import normalize_place_pair


def _uniq_ordered(pairs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen = set()
    out: List[Tuple[str, str]] = []
    for a, b in pairs:
        k = (a, b)
        if k in seen:
            continue
        seen.add(k)
        out.append((a, b))
    return out


# (startPlace, endPlace) for POST .../travelservice/trips/left — 与常见高铁线路/Route List 站名一致
_RAW_HIGH = [
    ("shanghai", "suzhou"),
    ("suzhou", "shanghai"),
    ("shanghai", "nanjing"),
    ("nanjing", "shanghai"),
    ("nanjing", "suzhou"),
    ("suzhou", "nanjing"),
    ("nanjing", "zhenjiang"),
    ("zhenjiang", "nanjing"),
    ("zhenjiang", "wuxi"),
    ("wuxi", "zhenjiang"),
    ("wuxi", "suzhou"),
    ("suzhou", "wuxi"),
    ("shanghaihongqiao", "jiaxingnan"),
    ("jiaxingnan", "shanghaihongqiao"),
    ("jiaxingnan", "hangzhou"),
    ("hangzhou", "jiaxingnan"),
    ("shanghaihongqiao", "hangzhou"),
    ("hangzhou", "shanghaihongqiao"),
]

# POST .../travel2service/trips/left — 普速/车次2 常见区段
_RAW_NORMAL = [
    ("shanghai", "nanjing"),
    ("nanjing", "shanghai"),
    ("nanjing", "xuzhou"),
    ("xuzhou", "nanjing"),
    ("xuzhou", "jinan"),
    ("jinan", "xuzhou"),
    ("jinan", "beijing"),
    ("beijing", "jinan"),
    ("shanghai", "shijiazhuang"),
    ("shijiazhuang", "shanghai"),
    ("shijiazhuang", "nanjing"),
    ("nanjing", "shijiazhuang"),
    ("shanghai", "taiyuan"),
    ("taiyuan", "shanghai"),
    ("taiyuan", "shijiazhuang"),
    ("shijiazhuang", "taiyuan"),
    ("nanjing", "beijing"),
    ("beijing", "nanjing"),
    ("shanghai", "beijing"),
    ("beijing", "shanghai"),
    ("nanjing", "shanghai"),
    ("shanghai", "nanjing"),
    ("nanjing", "suzhou"),
    ("suzhou", "nanjing"),
]

SEED_HIGH_SPEED_PLACE_PAIRS: List[Tuple[str, str]] = _uniq_ordered(_RAW_HIGH)
SEED_NORMAL_PLACE_PAIRS: List[Tuple[str, str]] = _uniq_ordered(_RAW_NORMAL)

# For travel-plan / exploratory queries (union of both services' typical OD)
SEED_PLACE_PAIRS_ALL: List[Tuple[str, str]] = _uniq_ordered(
    list(SEED_HIGH_SPEED_PLACE_PAIRS) + list(SEED_NORMAL_PLACE_PAIRS)
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
