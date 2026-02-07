#!/usr/bin/env bash
# get-upstash-redis.sh
# Quick helper to get your Upstash Redis connection URL
# Requirements: curl, jq

set -euo pipefail

# ────────────────────────────────────────────────
# Configuration – change these if needed
# ────────────────────────────────────────────────
UPSTASH_API_TOKEN="your_upstash_api_token_here"   # ← Paste your real token
UPSTASH_EMAIL="your@email.com"                     # optional, for logging
DATABASE_NAME="cursorcode-prod"                    # or whatever name you want

# ────────────────────────────────────────────────
# Colors & helpers
# ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()    { echo -e "\( {GREEN}[INFO] \){NC} $*" >&2; }
warn()    { echo -e "\( {YELLOW}[WARN] \){NC} $*" >&2; }
error()   { echo -e "\( {RED}[ERROR] \){NC} $*" >&2; exit 1; }

# ────────────────────────────────────────────────
# Check dependencies
# ────────────────────────────────────────────────
command -v curl >/dev/null 2>&1 || error "curl is required"
command -v jq   >/dev/null 2>&1 || error "jq is required (install: brew install jq or apt install jq)"

# ────────────────────────────────────────────────
# Ask for token if not set
# ────────────────────────────────────────────────
if [[ -z "${UPSTASH_API_TOKEN:-}" ]]; then
  read -r -p "Enter your Upstash API token: " UPSTASH_API_TOKEN
  [[ -z "$UPSTASH_API_TOKEN" ]] && error "API token is required"
fi

# ────────────────────────────────────────────────
# Create or get Redis database
# ────────────────────────────────────────────────
info "Checking/creating Upstash Redis database '$DATABASE_NAME'..."

DATABASE_ID=$(curl -s -H "Authorization: Bearer $UPSTASH_API_TOKEN" \
  "https://api.upstash.com/v2/redis/databases" | \
  jq -r --arg name "$DATABASE_NAME" '.[] | select(.name == $name) | .database_id')

if [[ -z "$DATABASE_ID" || "$DATABASE_ID" == "null" ]]; then
  info "Database '$DATABASE_NAME' not found → creating new one..."

  RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $UPSTASH_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"$DATABASE_NAME\",\"region\":\"us-east-1\",\"tls\":true}" \
    "https://api.upstash.com/v2/redis/databases")

  DATABASE_ID=$(echo "$RESPONSE" | jq -r '.database_id')
  if [[ -z "$DATABASE_ID" || "$DATABASE_ID" == "null" ]]; then
    error "Failed to create database: $(echo "$RESPONSE" | jq -r '.error // .message // .')"
  fi

  info "Database created with ID: $DATABASE_ID"
else
  info "Database '$DATABASE_NAME' already exists (ID: $DATABASE_ID)"
fi

# ────────────────────────────────────────────────
# Get connection details
# ────────────────────────────────────────────────
info "Fetching connection string..."

CONN_DETAILS=$(curl -s -H "Authorization: Bearer $UPSTASH_API_TOKEN" \
  "https://api.upstash.com/v2/redis/databases/$DATABASE_ID/details")

REDIS_URL=$(echo "$CONN_DETAILS" | jq -r '.connection_string // .endpoint // empty')

if [[ -z "$REDIS_URL" || "$REDIS_URL" == "null" ]]; then
  error "Could not retrieve Redis URL. Response: $CONN_DETAILS"
fi

# ────────────────────────────────────────────────
# Output
# ────────────────────────────────────────────────
echo ""
echo -e "\( {GREEN}Success! Upstash Redis connection string: \){NC}"
echo ""
echo "REDIS_URL=$REDIS_URL"
echo ""
echo -e "\( {YELLOW}Copy the line above into your .env file: \){NC}"
echo ""
echo "Next steps:"
echo "  1. Paste REDIS_URL into apps/api/.env"
echo "  2. Run docker compose up -d"
echo "  3. Test backend connection"
echo ""

# Optional: copy to clipboard (macOS & Linux with xclip)
if command -v pbcopy >/dev/null 2>&1; then
  echo "$REDIS_URL" | pbcopy
  echo "(copied to clipboard)"
elif command -v xclip >/dev/null 2>&1; then
  echo "$REDIS_URL" | xclip -selection clipboard
  echo "(copied to clipboard)"
fi
