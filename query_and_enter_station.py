from atomic_queries import auth_headers, _query_orders, _enter_station
from utils import random_form_list

try:
    from traffic_log import detail_indent, tlog
except ImportError:
    def tlog(msg: str, indent: int = 0) -> None:
        print(f"{'  ' * indent}{msg}")

    def detail_indent() -> int:
        return 0


def query_and_enter_station(headers):
    pairs = _query_orders(headers=headers, types=tuple([2]))
    pairs2 = _query_orders(headers=headers, types=tuple([2]), query_other=True)

    if not pairs and not pairs2:
        return

    pairs = pairs + pairs2

    # (orderId, tripId)
    pair = random_form_list(pairs)
    tlog(
        f"enter_station.pick among {len(pairs)} collected → order_id={pair[0]}",
        detail_indent(),
    )

    order_id = _enter_station(order_id=pair[0], headers=headers)
    if not order_id:
        return


if __name__ == '__main__':
    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")
    query_and_enter_station(headers=headers)
