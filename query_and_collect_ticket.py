from atomic_queries import auth_headers, _query_orders, _collect_one_order
from utils import random_form_list


def query_and_collect_ticket(headers):

    pairs = _query_orders(headers=headers, types=tuple([1]))
    pairs2 = _query_orders(headers=headers, types=tuple([1]), query_other=True)

    if not pairs and not pairs2:
        return

    pairs = pairs + pairs2

    # (orderId, tripId)
    pair = random_form_list(pairs)

    order_id = _collect_one_order(order_id=pair[0], headers=headers)
    if not order_id:
        return


if __name__ == '__main__':
    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")
    query_and_collect_ticket(headers=headers)
