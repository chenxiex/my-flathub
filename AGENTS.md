# AGENTS.md

本文件记录参与仓库开发和维护软件包所需的信息。面向 Flatpak 源使用者及仓库部署、发布运维人员的说明见 `README.md`。

## 语言规范

- 仓库内的文档、代码注释、工作流显示名称和 Git 提交信息必须使用中文。
- 命令、文件名、环境变量、应用 ID、API 名称及其他技术标识符保留其原始拼写。
- `LICENSE` 保留许可证官方英文原文，避免翻译改变法律含义；如需中文说明，应另建译文并明确其不具有法律效力。

## 文档组织

- 文档采用渐进式披露：仓库根目录只说明整个仓库的共性、入口和导航，不堆放单个软件包的细节。
- 包的安装、权限、限制、更新和故障恢复等说明放在对应的 `packages/<app-id>/README.md`；根目录 `README.md` 只链接到该说明。
- 脚本、测试或工作流的专属说明放在相应子目录；同一事实尽量只维护一份，其他位置使用链接或简短引用。
- 不复写上游许可证正文或组件清单来代替上游权威资料；需要说明来源时引用对应上游项目和版本。法定分发义务仍须在发布前核对。

## 仓库结构

每个应用独占一个目录，目录名、manifest 文件名和 `app-id` 必须一致。仓库维护逻辑位于 Python 包，应用包内运行时脚本仍与应用资源放在一起：

```text
packages/
  org.example.FlatpakHello/
    org.example.FlatpakHello.yaml
    org.example.FlatpakHello.metainfo.xml
    flatpak-hello.sh
src/my_flathub/
  cli.py
  core.py
  preview.py
tests/
  test_*.py
```

补丁、图标、Desktop 文件和本地辅助源码也应放入对应的应用目录。

## 添加或修改应用

- 新增应用时，在 `packages/<app-id>/` 中添加 `<app-id>.yaml` 和 `<app-id>.metainfo.xml`。发现脚本会自动将 manifest 加入 CI、发布和上游版本检查，不要另建或维护应用列表。
- manifest 必须设置 `runtime`、`runtime-version`、`sdk` 和 `command`。
- 远程 `archive`、`file` 和 `extra-data` 源必须提供 SHA256。
- Git 源必须固定为完整 commit，不能追踪 branch。
- 需要自动更新的源应添加标准 `x-checker-data`。
- MetaInfo 的组件 ID 必须与应用 ID 一致。

## 本地构建

使用 `uv` 管理 Python 3.12 环境和锁定依赖。所有仓库维护命令都通过统一 CLI 运行；系统已安装 `flatpak-builder`，或已通过 Flatpak 安装 `org.flatpak.Builder` 时运行：

```console
uv run --locked my-flathub build-repo
uv run --locked my-flathub verify-repo
```

CLI 优先使用原生 `flatpak-builder`；找不到时会自动通过 `flatpak run org.flatpak.Builder` 调用 Flatpak 版本。

Python 代码、测试和配置变更还必须运行：

```console
uv run --locked ruff check
uv run --locked ruff format --check
uv run --locked ty check
uv run --locked pytest
```

也可以使用 Flathub 的 Builder Flatpak 构建单个应用：

```console
flatpak install flathub org.flatpak.Builder
flatpak run --filesystem="$PWD" --command=flatpak-builder \
  org.flatpak.Builder --force-clean --disable-rofiles-fuse \
  --install-deps-from=flathub build/org.example.FlatpakHello \
  packages/org.example.FlatpakHello/org.example.FlatpakHello.yaml
```

CI 使用固定 digest 的 `ghcr.io/flathub-infra/flatpak-github-actions:freedesktop-25.08` 构建完整 monorepo。

## 当前软件包的 Flatpak 数据目录

- 为验证当前正在打包的软件，允许 agents 读写该应用对应的 `~/.var/app/<app-id>/`，包括 `flatpak run` 自行生成的数据、配置和缓存。`<app-id>` 必须先从当前包的 manifest 确认；此例外不适用于其他应用、`~/.var/app/` 根目录或其他主目录路径。
- 只在构建、运行及验收该包所需的范围内使用此目录。先检查已有数据，保留用户配置；不要通过符号链接、路径穿越或更改 `HOME`、`XDG_*` 路径扩大范围。
- 此例外仅调整本仓库的文件写入规则，不改变执行环境的沙箱权限。`flatpak run` 或对该目录的写入若因沙箱受阻，应说明具体权限并请求提权；提权被拒绝时立即停止，不改用宿主原生程序或重定向数据来绕过限制。

## 构建与验证

- 提交前按变更范围运行以下验证；一项变更涉及多个范围时，运行其全部命令。
- 修改 manifest 或打包资源后，运行 `uv run --locked my-flathub validate-manifests`。
- 修改 Python 构建、仓库生成或发布逻辑后，运行 `uv run --locked my-flathub build-repo` 和 `uv run --locked my-flathub verify-repo`，以及本节列出的 Python 检查。
- 修改 GitHub Actions 工作流后，使用 `actionlint` 验证工作流语法。
- 不得因为沙箱限制而跳过必要的测试、冒烟测试、设备探测、依赖安装或其他验证。
