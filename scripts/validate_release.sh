#!/usr/bin/env bash
set -euo pipefail
validation_dir=$(mktemp -d)
trap 'rm -rf "$validation_dir"' EXIT
python scripts/render_release.py \
  --image-prefix harbor.example.com/ci/mahavistaar \
  --image-tag dev-0000000000000000000000000000000000000000 \
  --app-origin https://ci.example.com \
  --output "$validation_dir/release.compose.json"
# Never read the developer's .env or print resolved credentials.
sed 's/=$/=ci-placeholder/' deploy/.env.dokploy.example > "$validation_dir/.env"
docker compose --project-directory "$validation_dir" --env-file "$validation_dir/.env" \
  -f "$validation_dir/release.compose.json" config --quiet
docker run --rm -v "$PWD/deploy/nginx-dokploy.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginx:1.28-alpine nginx -t
