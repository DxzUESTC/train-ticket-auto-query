import time

from atomic_queries import _query_orders_all_info, _put_consign, auth_headers
from utils import random_form_list


def query_one_and_put_consign(headers, pairs):
    """
    查询order并put consign
    """
    pair = random_form_list(pairs)

    order_id = _put_consign(result=pair, headers=headers)
    if not order_id:
        return

    print(f"{order_id} queried and put consign")


if __name__ == '__main__':
    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    pairs = _query_orders_all_info(headers=headers)
    pairs2 = _query_orders_all_info(headers=headers, query_other=True)

    pairs = (pairs or []) + (pairs2 or [])

    for i in range(330):
        try:
            query_one_and_put_consign(headers=headers, pairs=pairs)
            print("*****************************INDEX:" + str(i))
        except Exception as e:
            print(e)

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    print(f"start:{start_time} end:{end_time}")
