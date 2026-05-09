from typing import List, Optional
import logging
import time
import requests

from config import BASE_URL

logger = logging.getLogger("atomic_queries")

base_address = BASE_URL

# Set by _login() after successful authentication (used by order/contact endpoints).
uuid = ""

date = time.strftime("%Y-%m-%d", time.localtime())


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _hdr(headers: Optional[dict]) -> dict:
    return headers if headers is not None else {}


def auth_headers(username="fdse_microservice", password="111111"):
    """Login and return headers with Bearer token, or None if login fails."""
    _, token = _login(username=username, password=password)
    if not token:
        return None
    return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}


def _login(username="fdse_microservice", password="111111"):
    global uuid
    session = requests.Session()
    session.headers.update({
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Content-Type': 'application/json',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
    })

    base = base_address.rstrip("/")
    verify_url = f"{base}/api/v1/verifycode/generate"
    login_url = f"{base}/api/v1/users/login"

    session.get(url=verify_url, verify=False)

    headers = {
        'Origin': login_url,
        'Referer': f"{base}/client_login.html",
    }

    data = '{"username":"' + username + '","password":"' + password + '","verificationCode":"1234"}'

    r = session.post(url=login_url, headers=headers, data=data, verify=False)

    if r.status_code == 200:
        body = r.json().get("data")
        if not body:
            return None, None
        uid = body.get("userId")
        token = body.get("token")
        if uid:
            uuid = uid
        return uid, token

    return None, None


def admin_login():
    return _login


def _query_high_speed_ticket(place_pair: tuple = ("Shang Hai", "Su Zhou"), headers: Optional[dict] = None,
                             departure_time: Optional[str] = None) -> Optional[List[str]]:
    headers = _hdr(headers)
    dep = departure_time if departure_time is not None else _today()

    url = f"{base_address}/api/v1/travelservice/trips/left"

    payload = {
        "departureTime": dep,
        "startingPlace": place_pair[0],
        "endPlace": place_pair[1],
    }

    response = requests.post(url=url, headers=headers, json=payload)

    if response.status_code != 200 or response.json().get("data") is None:
        logger.warning(f"request for {url} failed. response data is {response.text}")
        return None

    data = response.json().get("data")

    trip_ids = []
    for d in data:
        trip_id = d.get("tripId").get("type") + d.get("tripId").get("number")
        trip_ids.append(trip_id)
    return trip_ids


def _query_normal_ticket(place_pair: tuple = ("Nan Jing", "Shang Hai"), headers: Optional[dict] = None,
                         departure_time: Optional[str] = None) -> Optional[List[str]]:
    headers = _hdr(headers)
    dep = departure_time if departure_time is not None else _today()

    url = f"{base_address}/api/v1/travel2service/trips/left"

    payload = {
        "departureTime": dep,
        "startingPlace": place_pair[0],
        "endPlace": place_pair[1],
    }

    response = requests.post(url=url, headers=headers, json=payload)
    if response.status_code != 200 or response.json().get("data") is None:
        logger.warning(f"request for {url} failed. response data is {response.json()}")
        return None

    data = response.json().get("data")

    trip_ids = []
    for d in data:
        trip_id = d.get("tripId").get("type") + d.get("tripId").get("number")
        trip_ids.append(trip_id)
    return trip_ids


def _query_high_speed_ticket_parallel(place_pair: tuple = ("Shang Hai", "Su Zhou"), headers: Optional[dict] = None,
                                      departure_time: Optional[str] = None) -> Optional[List[str]]:
    headers = _hdr(headers)
    dep = departure_time if departure_time is not None else _today()

    url = f"{base_address}/api/v1/travelservice/trips/left_parallel"

    payload = {
        "departureTime": dep,
        "startingPlace": place_pair[0],
        "endPlace": place_pair[1],
    }

    response = requests.post(url=url, headers=headers, json=payload)

    if response.status_code != 200 or response.json().get("data") is None:
        logger.warning(f"request for {url} failed. response data is {response.text}")
        return None

    data = response.json().get("data")

    trip_ids = []
    for d in data:
        trip_id = d.get("tripId").get("type") + d.get("tripId").get("number")
        trip_ids.append(trip_id)
    return trip_ids


