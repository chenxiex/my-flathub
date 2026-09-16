#!/usr/bin/env bash
set -euo pipefail

command_name="${0##*/}"
case "$command_name" in
    gsettings|kwriteconfig5|kwriteconfig6|dbus-send) ;;
    *)
        echo "不支持转发的宿主命令：$command_name" >&2
        exit 2
        ;;
esac

if ! command -v flatpak-spawn >/dev/null 2>&1; then
    echo "缺少 flatpak-spawn，无法修改宿主系统代理。" >&2
    exit 127
fi

# 保留参数边界，不通过 shell 拼接用户提供的代理地址或例外列表。
if flatpak-spawn --host -- "$command_name" "$@"; then
    exit 0
fi

echo "宿主命令 $command_name 不可用或执行失败；请确认桌面环境已安装该命令，并手工检查宿主系统代理。" >&2
exit 1
