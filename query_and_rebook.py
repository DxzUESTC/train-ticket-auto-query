from atomic_queries import _query_orders, _rebook_ticket, auth_headers

import time


def query_and_rebook(headers):

    pairs = _query_orders(headers=headers, types=tuple([1]))
    if not pairs:
        return

    new_trip_id = "D1345"
    new_date = time.strftime("%Y-%m-%d", time.localtime())
    new_seat_type = "3"

    for pair in pairs:
        _rebook_ticket(old_order_id=pair[0], old_trip_id=pair[1], new_trip_id=new_trip_id,
                       new_date=new_date, new_seat_type=new_seat_type, headers=headers)


if __name__ == '__main__':
    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    query_and_rebook(headers=headers)

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    print(f"start:{start_time} end:{end_time}")
