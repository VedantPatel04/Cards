#!/usr/bin/env bash
#
# End-to-end demo flow — the Postman collection, automated.
#
#   ./scripts/demo_flow.sh                 # seeds, then runs every step
#   ./scripts/demo_flow.sh --no-setup      # skip manage.py setup_dev
#   BASE_URL=http://127.0.0.1:8001 ./scripts/demo_flow.sh
#
# Requires a running dev server (python manage.py runserver) plus curl + jq.
# Exits non-zero if any assertion fails, so it doubles as a smoke test.

set -uo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
USERNAME="${USERNAME:-user1}"
EMAIL="${EMAIL:-user1@example.com}"
PASSWORD="${PASSWORD:-user1Password}"
RUN_SETUP=1
[[ "${1:-}" == "--no-setup" ]] && RUN_SETUP=0

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
SAMPLES="$BACKEND_DIR/data/sample_uploads"
STATEMENTS=("$SAMPLES/Chase_MAY_Transactions.csv" "$SAMPLES/Chase Transaction Statement.csv")

PASS=0
FAIL=0
BODY=""
HTTP_CODE=""
ACCESS=""

step()  { printf '\n=== %s ===\n' "$1"; }
ok()    { printf '  [OK]   %s\n' "$1"; PASS=$((PASS + 1)); }
bad()   { printf '  [FAIL] %s\n' "$1"; FAIL=$((FAIL + 1)); }
info()  { printf '         %s\n' "$1"; }
die()   { printf '\nAborted: %s\n' "$1" >&2; exit 2; }

# Sets BODY + HTTP_CODE. Must not be called in a subshell or the globals are lost.
api() {
  local method="$1" path="$2" raw
  shift 2
  raw="$(curl -sS -X "$method" "$BASE_URL$path" -w $'\n%{http_code}' "$@")" || {
    BODY=""; HTTP_CODE="000"; return 1
  }
  HTTP_CODE="$(tail -n1 <<<"$raw")"
  BODY="$(sed '$d' <<<"$raw")"
}

auth_api() {
  local method="$1" path="$2"
  shift 2
  api "$method" "$path" -H "Authorization: Bearer $ACCESS" "$@"
}

expect_code() {  # label expected_csv
  local label="$1" expected="$2"
  if [[ ",$expected," == *",$HTTP_CODE,"* ]]; then
    ok "$label (HTTP $HTTP_CODE)"
  else
    bad "$label — expected $expected, got $HTTP_CODE"
    info "$(head -c 300 <<<"$BODY")"
  fi
}

check() {  # label jq_filter  (reads $RECS)
  if jq -e "$2" >/dev/null 2>&1 <<<"$RECS"; then ok "$1"; else bad "$1"; fi
}

command -v curl >/dev/null || die "curl not found"
command -v jq   >/dev/null || die "jq not found"
for f in "${STATEMENTS[@]}"; do [[ -f "$f" ]] || die "missing sample statement: $f"; done

printf 'Cards API demo flow\n  base URL: %s\n  user:     %s\n' "$BASE_URL" "$USERNAME"

step "0. Preflight"
curl -sS -o /dev/null --max-time 5 "$BASE_URL/api/cards/" 2>/dev/null \
  || die "no server at $BASE_URL — run: cd backend && python manage.py runserver"
ok "server reachable"

if [[ "$RUN_SETUP" == "1" ]]; then
  if (cd "$BACKEND_DIR" && python manage.py setup_dev >/tmp/setup_dev.log 2>&1); then
    ok "setup_dev (catalog + aliases + demo user)"
  else
    bad "setup_dev failed — see /tmp/setup_dev.log"
  fi
else
  info "setup_dev skipped (--no-setup)"
fi

step "1. Register"
api POST /api/register/ -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"password2\":\"$PASSWORD\"}"
expect_code "register (201 new / 400 already exists)" "201,400"

step "2. Get token"
api POST /api/token/ -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}"
expect_code "login" "200"
ACCESS="$(jq -r '.access // empty' <<<"$BODY")"
[[ -n "$ACCESS" ]] || die "no access token in response: $BODY"
ok "access token captured"

step "3. Catalog cards"
auth_api GET /api/cards/
expect_code "catalog list" "200"
CARD_COUNT="$(jq -r '.count // 0' <<<"$BODY")"
CARD_PRODUCT_ID="$(jq -r '.cards[0].id // empty' <<<"$BODY")"
if [[ "$CARD_COUNT" -gt 0 ]]; then ok "catalog has $CARD_COUNT product(s)"; else bad "catalog is empty"; fi

