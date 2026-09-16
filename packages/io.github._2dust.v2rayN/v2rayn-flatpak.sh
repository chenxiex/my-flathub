#!/usr/bin/env bash
set -euo pipefail

# 优先使用包内的宿主代理设置转发命令。
export PATH="/app/bin:/usr/bin:${PATH:-}"
exec /app/lib/v2rayN/v2rayN "$@"
