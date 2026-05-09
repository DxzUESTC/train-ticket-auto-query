import atomic_queries as aq
from atomic_queries import _query_high_speed_ticket, _query_normal_ticket, _query_assurances, _query_food, _query_contacts
from config import BASE_URL, DEPARTURE_DATE
from seed_od import (
    SEED_HIGH_SPEED_PLACE_PAIRS,
    SEED_NORMAL_PLACE_PAIRS,
    first_non_empty_trips,
)
from utils import random_boolean, random_phone, random_str, random_form_list

import logging
import random
import requests
import time

logger = logging.getLogger("query_and_preserve")


def query_and_preserve(headers):
    """
    1. 查票（随机高铁或普通），OD 与上游 train-ticket 种子数据对齐
    2. 查保险、Food、Contacts
    3. 随机选择Contacts、保险、是否买食物、是否托运
    4. 买票
    :return:
    """
    dep = DEPARTURE_DATE
    high_speed = random_boolean()

    if high_speed:
        pair, trip_ids = first_non_empty_trips(
            _query_high_speed_ticket, SEED_HIGH_SPEED_PLACE_PAIRS, headers, dep)
        PRESERVE_URL = f"{BASE_URL}/api/v1/preserveservice/preserve"
    else:
        pair, trip_ids = first_non_empty_trips(
            _query_normal_ticket, SEED_NORMAL_PLACE_PAIRS, headers, dep)
        PRESERVE_URL = f"{BASE_URL}/api/v1/preserveotherservice/preserveOther"

    if not pair or not trip_ids:
        logger.warning(
            "no trips for preserve high_speed=%s date=%s tried_pairs=%s; skip",
            high_speed, dep,
            SEED_HIGH_SPEED_PLACE_PAIRS if high_speed else SEED_NORMAL_PLACE_PAIRS,
        )
        return

    start, end = pair
    _ = _query_assurances(headers=headers)
    place_pair = (start, end)

    trip_id = random_form_list(trip_ids)
    food_result = _query_food(
        place_pair=place_pair, train_num=trip_id, headers=headers, trip_date=dep)
    contacts_result = _query_contacts(headers=headers)

    if not contacts_result:
        logger.warning("no contacts for account; skip preserve")
        return

    base_preserve_payload = {
        "accountId": aq.uuid,
        "assurance": "0",
        "contactsId": "",
        "date": dep,
        "from": start,
        "to": end,
        "tripId": ""
    }

    base_preserve_payload["tripId"] = trip_id

    need_food = random_boolean()
    if need_food and food_result:
        logger.info("need food")
        food_dict = random_form_list(food_result)
        base_preserve_payload.update(food_dict)
    else:
        base_preserve_payload["foodType"] = "0"
        if need_food and not food_result:
            logger.info("need food but API returned none; skip food extras")
        elif not need_food:
            logger.info("not need food")

    need_assurance = random_boolean()
    if need_assurance:
        base_preserve_payload["assurance"] = 1

    contacts_id = random_form_list(contacts_result)
    base_preserve_payload["contactsId"] = contacts_id

    # 高铁 2-3
    seat_type = random_form_list(["2", "3"])
    base_preserve_payload["seatType"] = seat_type

    need_consign = random_boolean()
    if need_consign:
        consign = {
            "consigneeName": random_str(),
            "consigneePhone": random_phone(),
            "consigneeWeight": random.randint(1, 10),
            "handleDate": dep
        }
        base_preserve_payload.update(consign)

    print("payload:" + str(base_preserve_payload))

    print(f"choices: preserve_high: {high_speed} need_food:{need_food}  need_consign: {need_consign}  need_assurance:{need_assurance}")

    res = requests.post(url=PRESERVE_URL,
                        headers=headers,
                        json=base_preserve_payload)

    print(res.json())
    if res.json().get("data") != "Success":
        raise Exception(str(res.json()) + " not success")


if __name__ == '__main__':
    from atomic_queries import auth_headers

    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    for i in range(1000):
        try:
            query_and_preserve(headers=headers)
            print("*****************************INDEX:" + str(i))
        except Exception as e:
            print(e)

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time} end:{end_time}")
