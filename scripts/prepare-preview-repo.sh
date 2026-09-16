#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

repo_dir="${REPO_DIR:-repo}"
base_url="${PR_PREVIEW_BASE_URL:-}"
pr_number="${PR_NUMBER:-}"
head_sha="${PR_HEAD_SHA:-}"
run_id="${GITHUB_RUN_ID:-}"
run_attempt="${GITHUB_RUN_ATTEMPT:-}"

if [[ ! "$base_url" =~ ^https://[^/]+/$ ]]; then
    echo "PR_PREVIEW_BASE_URL 必须是 HTTPS Worker 根地址，并以 / 结尾" >&2
    exit 1
fi
if [[ ! "$pr_number" =~ ^[1-9][0-9]*$ || ! "$run_id" =~ ^[1-9][0-9]*$ || ! "$run_attempt" =~ ^[1-9][0-9]*$ || ! "$head_sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "PR 编号、运行 ID、重试次数或提交 SHA 无效" >&2
    exit 1
fi
if [[ ! -f "$repo_dir/config" ]]; then
    echo "未找到待发布的 OSTree 仓库" >&2
    exit 1
fi

export GNUPGHOME="$(mktemp -d "${RUNNER_TEMP:-/tmp}/preview-gnupg.XXXXXX")"
trap 'rm -rf -- "$GNUPGHOME"' EXIT
chmod 700 "$GNUPGHOME"
gpg --batch --pinentry-mode loopback --passphrase '' \
    --quick-generate-key "My Flathub PR #${pr_number} run ${run_id}-${run_attempt}" ed25519 sign 6d
key_id="$(gpg --batch --with-colons --list-secret-keys | awk -F: '$1 == "fpr" { print $10; exit }')"
test -n "$key_id"

while IFS= read -r ref; do
    if [[ "$ref" == appstream/* || "$ref" == appstream2/* ]]; then
        continue
    fi
    IFS=/ read -r kind app_id arch branch <<<"$ref"
    if [[ "$kind" != app && "$kind" != runtime ]] || [[ "$arch" != "${FLATPAK_ARCH:-x86_64}" || "$branch" != test ]]; then
        echo "预览仓库中存在意外的 ref：$ref" >&2
        exit 1
    fi
    sign_args=(--gpg-sign="$key_id" --arch="$arch")
    if [[ "$kind" == runtime ]]; then
        sign_args+=(--runtime)
    fi
    flatpak build-sign "${sign_args[@]}" "$repo_dir" "$app_id" "$branch"
done < <(ostree refs --repo="$repo_dir")

flatpak build-update-repo --gpg-sign="$key_id" --prune --prune-depth=0 "$repo_dir"
export GPG_KEY_ID="$key_id"
export FLATPAK_REPO_URL="${base_url}pr/${pr_number}/${run_id}-${run_attempt}/"
export FLATPAK_REPO_TITLE="My Flathub PR #${pr_number} 测试仓库"
bash "$script_dir/generate-flatpakrepo.sh"
gpg --batch --export "$key_id" >"${RUNNER_TEMP:-/tmp}/preview-public.gpg"

jq -n \
    --argjson pr_number "$pr_number" \
    --argjson run_id "$run_id" \
    --argjson run_attempt "$run_attempt" \
    --arg head_sha "$head_sha" \
    '{pr_number: $pr_number, run_id: $run_id, run_attempt: $run_attempt, head_sha: $head_sha}' \
    > preview.json
