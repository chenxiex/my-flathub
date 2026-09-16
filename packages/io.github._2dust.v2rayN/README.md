# v2rayN 非官方 Flatpak 包

`io.github._2dust.v2rayN` 重打包 [v2rayN 上游 7.24.9 Linux x64 便携版](https://github.com/2dust/v2rayN/releases/tag/7.24.9)，包含 Xray、sing-box、mihomo 和规则文件。它不是上游官方 Flatpak，也未投递到 Flathub。
通过本源安装时使用 `flatpak install anlor io.github._2dust.v2rayN`。

## 权限和系统代理

本包需要网络、X11、IPC、DRI、托盘 D-Bus 和 `org.freedesktop.Flatpak` 权限。上游托盘使用动态的 `org.kde.StatusNotifierItem-<pid>-<序号>` 名称，Flatpak 无法只放行这类名称；为避免 GUI 在托盘初始化时崩溃，第一版使用 `--own-name=org.kde.*`。它允许应用占用其他 KDE D-Bus 名称，存在冒充服务、接收本应发给其他 KDE 服务的数据等风险。

此外，`org.freedesktop.Flatpak` 允许应用通过 `flatpak-spawn --host` 执行宿主命令，显著降低沙箱隔离性；仅在接受这一风险的机器上安装。包内将上游系统代理脚本调用的 `gsettings`、`kwriteconfig5/6` 和 `dbus-send` 转发到宿主。GNOME/KDE 的设置与清除功能仍需在真实桌面环境中验收，不能仅凭构建成功视为可用。

若相关宿主命令不可用、运行失败或代理无法正常工作，请先在桌面系统设置中关闭代理。GNOME 可执行 `gsettings set org.gnome.system.proxy mode 'none'`；KDE 可在系统设置的“代理”页面选择“不使用代理”。测试前应记录原有代理设置，测试后恢复。

## 更新和限制

不要使用程序内的 v2rayN GUI 自更新按钮：GUI 只能通过 Flatpak 更新。程序内的核心与规则更新仍可使用，其文件存于 `~/.var/app/io.github._2dust.v2rayN/data/v2rayN/`，不受 Flatpak 包版本控制。首版不支持 TUN、全局透明代理和登录自启动；完整待办及与上游 Linux 原生包的功能差异见 [TODO.md](TODO.md)。

## 上游来源

应用、捆绑核心及规则的来源和许可证请以对应上游项目当前版本的资料为准：[v2rayN](https://github.com/2dust/v2rayN)、[Xray-core](https://github.com/XTLS/Xray-core)、[sing-box](https://github.com/SagerNet/sing-box)、[mihomo](https://github.com/MetaCubeX/mihomo) 及 [v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat)。本包不复制其许可证正文；发布前仍须审计归档内各组件和规则数据的实际来源与分发义务。
