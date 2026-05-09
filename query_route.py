from atomic_queries import _query_route, auth_headers

if __name__ == '__main__':
    headers = auth_headers()
    if not headers:
        raise SystemExit("login failed")

    _query_route(headers=headers)
