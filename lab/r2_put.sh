#!/usr/bin/env bash
# Upload one file to R2 via the Cloudflare API: r2_put.sh <file> <key>
# Needs R2_TOKEN (API token with R2 object write), R2_ACCOUNT, R2_BUCKET.
set -euo pipefail
curl -sS --fail-with-body --retry 3 -X PUT \
  -H "Authorization: Bearer $R2_TOKEN" -H "Content-Type: application/gzip" \
  --data-binary @"$1" \
  "https://api.cloudflare.com/client/v4/accounts/$R2_ACCOUNT/r2/buckets/$R2_BUCKET/objects/$2"
echo
