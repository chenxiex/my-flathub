#!/usr/bin/env bash
set -euo pipefail

operation="${1:-}"
repo_dir="${REPO_DIR:-repo}"

for variable in R2_ACCOUNT_ID R2_BUCKET R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
  if [[ -z "${!variable:-}" ]]; then
    echo "必须设置 $variable" >&2
    exit 1
  fi
done

export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true

remote="r2:${R2_BUCKET}"
common_filters=(
  --exclude '/.lock'
  --exclude '/state/**'
  --exclude '/tmp/**'
  --exclude '/uncompressed-objects-cache/**'
)

case "$operation" in
  pull)
    mkdir -p -- "$repo_dir"
    rclone copy "$remote" "$repo_dir" --fast-list "${common_filters[@]}"
    ;;
  push)
    if [[ ! -f "$repo_dir/config" || ! -f "$repo_dir/summary" || ! -f "$repo_dir/summary.sig" ]]; then
      echo "发布前必须完成仓库元数据生成和签名" >&2
      exit 1
    fi

    if [[ -d "$repo_dir/objects" ]]; then
      rclone copy "$repo_dir/objects" "$remote/objects" --fast-list \
        --header-upload 'Cache-Control: public, max-age=31536000, immutable'
    fi
    if [[ -d "$repo_dir/deltas" ]]; then
      rclone copy "$repo_dir/deltas" "$remote/deltas" --fast-list \
        --header-upload 'Cache-Control: public, max-age=31536000, immutable'
    fi

    rclone copy "$repo_dir" "$remote" --fast-list \
      --exclude '/objects/**' --exclude '/deltas/**' \
      --exclude '/summary' --exclude '/summary.sig' \
      --header-upload 'Cache-Control: no-cache' \
      "${common_filters[@]}"
    rclone copyto "$repo_dir/summary.sig" "$remote/summary.sig" \
      --header-upload 'Cache-Control: no-cache'
    rclone copyto "$repo_dir/summary" "$remote/summary" \
      --header-upload 'Cache-Control: no-cache'

    rclone sync "$repo_dir" "$remote" --fast-list --delete-after "${common_filters[@]}"
    rclone check "$repo_dir" "$remote" --fast-list "${common_filters[@]}"
    ;;
  *)
    echo "用法：$0 pull|push" >&2
    exit 2
    ;;
esac
