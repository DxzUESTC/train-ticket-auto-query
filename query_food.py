from atomic_queries import _query_food, auth_headers
from config import DEPARTURE_DATE
from seed_od import SEED_HIGH_SPEED_PLACE_PAIRS

import logging
import time

logger = logging.getLogger("query_food")

# D1345: ts-travel-service travel/init/InitData.java (DongCheOne, shanghai->suzhou segment)
DEFAULT_SEED_TRAIN = "D1345"


def query_food(headers, place_pair=None, train_num=None):
    pair = place_pair or SEED_HIGH_SPEED_PLACE_PAIRS[0]
    num = train_num or DEFAULT_SEED_TRAIN
    _query_food(place_pair=pair, train_num=num, headers=headers, trip_date=DEPARTURE_DATE)


if __name__ == '__main__':
    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    for i in range(320):
        try:
            query_food(headers=headers)
            print("*****************************INDEX:" + str(i))
        except Exception as e:
            print(e)

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    print(f"start:{start_time} end:{end_time}")
