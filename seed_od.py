"""
Origin–destination pairs aligned with upstream train-ticket seed data.

References (repo train-ticket):
- ts-travel-service/.../travel/init/InitData.java
  All G1234–G1237 and D1345: startStationName=shanghai, stationsName=suzhou
  (first segment for passengers is Shang Hai -> Su Zhou).
- ts-travel2-service/.../travel2/init/InitData.java
  Z1234–Z1236, T1235, K1345: startStationName=shanghai, stationsName=nanjing
  (first segment is Shang Hai -> Nan Jing).

API display names come from ts-station-service InitData (e.g. "Shang Hai", "Su Zhou", "Nan Jing").

There is no Haikou etc. in seed data; do not expect arbitrary city pairs to return trips.
"""

from typing import Callable, List, Optional, Tuple

# (startingPlace, endPlace) for POST .../travelservice/trips/left
SEED_HIGH_SPEED_PLACE_PAIRS: List[Tuple[str, str]] = [
    ("Shang Hai", "Su Zhou"),
    ("Su Zhou", "Shang Hai"),
]

# (startingPlace, endPlace) for POST .../travel2service/trips/left
SEED_NORMAL_PLACE_PAIRS: List[Tuple[str, str]] = [
    ("Shang Hai", "Nan Jing"),
    ("Nan Jing", "Shang Hai"),
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
    """Try each seed pair until query_fn returns a non-empty list."""
    for pair in pairs:
        trip_ids = query_fn(place_pair=pair, headers=headers, departure_time=departure_time)
        if trip_ids:
            return pair, trip_ids
    return None, None
