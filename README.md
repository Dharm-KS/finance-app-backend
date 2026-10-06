# Finance Friend — Backend (MVP)

FastAPI backend for an AI-powered "financial friend" mobile app. It's a modular monolith: async FastAPI, SQLAlchemy 2.x, MySQL 8, Alembic and JWT, with OTP login on the mobile number.

External integrations (CIBIL, a real OTP provider, equity APIs, AI analysis) sit behind provider interfaces. For now they're dummy or mock implementations.

---

## 1. Project structure

```
finance-app-backend/
├── app/
│   ├── main.py                     # app factory, CORS, error handlers, /docs
│   ├── core/
│   │   ├── config.py               # settings from env / .env
│   │   ├── database.py             # async engine + get_db dependency
│   │   ├── security.py             # JWT + OTP hashing
│   │   ├── exceptions.py           # AppError + standard error envelope
│   │   └── time.py                 # UTC helpers
│   ├── models/                     # SQLAlchemy models (one file per aggregate)
│   │   ├── base.py                 # Base, naming convention, Money/Percent/UTCDateTime types
│   │   ├── enums.py                # all domain enums
│   │   ├── user.py                 # User, RevokedToken
│   │   ├── otp.py  consent.py  onboarding.py  credit_report.py  credit_account.py
│   │   └── financial_profile.py  equity.py  risk_profile.py  goal.py
│   ├── schemas/                    # Pydantic v2 request/response models
│   │   ├── common.py               # ApiResponse[T], Money/Percent types, error docs
│   │   └── auth.py consent.py onboarding.py credit.py financial.py equity.py risk.py goal.py dashboard.py
│   ├── api/                        # thin routers: validate -> call service -> wrap response
│   │   ├── deps.py                 # DbSession, CurrentUser, Client deps
│   │   ├── router.py
│   │   └── auth.py consent.py onboarding.py credit.py financial.py equity.py risk.py goals.py dashboard.py
│   ├── services/                   # all business logic
│   │   ├── auth_service.py  otp_service.py  consent_service.py  onboarding_service.py
│   │   ├── credit_service.py  financial_service.py  equity_service.py  risk_service.py
│   │   ├── goal_service.py  dashboard_service.py
│   │   ├── insights.py             # pluggable InsightEngine (rule-based today, AI later)
│   │   └── providers/
│   │       ├── otp.py              # OtpProvider  -> FixedOtpProvider (123456)
│   │       ├── equity.py           # EquityProvider -> ManualEquityProvider
│   │       └── credit/
│   │           ├── base.py         # CreditProvider contract + normalised dataclasses
│   │           └── dummy.py        # DummyCreditProvider + 3 dummy bureau profiles
│   └── seed/dummy_data.py
├── alembic/  (env.py is async; versions/…_initial_migration.py)
├── tests/    (pytest; in-memory SQLite, no MySQL needed)
├── .env.example  requirements.txt  alembic.ini  pytest.ini  README.md
```

**Layering rule:** routes don't contain business logic, and services don't know about HTTP. Models (SQLAlchemy) and schemas (Pydantic) are kept separate.

---

## 2. Setup

Requires **Python 3.12+** and **MySQL 8**.

```bash
cd finance-app-backend
python3.12 -m venv .venv          # or: uv venv --python 3.12 .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Generate a JWT secret and paste it into `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Create the MySQL database and user:

```sql
CREATE DATABASE finance_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'finance_user'@'localhost' IDENTIFIED BY 'change-me';
GRANT ALL PRIVILEGES ON finance_app.* TO 'finance_user'@'localhost';
```

### Environment variables

| Variable | Example | Notes |
|---|---|---|
| `DATABASE_URL` | `mysql+aiomysql://finance_user:pw@localhost:3306/finance_app?charset=utf8mb4` | Must use an async driver (`aiomysql`) |
| `JWT_SECRET` | 64+ random chars | Required (min 32 chars) |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | User token lifetime (7 days) |
| `API_CLIENT_ID` | `finance-mobile-app` | Client credentials for `POST /auth/token` |
| `API_CLIENT_SECRET` | 32+ random chars | Required (min 16 chars) |
| `CLIENT_TOKEN_EXPIRE_MINUTES` | `60` | Client token lifetime |
| `OTP_PROVIDER` | `fixed` | MVP: OTP is always `123456` |
| `OTP_EXPIRY_SECONDS` | `300` | |
| `OTP_MAX_ATTEMPTS` | `5` | The session locks after this many wrong attempts |
| `OTP_RESEND_COOLDOWN_SECONDS` | `30` | Minimum gap between resends |
| `OTP_MAX_SENDS_PER_WINDOW` | `5` | Max OTPs per mobile in the window (`OTP_LIMIT_REACHED`) |
| `OTP_SEND_WINDOW_SECONDS` | `3600` | |
| `CREDIT_PROVIDER` | `dummy` | Later: `cibil` |
| `CORS_ORIGINS` | `*` | Comma separated |
| `ENVIRONMENT`, `DEBUG`, `APP_NAME` | | |

