import atomic_queries as aq
from atomic_queries import (
    _query_high_speed_ticket,
    _query_normal_ticket,
    _query_assurances,
    _query_food,
    _query_contacts,
    request_with_timeout,
)
from config import BASE_URL, DEPARTURE_DATE
from seed_od import (
    SEED_HIGH_SPEED_PLACE_PAIRS,
    SEED_NORMAL_PLACE_PAIRS,
    first_non_empty_trips,
)
from traffic_stats import STATS
from utils import (
    env_truthy,
    random_boolean,
    random_consignee_phone_cn,
    random_str,
    random_form_list,
)

try:
    from traffic_log import detail_indent, tlog
except ImportError:
    def tlog(msg: str, indent: int = 0) -> None:
        print(f"{'  ' * indent}{msg}")

    def detail_indent() -> int:
        return 0

import logging
import random
import time

logger = logging.getLogger("query_and_preserve")


def query_and_preserve(headers):
    """
    1. 查票（随机高铁或普通），OD 与上游 train-ticket 种子数据对齐
    2. 查保险、Food、Contacts
    3. 随机选择Contacts、保险、是否买食物；托运默认关闭（TRAFFIC_ENABLE_CONSIGN=1 时随机开启）
    4. 买票

    返回结构化结果，供流量统计与新单闭环使用：
    attempted/skip_reason/http_status/status/msg/order_created/consign_requested/consign_ok/error
    """
    result = {
        "high_speed": None,
        "attempted": False,
        "skip_reason": None,
        "http_status": None,
        "status": None,
        "msg": "",
        "order_created": False,
        "consign_requested": False,
        "consign_ok": None,
        "error": None,
    }

    dep = DEPARTURE_DATE
    high_speed = random_boolean()
    result["high_speed"] = high_speed

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
        tlog(
            f"preserve.skip no_trips high_speed={high_speed} date={dep}",
            detail_indent(),
        )
        result["skip_reason"] = "no_trips"
        STATS.record("preserve", "skip", detail="no_trips")
        return result

    start, end = pair
    _ = _query_assurances(headers=headers)
    place_pair = (start, end)

    trip_id = random_form_list(trip_ids)
    # 种子 trainfood 仅含高铁车次（如 D1345），普通车走 travel2 时不要查餐，避免无意义失败与脏数据
    if high_speed:
        food_result = _query_food(
            place_pair=place_pair, train_num=trip_id, headers=headers, trip_date=dep)
    else:
        food_result = None

    contacts_result = _query_contacts(headers=headers)

    if not contacts_result:
        logger.warning("no contacts for account; skip preserve")
        tlog("preserve.skip no_contacts", detail_indent())
        result["skip_reason"] = "no_contacts"
        STATS.record("preserve", "skip", detail="no_contacts")
        return result

    base_preserve_payload = {
        "accountId": aq.current_user_id(),
        "assurance": 0,
        "contactsId": "",
        "date": dep,
        "from": start,
        "to": end,
        "tripId": ""
    }

    base_preserve_payload["tripId"] = trip_id

    need_food = random_boolean() if high_speed else False
    if need_food and food_result:
        logger.info("need food")
        food_dict = random_form_list(food_result)
        base_preserve_payload.update(food_dict)
    else:
        base_preserve_payload["foodType"] = 0
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
    seat_type = random_form_list([2, 3])
    base_preserve_payload["seatType"] = seat_type

    need_consign = env_truthy("TRAFFIC_ENABLE_CONSIGN", False) and random_boolean()
    result["consign_requested"] = need_consign
    if need_consign:
        consign = {
            "consigneeName": random_str(),
            "consigneePhone": random_consignee_phone_cn(),
            "consigneeWeight": random.randint(1, 10),
            "handleDate": dep
        }
        base_preserve_payload.update(consign)

    di = detail_indent()
    tlog(f"preserve.POST {PRESERVE_URL}", di)
    tlog(f"preserve.payload {base_preserve_payload}", di)
    tlog(
        f"preserve.flags high_speed={high_speed} need_food={need_food} "
        f"need_consign={need_consign} need_assurance={need_assurance}",
        di,
    )

    try:
        res, ms = request_with_timeout(
            "preserve", "POST", PRESERVE_URL, headers=headers, json=base_preserve_payload
        )
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        tlog(f"preserve.EXCEPTION {result['error']}", di)
        return result

    result["attempted"] = True
    result["http_status"] = res.status_code

    if res.status_code != 200:
        logger.debug(
            "preserve HTTP %s url=%s text=%s",
            res.status_code,
            PRESERVE_URL,
            (res.text or "")[:800],
        )
        tlog(f"preserve.FAIL http={res.status_code} url={PRESERVE_URL}", di)
        tlog(f"preserve.FAIL body {(res.text or '')[:700]!r}", di + 1)
        STATS.record("preserve", "http_fail", ms, detail=f"http_{res.status_code}")
        return result

    try:
        out = res.json()
    except ValueError:
        logger.debug(
            "preserve non-JSON url=%s raw=%s",
            PRESERVE_URL,
            (res.text or "")[:800],
        )
        tlog("preserve.FAIL non-JSON response", di)
        STATS.record("preserve", "http_fail", ms, detail="non_json_body")
        return result

    tlog(f"preserve.response {out}", di)
    result["status"] = out.get("status")
    result["msg"] = str(out.get("msg") or "")
    result["order_created"] = result["status"] == 1

    if result["order_created"]:
        outcome = "success" if result["msg"] == "Success." else "partial"
    else:
        outcome = "business_fail"
    STATS.record("preserve", outcome, ms, detail=result["msg"])

    if need_consign and result["order_created"]:
        # 托运失败时 preserve 会把 msg 覆盖为 "Consign Fail."；其他 msg 均视为托运已成功
        consign_ok = result["msg"] != "Consign Fail."
        result["consign_ok"] = consign_ok
        STATS.record(
            "consign_hs" if high_speed else "consign_normal",
            "success" if consign_ok else "business_fail",
            ms,
            detail=result["msg"],
        )

    if not result["order_created"]:
        logger.debug("preserve not success (common under concurrent load): %s", out)
        tlog(f"preserve.business_not_success {out!r}", di)

    return result


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