def _query_advanced_ticket(place_pair: tuple = ("Nan Jing", "Shang Hai"), headers: Optional[dict] = None,
                           departure_time: Optional[str] = None,
                           type: str = "cheapest") -> Optional[List[str]]:
    headers = _hdr(headers)
    dep = departure_time if departure_time is not None else _today()

    url = f"{base_address}/api/v1/travelplanservice/travelPlan/" + type
    print(url)

    payload = {
        "departureTime": dep,
        "startingPlace": place_pair[0],
        "endPlace": place_pair[1],
    }

    response = requests.post(url=url, headers=headers, json=payload)
    if response.status_code != 200 or response.json().get("data") is None:
        logger.warning(f"request for {url} failed. response data is {response.json()}")
        return None

    data = response.json().get("data")

    trip_ids = []
    for d in data:
        trip_id = d.get("tripId")
        trip_ids.append(trip_id)
    return trip_ids


def _query_assurances(headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/assuranceservice/assurances/types"
    response = requests.get(url=url, headers=headers)
    if response.status_code != 200 or response.json().get("data") is None:
        logger.warning(f"query assurance failed, response data is {response.json()}")
        return None
    response.json().get("data")

    return [{"assurance": "1"}]


def _query_food(place_pair: tuple = ("Shang Hai", "Su Zhou"), train_num: str = "D1345",
                headers: Optional[dict] = None, trip_date: Optional[str] = None):
    headers = _hdr(headers)
    day = trip_date if trip_date is not None else _today()
    url = f"{base_address}/api/v1/foodservice/foods/{day}/{place_pair[0]}/{place_pair[1]}/{train_num}"

    response = requests.get(url=url, headers=headers)
    if response.status_code != 200 or response.json().get("data") is None:
        logger.warning(f"query food failed, response data is {response}")
        return None
    response.json().get("data")

    return [{
        "foodName": "Soup",
        "foodPrice": 3.7,
        "foodType": 2,
        "stationName": "Su Zhou",
        "storeName": "Roman Holiday"
    }]


def _query_contacts(headers: Optional[dict] = None) -> Optional[List[str]]:
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/contactservice/contacts/account/{uuid}"

    response = requests.get(url=url, headers=headers)
    if response.status_code != 200 or response.json().get("data") is None:
        logger.warning(f"query contacts failed, response data is {response.json()}")
        return None

    data = response.json().get("data")

    ids = [d.get("id") for d in data if d.get("id") is not None]
    return ids


def _query_orders(headers: Optional[dict] = None, types: tuple = tuple([0]), query_other: bool = False) -> Optional[List[tuple]]:
    headers = _hdr(headers)

    if query_other:
        url = f"{base_address}/api/v1/orderOtherService/orderOther/refresh"
    else:
        url = f"{base_address}/api/v1/orderservice/order/refresh"

    payload = {
        "loginId": uuid,
    }

    response = requests.post(url=url, headers=headers, json=payload)
    if response.status_code != 200 or response.json().get("data") is None:
        logger.warning(f"query orders failed, response data is {response.text}")
        return None

    data = response.json().get("data")
    pairs = []
    for d in data:
        if d.get("status") in types:
            order_id = d.get("id")
            trip_id = d.get("trainNumber")
            pairs.append((order_id, trip_id))
    print(f"queried {len(pairs)} orders")

    return pairs


def _query_orders_all_info(headers: Optional[dict] = None, query_other: bool = False) -> Optional[List[tuple]]:
    headers = _hdr(headers)

    if query_other:
        url = f"{base_address}/api/v1/orderOtherService/orderOther/refresh"
    else:
        url = f"{base_address}/api/v1/orderservice/order/refresh"

    payload = {
        "loginId": uuid,
    }

    response = requests.post(url=url, headers=headers, json=payload)
    if response.status_code != 200 or response.json().get("data") is None:
        logger.warning(f"query orders failed, response data is {response.text}")
        return None

    data = response.json().get("data")
    pairs = []
    for d in data:
        result = {}
        result["accountId"] = d.get("accountId")
        result["targetDate"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        result["orderId"] = d.get("id")
        result["from"] = d.get("from")
        result["to"] = d.get("to")
        pairs.append(result)
    print(f"queried {len(pairs)} orders")

    return pairs


def _put_consign(result, headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/consignservice/consigns"
    consignload = {
        "accountId": result["accountId"],
        "handleDate": time.strftime('%Y-%m-%d', time.localtime(time.time())),
        "targetDate": result["targetDate"],
        "from": result["from"],
        "to": result["to"],
        "orderId": result["orderId"],
        "consignee": "32",
        "phone": "12345677654",
        "weight": "32",
        "id": "",
        "isWithin": False
    }
    response = requests.put(url=url, headers=headers,
                            json=consignload)

    order_id = result["orderId"]
    if response.status_code in (200, 201):
        print(f"{order_id} put consign success")
    else:
        print(f"{order_id} failed!")
        return None

    return order_id


def _query_route(routeId: str = '92708982-77af-4318-be25-57ccb0ff69ad', headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/routeservice/routes/{routeId}"

    res = requests.get(url=url, headers=headers)

    if res.status_code == 200:
        print(f"query {routeId} success")
    else:
        print(f"query {routeId} fail")

    return


def _pay_one_order(order_id, trip_id, headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/inside_pay_service/inside_payment"
    payload = {
        "orderId": order_id,
        "tripId": trip_id
    }

    response = requests.post(url=url, headers=headers,
                             json=payload)

    if response.status_code == 200:
        print(f"{order_id} pay success")
    else:
        print(f"pay {order_id} failed!")
        return None

    return order_id


def _cancel_one_order(order_id, uid, headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/cancelservice/cancel/{order_id}/{uid}"

    response = requests.get(url=url,
                            headers=headers)

    if response.status_code == 200:
        print(f"{order_id} cancel success")
    else:
        print(f"{order_id} cancel failed")

    return order_id


def _collect_one_order(order_id, headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/executeservice/execute/collected/{order_id}"
    response = requests.get(url=url,
                            headers=headers)
    if response.status_code == 200:
        print(f"{order_id} collect success")
    else:
        print(f"{order_id} collect failed")

    return order_id


def _enter_station(order_id, headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/executeservice/execute/execute/{order_id}"
    response = requests.get(url=url,
                            headers=headers)
    if response.status_code == 200:
        print(f"{order_id} enter station success")
    else:
        print(f"{order_id} enter station failed")

    return order_id


def _query_cheapest(travel_date: Optional[str] = None, headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/travelplanservice/travelPlan/cheapest"
    dep = travel_date if travel_date is not None else _today()

    payload = {
        "departureTime": dep,
        "endPlace": "Shang Hai",
        "startingPlace": "Nan Jing"
    }

    r = requests.post(url=url, json=payload, headers=headers)
    if r.status_code == 200:
        print("query cheapest success")
    else:
        print("query cheapest failed")


def _query_min_station(travel_date: Optional[str] = None, headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/travelplanservice/travelPlan/minStation"
    dep = travel_date if travel_date is not None else _today()

    payload = {
        "departureTime": dep,
        "endPlace": "Shang Hai",
        "startingPlace": "Nan Jing"
    }

    r = requests.post(url=url, json=payload, headers=headers)
    if r.status_code == 200:
        print("query min station success")
    else:
        print("query min station failed")


def _query_quickest(travel_date: Optional[str] = None, headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/travelplanservice/travelPlan/quickest"
    dep = travel_date if travel_date is not None else _today()

    payload = {
        "departureTime": dep,
        "endPlace": "Shang Hai",
        "startingPlace": "Nan Jing"
    }

    r = requests.post(url=url, json=payload, headers=headers)
    if r.status_code == 200:
        print("query quickest success")
    else:
        print("query quickest failed")


def _query_admin_basic_price(headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/adminbasicservice/adminbasic/prices"
    response = requests.get(url=url,
                            headers=headers)
    if response.status_code == 200:
        print(f"price success")
        return response
    else:
        print(f"price failed")
        return None


def _query_admin_basic_config(headers: Optional[dict] = None):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/adminbasicservice/adminbasic/configs"
    response = requests.get(url=url,
                            headers=headers)
    if response.status_code == 200:
        print(f"config success")
        return response
    else:
        print(f"config failed")
        return None


def _rebook_ticket(old_order_id, old_trip_id, new_trip_id, new_date, new_seat_type, headers):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/rebookservice/rebook"

    payload = {
        "oldTripId": old_trip_id,
        "orderId": old_order_id,
        "tripId": new_trip_id,
        "date": new_date,
        "seatType": new_seat_type
    }
    print(payload)
    r = requests.post(url=url, json=payload, headers=headers)
    if r.status_code == 200:
        print(r.text)
    else:
        print(f"Request Failed: status code: {r.status_code}")
        print(r.text)


def _query_admin_travel(headers):
    headers = _hdr(headers)
    url = f"{base_address}/api/v1/admintravelservice/admintravel"

    r = requests.get(url=url, headers=headers)
    if r.status_code == 200 and r.json().get("status") == 1:
        print("success to query admin travel")
    else:
        print(f"faild to query admin travel with status_code: {r.status_code}")


if __name__ == '__main__':
    _, token = _login(username="admin", password="222222")
    print(token)
