#!/usr/bin/env bash
# Upload one file to R2 over its S3 API: r2_put.sh <file> <key>
# Needs R2_TOKEN (Cloudflare API token with R2 object write), R2_ACCOUNT, R2_BUCKET.
# S3 credentials derive from the token: key id = token id, secret = sha256(token).
set -euo pipefail
if [ -z "${AWS_ACCESS_KEY_ID:-}" ]; then
  AWS_ACCESS_KEY_ID=$(curl -sS -H "Authorization: Bearer $R2_TOKEN" \
    "https://api.cloudflare.com/client/v4/accounts/$R2_ACCOUNT/tokens/verify" | jq -r .result.id)
  AWS_SECRET_ACCESS_KEY=$(printf %s "$R2_TOKEN" | sha256sum | cut -d' ' -f1)
  echo "::add-mask::$AWS_SECRET_ACCESS_KEY"
  export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION=auto
fi
aws s3 cp --only-show-errors "$1" "s3://$R2_BUCKET/$2" \
  --endpoint-url "https://$R2_ACCOUNT.r2.cloudflarestorage.com"
