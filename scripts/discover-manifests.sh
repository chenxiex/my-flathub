#!/usr/bin/env bash
set -euo pipefail

packages_dir="${1:-packages}"

if [[ ! -d "$packages_dir" ]]; then
  echo "软件包目录不存在：$packages_dir" >&2
  exit 1
fi

find "$packages_dir" -mindepth 2 -maxdepth 2 -type f \
  \( -name '*.yaml' -o -name '*.yml' \) -print0 \
  | sort -z \
  | tr '\0' '\n'