## 3. Migrations

The initial migration is already in `alembic/versions/`.

```bash
alembic upgrade head                                    # create all tables
alembic revision --autogenerate -m "describe change"    # after changing models
alembic downgrade -1                                    # roll back one revision
alembic upgrade head --sql                              # print the SQL instead of running it
```

## 4. Seed data

```bash
python -m app.seed.dummy_data           # idempotent: skips users that already exist
python -m app.seed.dummy_data --reset   # delete the seed users and recreate them
```

| Mobile | Name | Credit | Onboarding state |
|---|---|---|---|
| 9876543210 | Aarav Sharma | 780 (good) | COMPLETED: full profile, 2 equity rows, risk, 4 goals, single-stock concentration alert |
| 9876543215 | Priya Nair | 692 (average) | Next step `EQUITY` (use this to test resuming onboarding) |
| 9876543218 | Rohan Verma | 615 (risky) | Next step `FINANCIAL_PROFILE` (prefill from credit report) |

Log in with any of these numbers and OTP **123456**.

## 5. Run

```bash
uvicorn app.main:app --reload
```

- Swagger UI: http://localhost:8000/docs. Call `POST /auth/token` first, click **Authorize** and paste its token for the OTP endpoints, then paste the user token from `verify-otp` for the rest.
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

### Run with Docker (API + MySQL)

You don't need Python or MySQL installed; Docker runs both. Fill in the "Docker" section of `.env`, then:

```bash
docker compose up -d --build
```

- The API listens on `http://<host>:${API_PORT}` (default 80). MySQL isn't published to the host.
- Migrations run automatically every time the container starts. Data lives in the `mysql_data` volume.
- To load test users, run `docker compose exec api python -m app.seed.dummy_data`.
- For logs, run `docker compose logs -f api`.
- To update after a `git pull`, run `docker compose up -d --build` again.

## 6. Tests

```bash
pytest -q
```

The 95 tests run against an in-memory SQLite database, so you don't need MySQL. They cover:
- registration, login, invalid, expired and locked OTPs, and the OTP being single-use
- `/me`, logout and token revocation
- consent and its audit trail
- credit fetch (all 3 profiles, no-hit, duplicate fetch, missing consent)
- financial profile prefill, GET/PUT and validation
- equity, risk and goal CRUD and validation
- goal calculations, onboarding progression and the dashboard
- 401 on all 28 protected endpoints, plus client vs user token separation
- cross-user isolation

---

## 7. API

