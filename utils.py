import random
from typing import List, Tuple
import string


def normalize_route_station_name(name: str) -> str:
    """Align with edu.fudan.common.util.StringUtils.String2Lower (train-ticket ts-common).

    Route.stations use compact lower-case ids (e.g. shanghai, nanjing). Display names
    from ts-station-service (e.g. \"Shang Hai\") must be normalized before trips/left
    or preserve from/to, or indexOf on the route list returns -1 and no trips are found.
    """
    if name is None or name == "":
        return name
    return name.replace(" ", "").lower()


def normalize_place_pair(pair: Tuple[str, str]) -> Tuple[str, str]:
    return (normalize_route_station_name(pair[0]), normalize_route_station_name(pair[1]))


def random_boolean() -> bool:
    return random.choice([True, False])


def random_from_list(l: List):
    if not l:
        raise ValueError("random_from_list: empty sequence")
    return random.choice(l)


def random_form_list(l: List):
    """Alias used by scenario scripts (same as random_from_list)."""
    return random_from_list(l)


def random_from_weighted(d: dict):
    """
    :param d: 带相对权重的字典，eg. {'a': 100, 'b': 50}
    :return: 返回随机选择的key
    """
    total = sum(d.values())    # 权重求和
    ra = random.uniform(0, total)   # 在0与权重和之前获取一个随机数
    curr_sum = 0
    ret = None

    keys = d.keys()
    for k in keys:
        curr_sum += d[k]             # 在遍历中，累加当前权重值
        if ra <= curr_sum:          # 当随机数<=当前权重和时，返回权重key
            ret = k
            break

    return ret


def random_str():
    return ''.join(random.choices(string.ascii_letters, k=random.randint(4, 10)))


def random_phone():
    return ''.join(random.choices(string.digits, k=random.randint(8, 15)))


def random_consignee_phone_cn() -> str:
    """11 位国内手机号样式，与常见校验/字段长度更一致（托运人电话）。"""
    return "1" + "".join(random.choices(string.digits, k=10))
