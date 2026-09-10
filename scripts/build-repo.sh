#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

repo_dir="${REPO_DIR:-repo}"
build_root="${BUILD_ROOT:-build}"
state_dir="${STATE_DIR:-.flatpak-builder}"
arch="${FLATPAK_ARCH:-x86_64}"
branch="${FLATPAK_BRANCH:-stable}"
runtime_repo="${FLATPAK_RUNTIME_REPO:-https://dl.flathub.org/repo/flathub.flatpakrepo}"

"$repo_root/tests/validate-manifests.sh"
mkdir -p -- "$repo_dir" "$build_root" "$state_dir"

if [[ ! -f "$repo_dir/config" ]]; then
  ostree init --repo="$repo_dir" --mode=archive-z2
fi

flatpak remote-add --user --if-not-exists flathub "$runtime_repo"
mapfile -t manifests < <("$script_dir/discover-manifests.sh")

for manifest in "${manifests[@]}"; do
  app_id="$(basename -- "$(dirname -- "$manifest")")"
  args=(
    --arch="$arch"
    --default-branch="$branch"
    --disable-rofiles-fuse
    --disable-updates
    --force-clean
    --install-deps-from=flathub
    --repo="$repo_dir"
    --state-dir="$state_dir"
    --user
  )
  if [[ -n "${GPG_KEY_ID:-}" ]]; then
    args+=(--gpg-sign="$GPG_KEY_ID")
  fi

  flatpak-builder "${args[@]}" "$build_root/$app_id" "$manifest"
done
