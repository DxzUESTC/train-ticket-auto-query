# train-ticket-auto-query

Train Ticket Auto Query Python Scripts

## Environment

| Variable | Meaning |
|----------|---------|
| `TRAIN_TICKET_BASE` | Gateway root URL (default `http://192.168.100.11:30467`) |
| `TRAIN_TICKET_DATE` | `today`, `tomorrow`, or `YYYY-MM-DD` (default `today`; must satisfy backend `afterToday` in travel services) |

## Seed routes (aligned with upstream `train-ticket`)

Simulated traffic uses **only** origin–destination pairs that exist in upstream seed data (`seed_od.py`):

- **High speed** (`/api/v1/travelservice/trips/left`): from `ts-travel-service/.../travel/init/InitData.java` — e.g. **Shang Hai ↔ Su Zhou** (G/D trips first segment).
- **Normal** (`/api/v1/travel2service/trips/left`): from `ts-travel2-service/.../travel2/init/InitData.java` — e.g. **Shang Hai ↔ Nan Jing** (Z/T/K trips first segment).

There is no seed data for arbitrary cities (e.g. Haikou); empty trip lists for other OD are expected.

## How to use

```python
import logging
from queries import Query
from scenarios import query_and_preserve

# login train-ticket and store the cookies
q = Query(url)
if not q.login():
    logging.fatal('login failed')

# execute scenario on current user
query_and_preserve(q)

# or execute query directly
q.query_high_speed_ticket()
```
