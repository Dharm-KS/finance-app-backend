#!/usr/bin/env bash
# Walks through the app's API flow against a running server: auth token -> OTP -> the 5 calibration
# screens -> dashboard. The API reference itself is the shared doc linked from docs/API.md.
#
#   ./docs/api_examples.sh                       # http://localhost:8000
#   BASE_URL=http://host:port ./docs/api_examples.sh
#   MOBILE=9812345670 ./docs/api_examples.sh     # pick the number (last digit selects the credit profile)
#
# Client credentials come from API_CLIENT_ID / API_CLIENT_SECRET in the environment, else from ./.env.
#
# A fresh random mobile is used by default, so the script can be re-run.
# Requires: curl, python3 (for JSON pretty-printing / field extraction).

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
BASE="$BASE_URL/api/v1"
MOBILE="${MOBILE:-98$(printf '%07d' $((RANDOM * RANDOM % 10000000)))0}"
OTP="123456"
JSON='Content-Type: application/json'
env_value() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2-; }
CLIENT_ID="${API_CLIENT_ID:-$(env_value API_CLIENT_ID)}"
CLIENT_SECRET="${API_CLIENT_SECRET:-$(env_value API_CLIENT_SECRET)}"
[[ -n "$CLIENT_ID" && -n "$CLIENT_SECRET" ]] || { echo "Set API_CLIENT_ID / API_CLIENT_SECRET (or run from the project root with a .env)"; exit 1; }

pretty() { python3 -m json.tool 2>/dev/null || cat; }
field()  { python3 -c "import sys,json; d=json.load(sys.stdin); print(eval('d' + sys.argv[1]))" "$1"; }