> **Full reference with curl examples for every endpoint:** the shared [Finance Friend API Reference](https://claude.ai/code/artifact/409f73bb-9e7f-4c08-8141-fa8f8e330c25) (linked from [docs/API.md](docs/API.md)).
> Onboarding order after OTP: Money → Equity → Risk → Goals → Preferences → COMPLETED.
> To run the entire flow against a running server: `./docs/api_examples.sh`.

Every endpoint needs `Authorization: Bearer <token>`:

- The 4 OTP endpoints take a **client token**, from `POST /auth/token` with `client_id` + `client_secret`.
- Everything else takes the **user token** returned by `verify-otp`.

**Response envelope**

```json
{ "success": true,  "data": { ... }, "message": "Financial profile fetched successfully" }
{ "success": false, "message": "Credit consent is required", "error_code": "CONSENT_REQUIRED" }
```

Validation errors (422) also include `errors: [{field, message, type}]`. Submitted values are never echoed back. Monetary values are JSON numbers. Internally they're `Decimal` and stored as `DECIMAL(18,2)`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/token` | – (client credentials) | Create the auth (client) token |
| POST | `/api/v1/auth/register/request-otp` | client | Send OTP to a new mobile (409 if already registered) |
| POST | `/api/v1/auth/register/verify-otp` | client | Verify OTP, create user (with optional `name`), return JWT and `next_step` |
| POST | `/api/v1/auth/login/request-otp` | client | Send OTP to a registered mobile (404 if unknown) |
| POST | `/api/v1/auth/login/verify-otp` | client | Verify OTP, return JWT and `next_step` |
| POST | `/api/v1/auth/logout` | ✔ | Revoke the current token |
| GET | `/api/v1/auth/me` | ✔ | Current user |
| PATCH | `/api/v1/auth/me` | ✔ | Set name/email (completes the `REGISTRATION` step) |
| GET | `/api/v1/onboarding/status` | ✔ | Step flags and `current_step` to resume at |
| POST | `/api/v1/onboarding/skip` | ✔ | Skip an optional step (`EQUITY`) |
| GET | `/api/v1/consents` | ✔ | Current status per type and full history |
| POST | `/api/v1/consents` | ✔ | Grant or revoke (append-only) |
| POST | `/api/v1/credit/fetch` | ✔ | Pull the report from the provider (needs `CREDIT_REPORT` consent) |
| GET | `/api/v1/credit/report` | ✔ | Latest report, summary and accounts |
| GET | `/api/v1/credit/accounts` | ✔ | Normalised accounts |
| GET | `/api/v1/financial-profile` | ✔ | Saved profile, or a form prefilled from the credit report |
| PUT | `/api/v1/financial-profile` | ✔ | Create or replace |
| GET/POST | `/api/v1/equity` | ✔ | List or add holdings |
| PUT/DELETE | `/api/v1/equity/{id}` | ✔ | Update (partial) or delete |
| GET/PUT | `/api/v1/risk-profile` | ✔ | Get or upsert risk settings |
| GET/PUT | `/api/v1/preferences` | ✔ | Insight tone and alert switches (last onboarding step) |
| GET/POST | `/api/v1/goals` | ✔ | List or create (targets calculated automatically) |
| GET | `/api/v1/goals/suggestions` | ✔ | The 9 goal cards with calculated targets |
| PUT | `/api/v1/goals/selection` | ✔ | Save the ticked goal cards in one call |
| PUT/DELETE | `/api/v1/goals/{id}` | ✔ | Update (partial) or delete |
| GET | `/api/v1/dashboard` | ✔ | Consolidated summary and alerts |

### Example flow (curl)

```bash
B=http://localhost:8000/api/v1

CT=$(curl -s -X POST $B/auth/token -H 'content-type: application/json' \
     -d '{"client_id":"finance-mobile-app","client_secret":"<API_CLIENT_SECRET>"}' | jq -r .data.access_token)

curl -X POST $B/auth/register/request-otp -H "Authorization: Bearer $CT" -H 'content-type: application/json' -d '{"mobile":"9812345670"}'
# {"success":true,"data":{"otp_session_id":"…","mobile":"+919812345670","expires_in_seconds":300,"resend_after_seconds":30},"message":"OTP sent successfully"}

curl -X POST $B/auth/register/verify-otp -H "Authorization: Bearer $CT" -H 'content-type: application/json' \
     -d '{"mobile":"9812345670","otp":"123456","name":"Aarav Sharma"}'
# {"success":true,"data":{"access_token":"eyJ…","token_type":"bearer","expires_at":"…",
#   "user":{…},"is_new_user":true,"next_step":"CONSENT","onboarding_completed":false},"message":"Registration successful"}

TOKEN=eyJ...
curl -X POST $B/consents -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"consent_type":"CREDIT_REPORT","consent_version":"v1"}'
curl -X POST $B/credit/fetch      -H "Authorization: Bearer $TOKEN"    # score 780 (mobile ends in 0)
curl        $B/financial-profile  -H "Authorization: Bearer $TOKEN"    # total_debt / monthly_emi prefilled
curl -X PUT $B/financial-profile  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"annual_income":3600000,"currency":"INR","monthly_spend":65000,"cash_reserve":450000,"monthly_emi":27950,
          "total_debt":682000,"investments":1200000,"employment_type":"SALARIED","age":32,"dependents":1}'
curl -X POST $B/equity -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"employer_name":"Acme","security_name":"Acme Inc.","ticker":"ACME","vested_value":2500000,"unvested_value":1200000}'
curl -X PUT $B/risk-profile -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"risk_tolerance":"BALANCED","max_drawdown_percent":18,"single_stock_limit_percent":35,"planning_horizon_years":10}'
curl -X POST $B/goals -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"goal_type":"EMERGENCY_FUND","priority":"ESSENTIAL"}'   # target = 6 x 65,000 = 390,000
curl $B/dashboard -H "Authorization: Bearer $TOKEN"
```

Example dashboard response (seed user Aarav):

```json
{
  "success": true,
  "data": {
    "currency": "INR", "net_worth": 3618000, "cash": 450000, "investments": 1200000,
    "equity": 2650000, "unvested_equity": 1200000, "debt": 682000, "monthly_emi": 27950,
    "credit_score": 780, "emergency_fund_months": 6.92,
    "top_concentration": {"security_name": "Acme Technologies Inc.", "ticker": "ACME", "value": 2650000,
                          "percent_of_net_worth": 73.24, "limit_percent": 35, "above_limit": true},
    "risk": {"profile": "BALANCED", "max_drawdown": 18, "single_stock_limit": 35, "planning_horizon_years": 10},
    "goals": {"total": 4, "active": 4, "completed": 0, "at_risk": 1},
    "alerts": [{"code": "SINGLE_STOCK_ABOVE_LIMIT", "severity": "WARNING", "title": "Single-stock concentration is high",
                "message": "Acme Technologies Inc. is 73.24% of your net worth; your limit is 35%."}, "…"],
    "onboarding_step": "COMPLETED"
  },
  "message": "Dashboard fetched successfully"
}
```

---

## 8. Database schema

```
users ─┬─< otp_sessions        (user_id nullable: the user doesn't exist yet at registration)
       ├─< revoked_tokens      (JWT denylist for logout)
       ├─< consents            (append-only audit log)
       ├── onboarding          (1:1, unique user_id)
       ├─< credit_reports ──< credit_accounts
       ├── financial_profiles  (1:1)
       ├─< equity_holdings
       ├── risk_profiles       (1:1, CHECK constraints on ranges)
       └─< financial_goals
```

- Primary keys are `BIGINT AUTO_INCREMENT`. Only `users.uuid` is exposed publicly (it's the JWT `sub`).
- Every child table has an FK with `ON DELETE CASCADE` back to `users`. Deleting a user removes all of their data.
- Unique keys: `users.mobile`, `users.uuid`, `users.email`, `otp_sessions.uuid`, `credit_reports.report_reference`, `revoked_tokens.jti`, and `user_id` on the 1:1 tables.
- Indexes:
  - `otp_sessions(mobile, purpose, status)`
  - `consents(user_id, consent_type, created_at)`
  - `credit_reports(user_id, created_at)`
  - `financial_goals(user_id, status)`
  - every FK
- Money is `DECIMAL(18,2)`, percentages are `DECIMAL(5,2)`, and timestamps are `DATETIME` in UTC.
- Enums are stored as `VARCHAR` rather than native `ENUM`, so adding a value doesn't need an `ALTER TABLE`. They're still validated in the app.
- `credit_reports.raw_report` (JSON) holds the untouched bureau payload. It's deferred-loaded and never returned by the API. The normalised data lives in `credit_accounts`.

---

## 9. Design decisions and assumptions

**Auth and OTP**
- **Mobile numbers:** Indian numbers only for the MVP. They're normalised to E.164 (`+91XXXXXXXXXX`), and inputs like `9876543210`, `+91 98765 43210` and `09876543210` are all accepted.
- **Fixed OTP:** the MVP OTP is always `123456`, issued by `FixedOtpProvider`. To add real SMS, implement `OtpProvider` and register it in `get_otp_provider()`. The API doesn't change.
- **OTP storage:** OTPs are stored only as an HMAC (keyed with `JWT_SECRET`, salted with the session uuid). They're never logged and never returned.
- **OTP rules:**
  - Only the newest OTP for a mobile/purpose pair is valid. Older ones are marked `SUPERSEDED`.
  - An OTP can be used once.
  - After 5 wrong attempts the session moves to `LOCKED` (HTTP 429).
  - Expiry returns 400 `OTP_EXPIRED`.
  - Resending is limited by a 30-second cooldown and a cap of 5 OTPs per mobile per hour. Both 429 responses include `retry_after_seconds` and a `Retry-After` header.
- **Name during registration:** the API contract has no separate "set name" endpoint, so `verify-otp` accepts an optional `name`. If the app collects the name on its own screen after the OTP, it calls `PATCH /auth/me`. Until then, `next_step` stays `REGISTRATION`.
- **Logout:** JWTs are stateless, so logout adds the token's `jti` to `revoked_tokens`, which is checked on every request. Rows can be purged once `expires_at` passes. There are no refresh tokens yet; a 7-day access token is the MVP trade-off.
- **Mobile enumeration:** register returns 409 for a known number and login returns 404 for an unknown one, as the spec requires. Add rate limiting at the gateway before going to production.

**Consent and credit**
- **Consent text:** the server owns it, through `CONSENT_CATALOG`. The client sends type and version, and the server stores the exact purpose text the user agreed to, plus IP and user agent.
- **Consent history:** revoking inserts a new row, so history is never lost.
- **Credit step:** onboarding's consent step only needs `CREDIT_REPORT`. Credit fetch is blocked (403) unless the latest `CREDIT_REPORT` consent is `GRANTED`.
- **Dummy credit profile:** chosen by the last digit of the mobile number, so tests are deterministic:
  - 0–3 → 780
  - 4–6 → 692
  - 7–9 → 615
  - a number ending `0000` → no bureau record (404 `CREDIT_REPORT_UNAVAILABLE`)
- **Credit reports:** one successful report per user. A second fetch returns 409 `CREDIT_REPORT_ALREADY_EXISTS`. Refresh support can come later.
- **`dpd`:** this is the highest days-past-due in the account's history, which is how the "historical DPD" requirement is represented. Recent enquiries stay in `raw_report`.

**Financial profile and equity**
- **Prefill:** if no profile has been saved, `GET /financial-profile` returns `is_saved=false` with `total_debt` and `monthly_emi` filled from active credit accounts. Those fields are listed in `prefilled_fields`. Nothing is saved until the user sends a PUT, so they can edit everything.
- **Updates:** financial profile PUT is a full replacement. Equity and goal PUTs are partial updates. Profiles are single upserted rows per user.
- **Equity:** holdings are entered manually (`source=MANUAL`) and a user can have several. Equity is optional; users without employer stock call `POST /onboarding/skip {"step":"EQUITY"}`.

**Calculations** (`goal_service`, `financial_service`)
- **Net worth** = cash reserve + investments + vested equity − total debt. Unvested equity isn't counted because it isn't owned yet. It's reported separately.
- **Concentration:** the largest single stock (holdings grouped by ticker) divided by net worth. If net worth is 0 or less, it counts as above any limit. When there's no risk profile, the limit defaults to 35%.
- **Goal targets:**
  - **Emergency fund:** 6 × monthly spend. `current_amount` defaults to the cash reserve, capped at the target.
  - **Equity tax reserve:** 30% of unvested equity. Upcoming vests are taxed as perquisites, and 30% is an assumption you can configure in `goal_service`.
  - **Concentration:** the target is the value to diversify, which is position − limit% × net worth.
  - **Home down payment:** the user must supply `target_amount`.
- **At risk:** a goal is flagged when any of these is true:
  - it's a concentration goal and the stock is above its limit
  - the target date has passed
  - progress lags elapsed time by more than 10 points
  - it's an emergency fund and the cash reserve covers less than 3 months of spending
- **Currency:** all amounts are assumed to be in the profile's reporting currency. Holdings in another currency are left out of totals, with an info alert, until FX support is added.

**Onboarding**
- **Status:** onboarding status is derived from real data on each change. Flags are sticky: once true they stay true.
- **Current step:** `current_step` is the first incomplete step, which makes resuming reliable.
- **One row per user:** this is enforced by a unique constraint plus race-safe get-or-create.

**Errors and data**
- **Other users' resources:** accessing another user's resource returns **404**, not 403, so the response doesn't reveal that the resource exists. Ownership is part of every query (`WHERE id = ? AND user_id = ?`).
- **Transactions:** each service call is one unit of work and commits once. Failed OTP attempts are committed before raising, so attempt counts persist.

## 10. Extension points

| Future integration | Where it plugs in |
|---|---|
| CIBIL / other bureau | Implement `CreditProvider` (`services/providers/credit/`) and register it in `get_credit_provider()`; set `CREDIT_PROVIDER=cibil` |
| Real OTP (SMS/WhatsApp) | Implement `OtpProvider` (`services/providers/otp.py`) |
| Equity / broker / market-price APIs | Implement `EquityProvider` (`services/providers/equity.py`) and add new `EquitySource` values |
| Account Aggregator / bank data | New provider + service that feeds `FinancialSnapshot` |
| AI financial analysis | Implement `InsightEngine` (`services/insights.py`); it receives the same `FinancialSnapshot` |
| Notifications | New service that consumes alerts from `InsightEngine` |
