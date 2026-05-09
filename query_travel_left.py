from atomic_queries import _query_high_speed_ticket, _query_normal_ticket, auth_headers
from config import DEPARTURE_DATE

import logging
import time

logger = logging.getLogger("query_travel_left")


def query_travel_left(headers):
    """
    1. 查票（随机高铁或普通）
    :return:
    """
    high_speed = False
    if high_speed:
        start = "Shang Hai"
        end = "Su Zhou"
        high_speed_place_pair = (start, end)
        _query_high_speed_ticket(place_pair=high_speed_place_pair, headers=headers, departure_time=DEPARTURE_DATE)
    else:
        start = "Shang Hai"
        end = "Nan Jing"
        other_place_pair = (start, end)
        _query_normal_ticket(place_pair=other_place_pair, headers=headers, departure_time=DEPARTURE_DATE)


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
