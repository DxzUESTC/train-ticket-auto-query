import atomic_queries as aq
from atomic_queries import _query_orders, _cancel_one_order
from utils import random_form_list

try:
    from traffic_log import detail_indent, tlog
except ImportError:
    def tlog(msg: str, indent: int = 0) -> None:
        print(f"{'  ' * indent}{msg}")

    def detail_indent() -> int:
        return 0


def query_one_and_cancel(headers, uuid=None, pairs=None):
    """
    查询order并取消order
    :param uuid:
    :param headers:
    :param pairs: 可选的 (orderId, tripId) 列表；传入时直接在该列表中随机选一单取消
    :return:
    """
    if pairs is None:
        pairs = _query_orders(headers=headers, types=tuple([0, 1]))
        pairs2 = _query_orders(headers=headers, types=tuple([0, 1]), query_other=True)

        pairs = (pairs or []) + (pairs2 or [])

    if not pairs:
        return

    # (orderId, tripId) pair
    pair = random_form_list(pairs)
    tlog(
        f"cancel.pick among {len(pairs)} orders → order_id={pair[0]} trip_id={pair[1]}",
        detail_indent(),
    )

    uid = uuid if uuid is not None else aq.current_user_id()
    order_id = _cancel_one_order(order_id=pair[0], uid=uid, headers=headers)
    if not order_id:
        return


if __name__ == '__main__':
    from atomic_queries import auth_headers

    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")

    query_one_and_cancel(headers=headers)
