import logging
import time

from atomic_queries import _query_admin_basic_config, auth_headers

logger = logging.getLogger("query_admin_basic_config")


def query_admin_basic_config(headers):
    _query_admin_basic_config(headers=headers)


if __name__ == '__main__':
    headers = auth_headers(username="admin", password="222222")
    if not headers:
        raise SystemExit("admin login failed")

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    for i in range(330):
        try:
            query_admin_basic_config(headers=headers)
            print("*****************************INDEX:" + str(i))
        except Exception as e:
            print(e)

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    print(f"start:{start_time} end:{end_time}")
