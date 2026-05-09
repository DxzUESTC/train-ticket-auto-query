import time

from atomic_queries import _query_orders, _pay_one_order, auth_headers
from utils import random_form_list


def query_order_and_pay(headers, pairs):
    """
    查询Order并付款未付款Order
    :return:
    """

    if not pairs:
        return

    # (orderId, tripId) pair
    pair = random_form_list(pairs)

    order_id = _pay_one_order(pair[0], pair[1], headers=headers)
    if not order_id:
        return

    print(f"{order_id} queried and paid")


if __name__ == '__main__':
    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    pairs = _query_orders(headers=headers, types=tuple([0, 1]))
    pairs2 = _query_orders(headers=headers, types=tuple([0, 1]), query_other=True)

    pairs = (pairs or []) + (pairs2 or [])

    for i in range(330):
        try:
            query_order_and_pay(headers=headers, pairs=pairs)
            print("*****************************INDEX:" + str(i))
        except Exception as e:
            print(e)

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    print(f"start:{start_time} end:{end_time}")
