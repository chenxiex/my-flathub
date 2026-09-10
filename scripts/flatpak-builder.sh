#!/usr/bin/env bash

flatpak_builder_init() {
    local repo_root="$1"

    if command -v flatpak-builder >/dev/null 2>&1; then
        flatpak_builder_backend="native"
        flatpak_builder_command=(flatpak-builder)
        return
    fi

    if ! command -v flatpak >/dev/null 2>&1; then
        echo "缺少必需命令：flatpak-builder，且无法通过 flatpak 运行 org.flatpak.Builder" >&2
        return 1
    fi
    if ! flatpak info org.flatpak.Builder >/dev/null 2>&1; then
        echo "缺少 Flatpak Builder：请安装 flatpak-builder 或 org.flatpak.Builder" >&2
        return 1
    fi

    flatpak_builder_backend="flatpak"
    flatpak_builder_command=(
        flatpak run
        --filesystem="$repo_root"
        --command=flatpak-builder
        org.flatpak.Builder
    )
}

flatpak_builder_run() {
    "${flatpak_builder_command[@]}" "$@"
}
