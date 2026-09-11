#!/usr/bin/env bash
set -euo pipefail

repo_dir="${REPO_DIR:-repo}"
repo_url="${FLATPAK_REPO_URL:-}"
repo_title="${FLATPAK_REPO_TITLE:-My Flathub}"

if [[ -z "${GPG_KEY_ID:-}" ]]; then
    echo "必须设置 GPG_KEY_ID" >&2
    exit 1
fi
if [[ -z "$repo_url" || "$repo_url" != */ ]]; then
    echo "FLATPAK_REPO_URL 必须是以“/”结尾的 HTTPS URL" >&2
    exit 1
fi
if [[ "$repo_url" != https://* ]]; then
    echo "FLATPAK_REPO_URL 必须使用 HTTPS" >&2
    exit 1
fi

gpg_key="$(gpg --batch --export "$GPG_KEY_ID" | base64 | tr -d '\n')"
if [[ -z "$gpg_key" ]]; then
    echo "无法导出 $GPG_KEY_ID 对应的公钥" >&2
    exit 1
fi

mkdir -p -- "$repo_dir"
{
    printf '%s\n' '[Flatpak Repo]'
    printf 'Title=%s\n' "$repo_title"
    printf 'Url=%s\n' "$repo_url"
    printf '%s\n' 'Comment=由 My Flathub 发布的应用程序'
    printf '%s\n' 'Description=由 My Flathub monorepo 构建并发布的应用程序'
    printf 'GPGKey=%s\n' "$gpg_key"
} >"$repo_dir/repo.flatpakrepo"
