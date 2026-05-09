"""TrainTicket API base URL (Spring Cloud Gateway NodePort). Override with env TRAIN_TICKET_BASE."""

import os

BASE_URL = os.environ.get(
    "TRAIN_TICKET_BASE",
    "http://192.168.100.11:30467",
).rstrip("/")