# call LABEL METHOD PATH [BODY] - prints status + pretty JSON, stores body in $LAST
call() {
  local label=$1 method=$2 path=$3 body=${4:-}
  local args=(-s -w '\n%{http_code}' -X "$method" "$BASE$path")
  [[ -n "${TOKEN:-}" ]] && args+=(-H "Authorization: Bearer $TOKEN")
  [[ -n "$body" ]] && args+=(-H "$JSON" -d "$body")
  local out; out=$(curl "${args[@]}")
  local status=${out##*$'\n'}
  LAST=${out%$'\n'*}
  printf '\n\033[1;34m== %s\033[0m  %s %s  ->  \033[1m%s\033[0m\n' "$label" "$method" "$path" "$status"
  echo "$LAST" | pretty
}

curl -sf "$BASE_URL/health" >/dev/null || { echo "Server not reachable at $BASE_URL (start it with: uvicorn app.main:app)"; exit 1; }
echo "Using mobile $MOBILE against $BASE"

# ---- 0. Create auth token (client token for the OTP endpoints) --------------------------------
TOKEN=""
call "0.1 Create auth token: wrong secret (401)" POST /auth/token "{\"client_id\":\"$CLIENT_ID\",\"client_secret\":\"wrong\"}"
call "0.1 Create auth token" POST /auth/token "{\"client_id\":\"$CLIENT_ID\",\"client_secret\":\"$CLIENT_SECRET\"}"
CLIENT_TOKEN=$(echo "$LAST" | field "['data']['access_token']")

# ---- 1. Auth (OTP endpoints use the client token, everything after uses the user token) ------
TOKEN=""
call "1.1 Register without token (401)" POST /auth/register/request-otp "{\"mobile\":\"$MOBILE\"}"
TOKEN=$CLIENT_TOKEN
call "1.1 Register: request OTP" POST /auth/register/request-otp "{\"mobile\":\"$MOBILE\"}"
call "1.2 Register: wrong OTP (400)" POST /auth/register/verify-otp "{\"mobile\":\"$MOBILE\",\"otp\":\"000000\"}"
call "1.2 Register: verify OTP" POST /auth/register/verify-otp "{\"mobile\":\"$MOBILE\",\"otp\":\"$OTP\",\"name\":\"Aarav Sharma\"}"
call "1.1 Register again (409)" POST /auth/register/request-otp "{\"mobile\":\"$MOBILE\"}"

call "1.3 Login: request OTP" POST /auth/login/request-otp "{\"mobile\":\"$MOBILE\"}"
call "1.4 Login: verify OTP" POST /auth/login/verify-otp "{\"mobile\":\"$MOBILE\",\"otp\":\"$OTP\"}"
TOKEN=$(echo "$LAST" | field "['data']['access_token']")

call "1.5 Me" GET /auth/me
call "1.6 Update me" PATCH /auth/me '{"name":"Aarav Sharma"}'

SAVED=$TOKEN; TOKEN=""
call "1.5 Me without token (401)" GET /auth/me
TOKEN=$SAVED

# ---- Calibration: Money -> Equity -> Risk -> Goals -> Preferences ----------------------------
NEXT_VEST=$(date -d "+60 days" +%Y-%m-%d 2>/dev/null || date -v+60d +%Y-%m-%d)
call "Onboarding status (FINANCIAL_PROFILE)" GET /onboarding/status

call "Step 1 Money: load" GET /financial-profile
call "Step 1 Money: missing fields (422)" PUT /financial-profile '{"annual_income":6000000}'
call "Step 1 Money: save" PUT /financial-profile '{"annual_income":6000000,"monthly_spend":260000,"cash_reserve":1850000,"currency":"INR"}'

call "Step 2 Equity: add" POST /equity "{\"employer_name\":\"Helio Systems\",\"ticker\":\"HELO\",\"vested_value\":2500000,\"unvested_value\":1200000,\"next_vest_date\":\"$NEXT_VEST\"}"
EQUITY_ID=$(echo "$LAST" | field "['data']['id']")
call "Step 2 Equity: list" GET /equity
call "Step 2 Equity: update" PUT "/equity/$EQUITY_ID" '{"vested_value":2650000}'
call "Step 2 Equity: missing holding (404)" PUT /equity/999999 '{"vested_value":1}'

call "Step 3 Risk: load (404 before save)" GET /risk-profile
call "Step 3 Risk: out of range (422)" PUT /risk-profile '{"risk_tolerance":"BALANCED","max_drawdown_percent":120,"single_stock_limit_percent":35,"planning_horizon_years":60}'
call "Step 3 Risk: save" PUT /risk-profile '{"risk_tolerance":"BALANCED","max_drawdown_percent":18,"single_stock_limit_percent":35,"planning_horizon_years":10}'

call "Step 4 Goals: cards" GET /goals/suggestions
call "Step 4 Goals: home without input (422)" PUT /goals/selection '{"goals":[{"goal_type":"EMERGENCY_FUND"},{"goal_type":"HOME_DOWN_PAYMENT"}]}'
call "Step 4 Goals: save selection" PUT /goals/selection '{"goals":[
  {"goal_type":"EMERGENCY_FUND"},{"goal_type":"EQUITY_TAX_RESERVE"},{"goal_type":"REDUCE_SINGLE_STOCK_CONCENTRATION"},
  {"goal_type":"RETIREMENT_CORPUS"},{"goal_type":"PROTECTION_TOPUP"},
  {"goal_type":"HOME_DOWN_PAYMENT","inputs":{"property_value":15000000}}]}'
GOAL_ID=$(echo "$LAST" | field "['data']['goals'][-1]['id']")
call "Goals: edit one" PUT "/goals/$GOAL_ID" '{"current_amount":400000}'
call "Goals: list" GET /goals

call "Step 5 Preferences: defaults" GET /preferences
call "Step 5 Preferences: save" PUT /preferences '{"insight_tone":"BALANCED","vesting_alerts":true,"tax_deadline_alerts":true,"weekly_digest":false}'
call "Onboarding status (COMPLETED)" GET /onboarding/status
call "Dashboard" GET /dashboard

# ---- Cleanup / delete + logout -------------------------------------------------------------
call "Delete goal" DELETE "/goals/$GOAL_ID"
call "Delete equity" DELETE "/equity/$EQUITY_ID"
call "1.7 Logout" POST /auth/logout
call "1.5 Me after logout (401)" GET /auth/me

echo -e "\nDone. Registered user: $MOBILE"
