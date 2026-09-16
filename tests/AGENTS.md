# Linter 例外

`linter-exceptions.json` 使用 `flatpak-builder-lint --user-exceptions` 的原生格式：键是应用 ID，值是该应用允许忽略的错误代码数组。不要在这里使用 `"*"` 表示所有应用；linter 不会这样解释它。

`linter-repository-policy.json` 是本仓库自己的策略文件，不直接传给 linter。其中 `ignored_error_codes` 对本仓库所有应用生效。验证脚本会将它与应用专属例外合并成临时的原生格式文件，再传给 `--user-exceptions`。这项本地策略不等于 Flathub 批准的例外。
