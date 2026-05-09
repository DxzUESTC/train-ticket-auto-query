from atomic_queries import _query_high_speed_ticket_parallel, auth_headers
from config import DEPARTURE_DATE

import logging
import time

logger = logging.getLogger("query_travel_left_parallel")


def query_travel_left_parallel(headers):
    start = "Su Zhou"
    end = "Shang Hai"
    high_speed_place_pair = (start, end)
    _query_high_speed_ticket_parallel(place_pair=high_speed_place_pair, headers=headers, departure_time=DEPARTURE_DATE)


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
