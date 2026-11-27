#!/usr/bin/env bash
# Quick check that a deployed server works end to end.
# Usage:  CLIENT_SECRET=<secret> bash docs/smoke_test.sh [BASE_URL] [MOBILE]
#   BASE_URL defaults to the AWS server, MOBILE to a test number.
set -u

HOST=${1:-http://13.126.149.116}
MOBILE=${2:-9999900001}
BASE="$HOST/api/v1"
CLIENT_ID=${CLIENT_ID:-finance-mobile-app}
: "${CLIENT_SECRET:?Set CLIENT_SECRET first (API_CLIENT_SECRET from the server .env)}"

j() { python3 -c "import sys,json; d=json.load(sys.stdin); print(eval(sys.argv[1]))" "$1" 2>/dev/null; }
step() { printf '\n== %s\n' "$1"; }

step "1. Health"
curl -s -m 10 "$HOST/health" || { echo "Server not reachable (check security group port 80)"; exit 1; }

step "2. Client token"
R=$(curl -s -X POST "$BASE/auth/token" -H "Content-Type: application/json" \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_secret\":\"$CLIENT_SECRET\"}")
CLIENT_TOKEN=$(echo "$R" | j 'd["data"]["access_token"]')
[ -n "$CLIENT_TOKEN" ] && echo "OK" || { echo "$R"; exit 1; }

step "3. Request OTP (login, or register if the number is new)"
FLOW=login
R=$(curl -s -X POST "$BASE/auth/login/request-otp" -H "Authorization: Bearer $CLIENT_TOKEN" \
  -H "Content-Type: application/json" -d "{\"mobile\":\"$MOBILE\"}")
if echo "$R" | grep -q MOBILE_NOT_REGISTERED; then
  FLOW=register
  R=$(curl -s -X POST "$BASE/auth/register/request-otp" -H "Authorization: Bearer $CLIENT_TOKEN" \
    -H "Content-Type: application/json" -d "{\"mobile\":\"$MOBILE\"}")
fi
echo "$FLOW: $R"

step "4. Verify OTP 123456"
R=$(curl -s -X POST "$BASE/auth/$FLOW/verify-otp" -H "Authorization: Bearer $CLIENT_TOKEN" \
  -H "Content-Type: application/json" -d "{\"mobile\":\"$MOBILE\",\"otp\":\"123456\",\"name\":\"Smoke Test\"}")
TOKEN=$(echo "$R" | j 'd["data"]["access_token"]')
[ -n "$TOKEN" ] && echo "OK, next_step=$(echo "$R" | j 'd["data"]["next_step"]')" || { echo "$R"; exit 1; }

step "5. Current user"
curl -s "$BASE/auth/me" -H "Authorization: Bearer $TOKEN"; echo

step "6. Onboarding status"
curl -s "$BASE/onboarding/status" -H "Authorization: Bearer $TOKEN"; echo

step "7. Advisor status"
curl -s "$BASE/advisor/status" -H "Authorization: Bearer $TOKEN"; echo

step "8. Web app page"
curl -s -o /dev/null -w "GET /app/ -> HTTP %{http_code}\n" "$HOST/app/"

printf '\nAll checks ran.\n'
