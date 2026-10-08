#!/bin/sh
# Is the AI path up — and is it the path the platform says it is?
#
# The order of these checks is the architecture, not a preference:
#
#   1. the Gateway's readiness          — is the only address applications may
#                                        use actually accepting traffic?
#   2. the skills an interface may name — is the catalogue loaded and authorised?
#   3. LiteLLM, from inside the network — the Gateway's upstream, nobody else's
#   4. LiteLLM, from the host           — must FAIL: compose publishes no port for
#                                        it (docs/ARCHITECTURE.md:106)
#
# A doctor script that reached LiteLLM over the host would be testing a door this
# deployment deliberately closed, and reporting green for a rule nobody enforces.
#
# Usage:  sh scripts/doctor/check-ai.sh [ask]
#   "ask" adds one real end-to-end completion through the Gateway. It needs a model
#   loaded on the Ollama host and it costs tokens, so it is off by default.

GATEWAY_URL="${FK_GATEWAY_DOCTOR_URL:-http://localhost:8100}"
LITELLM_URL="${FK_GATEWAY_DOCTOR_LITELLM:-http://localhost:4000}"
# The first key wins when several are configured for a rotation window.
GATEWAY_KEY="${FK_GATEWAY_API_KEYS%%,*}"
COMPOSE="${FK_GATEWAY_COMPOSE:-docker compose}"
BODY=$(mktemp 2>/dev/null || echo /tmp/fk-doctor-body)

failures=0

note() {
    printf '%s\n' "$1"
}

fail() {
    note "FAIL  $1"
    [ -s "$BODY" ] && sed -n '1,3p' "$BODY"
    failures=$((failures + 1))
}

# get <label> <url> — a 200 is the only acceptable answer.
get() {
    status=$(curl -s -o "$BODY" -w '%{http_code}' -m 10 "$2" 2>/dev/null)
    if [ "$status" = "200" ]; then
        note "OK    $1  (HTTP $status)"
    else
        fail "$1  (HTTP ${status:-no response})"
    fi
}

note "FutureKind AI path — Gateway first"
note ""

get "GET  $GATEWAY_URL/health/ready" "$GATEWAY_URL/health/ready"

if [ -z "$GATEWAY_KEY" ]; then
    note "SKIP  skill listing  (FK_GATEWAY_API_KEYS is not set in this shell)"
    failures=$((failures + 1))
else
    status=$(curl -s -o "$BODY" -w '%{http_code}' -m 10 \
        -H "Authorization: Bearer $GATEWAY_KEY" "$GATEWAY_URL/v1/models" 2>/dev/null)
    skills=$(grep -o '"id"' "$BODY" 2>/dev/null | wc -l)
    if [ "$status" = "200" ] && [ "$skills" -gt 0 ]; then
        note "OK    GET  $GATEWAY_URL/v1/models  ($skills skill(s) offered)"
    else
        fail "GET  $GATEWAY_URL/v1/models  (HTTP ${status:-no response}, no skills listed)"
    fi

    note ""
    note "Checking that the interface's door refuses an unknown credential..."
    status=$(curl -s -o "$BODY" -w '%{http_code}' -m 10 \
        -H "Authorization: Bearer not-a-real-key" "$GATEWAY_URL/v1/models" 2>/dev/null)
    if [ "$status" = "401" ]; then
        note "OK    an unauthenticated /v1/models is refused  (HTTP 401)"
    else
        fail "unauthenticated /v1/models returned HTTP ${status:-no response}, expected 401"
    fi
fi

note ""
note "Checking LiteLLM from inside the network..."
if command -v docker >/dev/null 2>&1; then
    if $COMPOSE exec -T litellm wget -qO- http://localhost:4000/health/liveliness >/dev/null 2>&1; then
        note "OK    litellm /health/liveliness  (via docker compose exec)"
    else
        fail "litellm is not answering inside the futurekind network"
    fi
else
    note "SKIP  litellm internal check  (no docker CLI on this host)"
fi

note ""
note "Checking that LiteLLM is not reachable from the host..."
if curl -s -m 3 -o /dev/null "$LITELLM_URL/health/liveliness" 2>/dev/null; then
    fail "$LITELLM_URL answered from the host — LiteLLM must not be a second entry point"
else
    note "OK    $LITELLM_URL is closed to the host"
fi

if [ "${1:-}" = "ask" ]; then
    note ""
    note "Asking one non-clinical question through the full stack..."
    status=$(curl -s -o "$BODY" -w '%{http_code}' -m 60 \
        -H "Authorization: Bearer $GATEWAY_KEY" -H 'Content-Type: application/json' \
        -X POST "$GATEWAY_URL/chat" \
        -d '{"skill":"platform-chat","messages":[{"role":"user","content":"Reply with the single word: ready"}]}' \
        2>/dev/null)
    if [ "$status" = "200" ] && grep -q '"content"' "$BODY"; then
        note "OK    application -> Gateway -> LiteLLM -> model answered"
    else
        fail "the request did not come back with an answer (HTTP ${status:-no response})"
    fi
fi

rm -f "$BODY" 2>/dev/null

note ""
if [ "$failures" -eq 0 ]; then
    note "All checks passed."
else
    note "$failures check(s) failed."
fi
exit $([ "$failures" -eq 0 ] && echo 0 || echo 1)