step "4. Wallet"
auth_api GET /api/wallet/
expect_code "wallet list" "200"
USER_CARD_ID="$(jq -r '.cards[0].id // empty' <<<"$BODY")"
if [[ -z "$USER_CARD_ID" ]]; then
  auth_api POST /api/wallet/ -H 'Content-Type: application/json' \
    -d "{\"card_product_id\": $CARD_PRODUCT_ID}"
  expect_code "wallet add from catalog" "201"
  USER_CARD_ID="$(jq -r '.id // empty' <<<"$BODY")"
fi
[[ -n "$USER_CARD_ID" ]] || die "could not resolve a user_card_id"
ok "user_card_id=$USER_CARD_ID"

step "5. Upload statements"
# 409 means these bytes are already imported under a different wallet card
# (leftover dev state). The documented recovery is reassign, not re-upload.
for f in "${STATEMENTS[@]}"; do
  auth_api POST /api/upload/ -F "file=@$f" -F "user_card_id=$USER_CARD_ID"
  if [[ "$HTTP_CODE" == "409" ]]; then
    PRIOR_UPLOAD_ID="$(jq -r '.upload_id // empty' <<<"$BODY")"
    info "$(basename "$f") already imported elsewhere (upload_id=$PRIOR_UPLOAD_ID) — reassigning"
    auth_api POST "/api/uploads/$PRIOR_UPLOAD_ID/reassign/" -H 'Content-Type: application/json' \
      -d "{\"user_card_id\": $USER_CARD_ID}"
    expect_code "reassign upload $PRIOR_UPLOAD_ID to user_card $USER_CARD_ID" "200"
    info "transactions_updated=$(jq -r '.transactions_updated // 0' <<<"$BODY")"
  else
    expect_code "upload $(basename "$f")" "200,201"
    info "$(jq -rc '.summary // {}' <<<"$BODY")"
  fi
done

step "6. Transactions"
auth_api GET /api/transactions/
expect_code "transaction list" "200"
TX_COUNT="$(jq -r '.count // 0' <<<"$BODY")"
if [[ "$TX_COUNT" -gt 0 ]]; then ok "$TX_COUNT transaction(s) stored"; else bad "no transactions stored"; fi

step "7. Review queue"
auth_api GET /api/review/
expect_code "review queue" "200"
MERCHANT_KEY="$(jq -r '.merchants[0].merchant_key // empty' <<<"$BODY")"
info "$(jq -r '.count // 0' <<<"$BODY") merchant(s) awaiting a category"

step "8. Review answer"
if [[ -n "$MERCHANT_KEY" ]]; then
  auth_api POST /api/review/answer/ -H 'Content-Type: application/json' \
    -d "$(jq -nc --arg m "$MERCHANT_KEY" '{merchant_key: $m, category: "groceries"}')"
  expect_code "label \"$MERCHANT_KEY\" as groceries" "200"
  info "transactions_updated=$(jq -r '.transactions_updated // 0' <<<"$BODY")"
else
  info "queue empty — nothing to label"
fi

step "9. Spend summary"
auth_api GET /api/summary/
expect_code "summary" "200"
info "days_span=$(jq -r .period.days_span <<<"$BODY")  months_covered=$(jq -r .period.months_covered <<<"$BODY")  categorized_pct=$(jq -r .categorized_pct <<<"$BODY")  total_spend=$(jq -r .total_spend <<<"$BODY")"
info "by_category: $(jq -rc .by_category <<<"$BODY")"

step "10. Recommendations"
auth_api GET /api/recommendations/
expect_code "recommendations" "200"
RECS="$BODY"

check "top-level keys present" \
  'has("confidence") and has("confidence_note") and has("value_basis") and has("recommendations")'

check "at most 5 recommendations" '.recommendations | length <= 5'

check "every card carries the locked field set" \
  '[.recommendations[] | has("rank") and has("card_id") and has("card_name")
     and has("issuer") and has("reward_currency") and has("headline")
     and has("spending_score") and has("annual_fee") and has("signup_bonus_score")
     and has("signup_bonus_status") and has("signup_bonus_note") and has("total_score")
     and has("ongoing_annual_value") and has("break_even_annual_spend")
     and has("explanation")] | all'

