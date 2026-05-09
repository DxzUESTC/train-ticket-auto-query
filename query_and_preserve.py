import atomic_queries as aq
from atomic_queries import _query_high_speed_ticket, _query_normal_ticket, _query_assurances, _query_food, _query_contacts
from config import BASE_URL
from utils import random_boolean, random_phone, random_str, random_form_list

import logging
import random
import requests
import time

logger = logging.getLogger("query_and_preserve")

date = time.strftime("%Y-%m-%d", time.localtime())


def query_and_preserve(headers):
    """
    1. 查票（随机高铁或普通）
    2. 查保险、Food、Contacts
    3. 随机选择Contacts、保险、是否买食物、是否托运
    4. 买票
    :return:
    """
    start = ""
    end = ""
    trip_ids = []
    PRESERVE_URL = ""

    high_speed = random_boolean()
    if high_speed:
        start = "Shang Hai"
        end = "Su Zhou"
        high_speed_place_pair = (start, end)
        trip_ids = _query_high_speed_ticket(place_pair=high_speed_place_pair, headers=headers, departure_time=date)
        PRESERVE_URL = f"{BASE_URL}/api/v1/preserveservice/preserve"
    else:
        start = "Shang Hai"
        end = "Nan Jing"
        other_place_pair = (start, end)
        trip_ids = _query_normal_ticket(place_pair=other_place_pair, headers=headers, departure_time=date)
        PRESERVE_URL = f"{BASE_URL}/api/v1/preserveotherservice/preserveOther"

    if not trip_ids:
        logger.warning(
            "no trips for preserve path=%s-%s high_speed=%s date=%s; skip",
            start, end, high_speed, date,
        )
        return

    _ = _query_assurances(headers=headers)
    food_result = _query_food(headers=headers, trip_date=date)
    contacts_result = _query_contacts(headers=headers)

    if not contacts_result:
        logger.warning("no contacts for account; skip preserve")
        return

    base_preserve_payload = {
        "accountId": aq.uuid,
        "assurance": "0",
        "contactsId": "",
        "date": date,
        "from": start,
        "to": end,
        "tripId": ""
    }

    trip_id = random_form_list(trip_ids)
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
            "handleDate": date
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
