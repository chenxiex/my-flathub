# AGENTS.md

本文件记录参与仓库开发和维护软件包所需的信息。面向 Flatpak 源使用者及仓库
部署、发布运维人员的说明见 `README.md`。

## 语言规范

- 仓库内的文档、代码注释、工作流显示名称和 Git 提交信息必须使用中文。
- 命令、文件名、环境变量、应用 ID、API 名称及其他技术标识符保留其原始拼写。
- `LICENSE` 保留许可证官方英文原文，避免翻译改变法律含义；如需中文说明，应另建译文并明确其不具有法律效力。

## 仓库结构

每个应用独占一个目录，目录名、manifest 文件名和 `app-id` 必须一致：

```text
packages/
  org.example.FlatpakHello/
    org.example.FlatpakHello.yaml
    org.example.FlatpakHello.metainfo.xml
    flatpak-hello.sh
scripts/
  build-repo.sh
  discover-manifests.sh
  finalize-repo.sh
  generate-flatpakrepo.sh
  r2-repo.sh
tests/
  probe-public-repo.sh
  validate-manifests.sh
  verify-repo.sh
```

补丁、图标、Desktop 文件和本地辅助源码也应放入对应的应用目录。

## 添加或修改应用

- 新增应用时，在 `packages/<app-id>/` 中添加 `<app-id>.yaml` 和
  `<app-id>.metainfo.xml`。发现脚本会自动将 manifest 加入 CI、发布和上游版本
  检查，不要另建或维护应用列表。
- manifest 必须设置 `runtime`、`runtime-version`、`sdk` 和 `command`。
- 远程 `archive`、`file` 和 `extra-data` 源必须提供 SHA256。
- Git 源必须固定为完整 commit，不能追踪 branch。
- 需要自动更新的源应添加标准 `x-checker-data`。
- MetaInfo 的组件 ID 必须与应用 ID 一致。

## 本地构建

系统已安装 `flatpak-builder`，或已通过 Flatpak 安装 `org.flatpak.Builder` 时运行：

```console
bash scripts/build-repo.sh
bash tests/verify-repo.sh
```

脚本优先使用原生 `flatpak-builder`；找不到时会自动通过
`flatpak run org.flatpak.Builder` 调用 Flatpak 版本。

也可以使用 Flathub 的 Builder Flatpak 构建单个应用：

```console
flatpak install flathub org.flatpak.Builder
flatpak run --filesystem="$PWD" --command=flatpak-builder \
  org.flatpak.Builder --force-clean --disable-rofiles-fuse \
  --install-deps-from=flathub build/org.example.FlatpakHello \
  packages/org.example.FlatpakHello/org.example.FlatpakHello.yaml
```

CI 使用固定 digest 的
`ghcr.io/flathub-infra/flatpak-github-actions:freedesktop-25.08` 构建完整 monorepo。

## 构建与验证

- 提交前按变更范围运行以下验证；一项变更涉及多个范围时，运行其全部命令。
- 修改 manifest 或打包资源后，运行 `bash tests/validate-manifests.sh`。
- 修改构建、仓库生成或发布逻辑后，运行 `bash scripts/build-repo.sh` 和 `bash tests/verify-repo.sh`。
- 修改 GitHub Actions 工作流后，使用 `actionlint` 验证工作流语法。
- 不得因为沙箱限制而跳过必要的测试、冒烟测试、设备探测、依赖安装或其他验证。