check "money fields are 2-decimal strings" \
  '[.recommendations[] | .spending_score, .annual_fee, .signup_bonus_score, .total_score,
     .ongoing_annual_value | test("^-?[0-9]+\\.[0-9]{2}$")] | all'

# Each field is rounded independently, so the identity can drift by one cent.
check "total_score = spending_score - annual_fee + signup_bonus_score" \
  '[.recommendations[]
     | (((.spending_score | tonumber) - (.annual_fee | tonumber) + (.signup_bonus_score | tonumber))
        - (.total_score | tonumber) | fabs) <= 0.011] | all'

check "ongoing_annual_value = spending_score - annual_fee" \
  '[.recommendations[]
     | (((.spending_score | tonumber) - (.annual_fee | tonumber))
        - (.ongoing_annual_value | tonumber) | fabs) <= 0.011] | all'

check "break_even is present exactly when a fee needs covering" \
  '[.recommendations[]
     | if (.annual_fee | tonumber) > 0 and (.spending_score | tonumber) > 0
       then .break_even_annual_spend != null
       else .break_even_annual_spend == null end] | all'

check "signup_bonus_status values are valid" \
  '[.recommendations[].signup_bonus_status
     | . == "met" or . == "not_met" or . == "insufficient_data" or . == "no_bonus"] | all'

check "a scored bonus implies status met" \
  '[.recommendations[] | ((.signup_bonus_score | tonumber) > 0) == (.signup_bonus_status == "met")] | all'

check "competition ranks are consistent (ties share a rank)" \
  '([.recommendations | to_entries[] | .value.rank <= (.key + 1)] | all)
   and ([.recommendations[].rank] | . == sort)'

check "rank_note appears only on ties" \
  '[.recommendations[] | has("rank_note") | not] | all
   or ([.recommendations[] | select(has("rank_note")) | .rank_note | test("Tied with")] | all)'

check "explanation rows reconcile with their effective rate" \
  '[.recommendations[].explanation[]
     | (((.annualized_spend | tonumber) * (.effective_rate | tonumber) / 100)
        - (.value | tonumber) | fabs) <= 0.011] | all'

printf '\n  confidence: %s%s\n' \
  "$(jq -r .confidence <<<"$RECS")" \
  "$(jq -r 'if .confidence_note == "" then "" else "  (" + .confidence_note + ")" end' <<<"$RECS")"
printf '  basis: %s\n\n' \
  "$(jq -r '.value_basis | "USD/year from " + (.months_of_data|tostring) + " month(s) of data, " + .point_value_cents + "c per point"' <<<"$RECS")"
printf '  %-5s %-22s %-9s %-8s %-8s %-18s %-10s %s\n' RANK CARD REWARDS FEE BONUS BONUS_STATUS ONGOING YEAR_1
jq -r '.recommendations[] | [.rank, .card_name, .spending_score, .annual_fee,
                             .signup_bonus_score, .signup_bonus_status,
                             .ongoing_annual_value, .total_score] | @tsv' <<<"$RECS" \
| while IFS=$'\t' read -r rank name spend fee bonus bstatus ongoing total; do
    printf '  %-5s %-22s %-9s %-8s %-8s %-18s %-10s %s\n' \
      "$rank" "$name" "$spend" "$fee" "$bonus" "$bstatus" "$ongoing" "$total"
  done

printf '\n'
jq -r '.recommendations[] | "  #" + (.rank|tostring) + " " + .card_name + ": " + .headline' <<<"$RECS"
jq -r '.recommendations[0] | "\n  where #" + (.rank|tostring) + " " + .card_name + " earns it:"' <<<"$RECS"
jq -r '.recommendations[0].explanation[] | select((.value | tonumber) != 0)
       | "    " + .category + " @ " + .effective_rate + "% of " + .annualized_spend + " = " + .value' <<<"$RECS"
jq -r '.recommendations[] | select(has("rank_note")) | "  tie: " + .card_name + " — " + .rank_note' <<<"$RECS"
jq -r '.recommendations[] | select(.signup_bonus_note != "") | "  bonus: " + .card_name + " — " + .signup_bonus_note' <<<"$RECS"

step "11. Auth guard"
api GET /api/recommendations/
expect_code "recommendations without a token" "401"

step "Result"
printf '  %d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]] || exit 1
