#!/usr/bin/env bash
set -euo pipefail

repo_dir="${REPO_DIR:-repo}"
arch="${FLATPAK_ARCH:-x86_64}"
branch="${FLATPAK_BRANCH:-stable}"
test_app="${FLATPAK_TEST_APP:-org.example.FlatpakHello}"

if [[ ! -f "$repo_dir/config" ]]; then
  echo "未找到 OSTree 仓库：$repo_dir" >&2
  exit 1
fi

ostree fsck --repo="$repo_dir"
if command -v flatpak-builder-lint >/dev/null 2>&1; then
  flatpak-builder-lint --gha-format repo "$repo_dir"
fi

repo_abs="$(cd -- "$repo_dir" && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
remote_name="my-flathub-test"
flatpak_args=(--user)

if [[ -n "${FLATPAK_GPG_PUBLIC_KEY_FILE:-}" ]]; then
  flatpak_args+=(--gpg-import="$FLATPAK_GPG_PUBLIC_KEY_FILE")
else
  flatpak_args+=(--no-gpg-verify)
fi

env XDG_DATA_HOME="$test_root/data" flatpak remote-add \
  "${flatpak_args[@]}" "$remote_name" "file://$repo_abs"
env XDG_DATA_HOME="$test_root/data" flatpak remote-ls --user "$remote_name"
env XDG_DATA_HOME="$test_root/data" flatpak install --user --noninteractive \
  "$remote_name" "$test_app//$branch"
output="$(env XDG_DATA_HOME="$test_root/data" flatpak run --user --arch="$arch" --branch="$branch" "$test_app")"
if [[ "$output" != '来自 My Flathub 的问候！' ]]; then
  echo "冒烟测试输出不符合预期：$output" >&2
  exit 1
fi
