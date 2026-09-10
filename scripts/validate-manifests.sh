#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

for command in flatpak-builder jq xmllint; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "缺少必需命令：$command" >&2
    exit 1
  fi
done

mapfile -t manifests < <("$script_dir/discover-manifests.sh")
if (( ${#manifests[@]} == 0 )); then
  echo "packages/ 下未发现 Flatpak manifest" >&2
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "$tmp_dir"' EXIT
declare -A seen_ids=()

for manifest in "${manifests[@]}"; do
  package_dir="$(dirname -- "$manifest")"
  package_name="$(basename -- "$package_dir")"
  expected_manifest="$package_dir/$package_name.yaml"

  if [[ "$manifest" != "$expected_manifest" ]]; then
    echo "$manifest：文件路径必须为 $expected_manifest" >&2
    exit 1
  fi

  normalized="$tmp_dir/$package_name.json"
  flatpak-builder --show-manifest "$manifest" >"$normalized"

  app_id="$(jq -er '.["app-id"] // .id' "$normalized")"
  if [[ "$app_id" != "$package_name" ]]; then
    echo "$manifest：app-id“$app_id”必须与目录名“$package_name”一致" >&2
    exit 1
  fi
  if [[ -n "${seen_ids[$app_id]:-}" ]]; then
    echo "$manifest：app-id“$app_id”重复，另见 ${seen_ids[$app_id]}" >&2
    exit 1
  fi
  seen_ids[$app_id]="$manifest"

  jq -e '
    ((.["runtime"] // "") | length > 0) and
    ((.["runtime-version"] // "") | length > 0) and
    ((.["sdk"] // "") | length > 0) and
    ((.["command"] // "") | length > 0)
  ' "$normalized" >/dev/null || {
    echo "$manifest：必须设置 runtime、runtime-version、sdk 和 command" >&2
    exit 1
  }

  if ! jq -e '
    [.. | objects |
      select((.type? == "archive" or .type? == "file" or .type? == "extra-data") and .url?) |
      select((.sha256? // "") | test("^[0-9a-fA-F]{64}$") | not)
    ] | length == 0
  ' "$normalized" >/dev/null; then
    echo "$manifest：每个远程 archive、file 或 extra-data 源都必须提供 SHA256" >&2
    exit 1
  fi

  if ! jq -e '
    [.. | objects |
      select(.type? == "git") |
      select(
        (.branch? != null) or
        (((.commit? // "") | test("^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$")) | not)
      )
    ] | length == 0
  ' "$normalized" >/dev/null; then
    echo "$manifest：Git 源必须使用完整提交哈希，且不得使用 branch" >&2
    exit 1
  fi

  metainfo="$package_dir/$app_id.metainfo.xml"
  if [[ ! -f "$metainfo" ]]; then
    echo "$manifest：缺少必需的 MetaInfo 文件：$metainfo" >&2
    exit 1
  fi
  metainfo_id="$(xmllint --xpath 'string(/*[local-name()="component"]/*[local-name()="id"][1])' "$metainfo")"
  if [[ "$metainfo_id" != "$app_id" ]]; then
    echo "$metainfo：组件 ID“$metainfo_id”与“$app_id”不一致" >&2
    exit 1
  fi

  if command -v flatpak-builder-lint >/dev/null 2>&1; then
    flatpak-builder-lint --gha-format manifest "$manifest"
    flatpak-builder-lint --gha-format appstream "$metainfo"
  else
    echo "警告：flatpak-builder-lint 不可用，已跳过 $manifest" >&2
  fi
done

printf '已验证 %d 个 Flatpak manifest。\n' "${#manifests[@]}"
