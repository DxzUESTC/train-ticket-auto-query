"""TrainTicket API base URL and departure date for queries.

Aligns with ts-travel-service / ts-travel2-service: TravelServiceImpl.afterToday()
rejects any departure date strictly before the JVM's calendar day (past dates -> empty trips).

So do NOT use historical demo dates like 2021-07-15 when running in 2026 unless you patch the
backend; use 'today' or an explicit future YYYY-MM-DD.

Environment variables:
  TRAIN_TICKET_BASE   Gateway root URL (default: lab NodePort below).
  TRAIN_TICKET_DATE   YYYY-MM-DD, or 'today' / 'tomorrow' (default: today).
  LOAD_THREADS        Worker threads in normal_request_manager.main_thread (default: 5).
                        Use 1 if you see concurrent preserve HTTP 500 from the gateway.
  TRAIN_TICKET_ACCOUNTS_FILE  JSON list of {username, password, userId?}; default
                        uestc_loadtest_accounts.json beside this package. Run
                        register_uestc_loadtest_accounts.py once to create users and refresh userIds.
"""

import os
from datetime import date as dt_date
from datetime import timedelta

BASE_URL = os.environ.get(
    "TRAIN_TICKET_BASE",
    "http://192.168.100.11:30467",
).rstrip("/")

_raw_date = os.environ.get("TRAIN_TICKET_DATE", "today").strip()
_lower = _raw_date.lower()
if _lower == "today":
    DEPARTURE_DATE = dt_date.today().isoformat()
elif _lower == "tomorrow":
    DEPARTURE_DATE = (dt_date.today() + timedelta(days=1)).isoformat()
else:
    DEPARTURE_DATE = _raw_date
