#!/usr/bin/env bash
set -euo pipefail

repo_url="${FLATPAK_REPO_URL:-}"
remote_name="${FLATPAK_REMOTE_NAME:-my-flathub}"

if [[ -z "$repo_url" || "$repo_url" != https://*/ ]]; then
    echo "FLATPAK_REPO_URL 必须是以“/”结尾的 HTTPS URL" >&2
    exit 1
fi

curl --fail --silent --show-error --retry 5 --retry-all-errors \
    --output /dev/null "${repo_url}repo.flatpakrepo"
curl --fail --silent --show-error --retry 5 --retry-all-errors \
    --output /dev/null "${repo_url}summary"

test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
env XDG_DATA_HOME="$test_root/data" flatpak remote-add --user --if-not-exists \
    "$remote_name" "${repo_url}repo.flatpakrepo"
env XDG_DATA_HOME="$test_root/data" flatpak remote-ls --user "$remote_name"
