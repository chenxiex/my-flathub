# v2rayN Flatpak 待办

本文记录 `io.github._2dust.v2rayN` 与 v2rayN 7.24.9 上游 Linux 发行包的功能差异、风险和验收工作。完成项目时应同时更新本文和包级 `README.md`。

调查基线：

- Flatpak 当前重打包 `v2rayN-linux-64.zip`，运行时为 `org.freedesktop.Platform//25.08`。
- 上游原生包以同版本官方 `v2rayN-linux-64.deb` 为主要对照；它将程序安装到 `/opt/v2rayN`，通过 `/usr/bin/v2rayn` 启动，并直接使用宿主桌面和提权工具。
- 上游版本提交为 [`521230c`](https://github.com/2dust/v2rayN/commit/521230c4)，发布说明见 [7.24.9](https://github.com/2dust/v2rayN/releases/tag/7.24.9)。

## 功能差异

| 功能 | 上游 Linux 原生包 | 当前 Flatpak | 状态 |
| --- | --- | --- | --- |
| GUI、配置和订阅管理 | 直接运行 Avalonia GUI | 原程序重打包，尚未完成真实桌面验收 | 待验收 |
| Xray、sing-box、mihomo 普通代理 | 可直接启动捆绑核心 | 三个核心均能在 25.08 构建沙盒中输出版本 | 部分通过 |
| 配置、日志及可更新核心的存储 | 安装目录不可写时使用用户本地数据目录 | 应落到 `~/.var/app/io.github._2dust.v2rayN/data/v2rayN/`，首次启动时复制 `bin` | 待验收 |
| GUI 自更新 | `/opt/v2rayN` 被识别为系统包，GUI 更新被禁用 | `/app/lib/v2rayN` 未被识别为系统包，仍可能错误提供 GUI 更新 | 不兼容 |
| 核心及 Geo/规则更新 | 写入用户本地数据目录 | 理论上可写入 Flatpak 数据目录 | 待验收 |
| 系统代理 | 直接调用宿主 `gsettings`、`kwriteconfig5/6` 和 `dbus-send` | 通过 `flatpak-spawn --host` 转发同名命令 | 待验收、高权限 |
| 托盘 | 直接注册动态 `org.kde.StatusNotifierItem-<pid>-<序号>` 名称 | 使用 `--own-name=org.kde.*` 放行 | 待验收、高权限 |
| TUN | 通过 `sudo` 启动 Xray 或 sing-box，并操作宿主网络 | 没有 `/dev/net/tun`、网络管理能力或可用的宿主提权流程 | 不支持 |
| 登录自启动 | 写入宿主 `~/.config/autostart/v2rayN.desktop` | 只会写入沙盒私有 home，不能形成宿主自启动项 | 不支持 |
| 打开数据目录和外部链接 | 使用宿主 `xdg-open` | 需要验证 Flatpak 门户行为和打开位置 | 待验收 |
| 架构 | 7.24.9 提供 amd64、arm64、loong64 和 riscv64 等 Linux 资产 | manifest 固定使用 `linux-64` 资产 | 仅 x86_64 |
| Wayland | Avalonia Linux 版本主要经 X11/XWayland 工作 | 仅授予 X11 socket | 与上游现状接近，待 Wayland 会话验收 |

上游功能依据：

- [Linux 系统代理脚本](https://github.com/2dust/v2rayN/blob/521230c4/v2rayN/ServiceLib/Sample/proxy_set_linux_sh)
- [Linux 登录自启动实现](https://github.com/2dust/v2rayN/blob/521230c4/v2rayN/ServiceLib/Handler/AutoStartupHandler.cs)
- [Linux TUN 提权实现](https://github.com/2dust/v2rayN/blob/521230c4/v2rayN/ServiceLib/Manager/CoreAdminManager.cs)
- [本地数据目录选择逻辑](https://github.com/2dust/v2rayN/blob/521230c4/v2rayN/ServiceLib/Common/Utils.cs)
- [上游系统代理和路由说明](https://github.com/2dust/v2rayN/wiki/Description-of-system-proxy-routing)

## P0：发布前必须处理

- [ ] 在真实 X11 和 Wayland/XWayland 会话启动 GUI，确认窗口、字体、剪贴板、文件选择器、外部链接和“打开存储所在的位置”可用。
- [ ] 导入不含敏感信息的测试配置，分别启动 Xray、sing-box 和 mihomo，验证本地监听、连接测试、延迟测试、订阅更新和退出时的子进程清理。
- [ ] 确认首次启动把 `bin` 复制到 Flatpak 数据目录；验证核心、Geo 和规则更新只修改该目录，Flatpak 更新后仍能继续使用。
- [ ] 禁用 GUI 自更新。优先让上游的 `IsPackagedInstall()` 识别 `/app`，或在源码构建时提供等价的 Flatpak 标识；不能只在文档中要求用户不要点击。
- [ ] 使用 `flatpak run --log-session-bus io.github._2dust.v2rayN` 验证托盘注册、菜单和退出操作，并评估能否消除 `--own-name=org.kde.*`。
- [ ] 分别在 GNOME 和 KDE 记录原代理设置，测试设置、重启核心、清除和异常退出，最后恢复原值。需要特别检查 KDE 清除后是否残留旧代理地址。
- [ ] 为 TUN 和登录自启动隐藏或禁用不可用的 UI，或提供不会误导用户的明确提示。

## P1：权限和发布质量

- [ ] 决定发布目标。私人仓库若保留 `org.freedesktop.Flatpak` 和 `org.kde.*`，必须继续醒目标注任意宿主命令执行和宽泛 D-Bus ownership 风险。
- [ ] 若准备投递 Flathub，重新设计动态托盘名称；Flathub linter 不接受当前 `--own-name=org.kde.*`。
- [ ] 若准备投递 Flathub，为 `flatpak-spawn` 权限准备充分理由并接受人工审核，或取消自动修改宿主系统代理。当前 linter 错误为 `finish-args-flatpak-spawn-access` 和 `finish-args-own-name-wildcard-org.kde`。私人仓库已在 `tests/linter-exceptions.json` 中仅对本应用显式放行；这不等于 Flathub 批准。
- [ ] 评估从上游源码构建，避免把上游便携归档作为不可修改的整体引入，并便于针对 Flatpak 禁用自更新、TUN 和原生 autostart。
- [ ] 审计 v2rayN、三个捆绑核心、规则数据库和 MaxMind 数据的版本、来源、签名及分发许可证；不能用主项目许可证替代捆绑组件审计。
- [ ] 视资源情况补充 AppStream 截图、翻译、开发者信息和非官方打包说明。私人仓库暂不托管截图；`metainfo-missing-screenshots` 和 `appstream-screenshots-not-mirrored-in-ostree` 已在 `tests/linter-repository-policy.json` 中对仓库所有应用放行，投递 Flathub 前必须撤销。
- [ ] 评估 26.08 runtime；完成 25.08 功能基线后再升级并重复冒烟测试。

## P2：平台覆盖和自动化

- [ ] 为 `aarch64` 选择 `v2rayN-linux-arm64.zip` 并维护对应 SHA256；在此之前显式限制构建架构，避免其他架构误用 x86_64 ELF。
- [ ] 评估 loongarch64 和 riscv64 构建；上游 7.24.9 的 Linux 资产并非所有架构都同时提供便携 ZIP。
- [ ] 增加启动包装、宿主代理转发参数边界和数据目录初始化的自动化测试。
- [ ] 增加 v2rayN 专用安装冒烟测试；现有 `tests/verify-repo.sh` 默认只运行 `org.example.FlatpakHello`。
