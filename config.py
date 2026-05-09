"""TrainTicket API base URL and departure date for queries.

Environment variables:
  TRAIN_TICKET_BASE   Gateway root URL (default: lab NodePort below).
  TRAIN_TICKET_DATE   YYYY-MM-DD for trip queries, or the word 'today'.
                      Default 2021-07-15 matches common TrainTicket seed/demo data;
                      using 'today' often yields no trips if the DB has no rows for that date.
"""

import os
from datetime import date as dt_date

BASE_URL = os.environ.get(
    "TRAIN_TICKET_BASE",
    "http://192.168.100.11:30467",
).rstrip("/")

_raw_date = os.environ.get("TRAIN_TICKET_DATE", "2021-07-15").strip()
if _raw_date.lower() == "today":
    DEPARTURE_DATE = dt_date.today().isoformat()
else:
    DEPARTURE_DATE = _raw_date
