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

flatpak_builder_lint_init() {
    local repo_root="$1"

    if command -v flatpak-builder-lint >/dev/null 2>&1; then
        flatpak_builder_lint_command=(flatpak-builder-lint)
        return
    fi

    if [[ "${flatpak_builder_backend:-}" != "flatpak" ]]; then
        echo "缺少必需命令：flatpak-builder-lint" >&2
        return 1
    fi

    flatpak_builder_lint_command=(
        flatpak run
        --filesystem="$repo_root"
        --command=flatpak-builder-lint
        org.flatpak.Builder
    )
}

flatpak_builder_lint_run() {
    "${flatpak_builder_lint_command[@]}" "$@"
}

flatpak_builder_lint_run_for_app() {
    local repo_root="$1"
    local app_id="$2"
    shift 2

    # linter 的本地例外只按应用 ID 查找；仓库策略单独维护，调用前转换为原生格式。
    local exceptions_file
    local lint_status
    exceptions_file="$(mktemp "$repo_root/.flatpak-lint-exceptions.XXXXXX.json")"
    if ! jq -n --arg app_id "$app_id" \
        --slurpfile policy "$repo_root/tests/linter-repository-policy.json" \
        --slurpfile exceptions "$repo_root/tests/linter-exceptions.json" \
        '{($app_id): (($policy[0].ignored_error_codes + ($exceptions[0][$app_id] // [])) | unique)}' \
        >"$exceptions_file"; then
        rm -f -- "$exceptions_file"
        return 1
    fi

    if flatpak_builder_lint_run --exceptions \
        --user-exceptions "$exceptions_file" --appid "$app_id" "$@"; then
        lint_status=0
    else
        lint_status=$?
    fi
    rm -f -- "$exceptions_file"
    return "$lint_status"
}
