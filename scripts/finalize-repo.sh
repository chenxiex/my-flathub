#!/usr/bin/env bash
set -euo pipefail

repo_dir="${REPO_DIR:-repo}"

if [[ -z "${GPG_KEY_ID:-}" ]]; then
    echo "必须设置 GPG_KEY_ID" >&2
    exit 1
fi
if [[ ! -f "$repo_dir/config" ]]; then
    echo "未找到 OSTree 仓库：$repo_dir" >&2
    exit 1
fi

flatpak build-update-repo \
    --gpg-sign="$GPG_KEY_ID" \
    --generate-static-deltas \
    --prune \
    --prune-depth=1 \
    "$repo_dir"
