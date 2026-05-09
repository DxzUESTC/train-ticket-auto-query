from atomic_queries import _query_high_speed_ticket_parallel, auth_headers
from config import DEPARTURE_DATE
from seed_od import SEED_HIGH_SPEED_PLACE_PAIRS, first_non_empty_trips

import logging
import time

logger = logging.getLogger("query_travel_left_parallel")


def query_travel_left_parallel(headers):
    dep = DEPARTURE_DATE
    _, trip_ids = first_non_empty_trips(
        _query_high_speed_ticket_parallel, SEED_HIGH_SPEED_PLACE_PAIRS, headers, dep)
    if not trip_ids:
        logger.warning("no parallel high-speed trips for seed pairs")


if __name__ == '__main__':
    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time}")

    for i in range(320):
        try:
            query_travel_left_parallel(headers=headers)
            print("*****************************INDEX:" + str(i))
        except Exception as e:
            print(e)
    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    print(f"start:{start_time} end:{end_time}")
