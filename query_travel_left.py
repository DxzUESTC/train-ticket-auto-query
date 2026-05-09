from atomic_queries import _query_high_speed_ticket, _query_normal_ticket, auth_headers
from config import DEPARTURE_DATE
from seed_od import (
    SEED_HIGH_SPEED_PLACE_PAIRS,
    SEED_NORMAL_PLACE_PAIRS,
    first_non_empty_trips,
)

import logging
import time

logger = logging.getLogger("query_travel_left")


def query_travel_left(headers):
    dep = DEPARTURE_DATE
    high_speed = False
    if high_speed:
        _, trip_ids = first_non_empty_trips(
            _query_high_speed_ticket, SEED_HIGH_SPEED_PLACE_PAIRS, headers, dep)
        if not trip_ids:
            logger.warning("no high-speed trips for seed pairs")
    else:
        _, trip_ids = first_non_empty_trips(
            _query_normal_ticket, SEED_NORMAL_PLACE_PAIRS, headers, dep)
        if not trip_ids:
            logger.warning("no normal trips for seed pairs")


if __name__ == '__main__':
    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time}")

    for i in range(30):
        try:
            query_travel_left(headers=headers)
            print("*****************************INDEX:" + str(i))
        except Exception as e:
            print(e)
    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    print(f"start:{start_time} end:{end_time}")
