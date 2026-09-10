# AGENTS.md

## 语言规范

- 仓库内的文档、代码注释、工作流显示名称和 Git 提交信息必须使用中文。
- 命令、文件名、环境变量、应用 ID、API 名称及其他技术标识符保留其原始拼写。
- `LICENSE` 保留许可证官方英文原文，避免翻译改变法律含义；如需中文说明，应另建译文并明确其不具有法律效力。

## 构建与验证

- 修改 manifest 或打包资源后，运行 `bash scripts/validate-manifests.sh`。
- 修改构建、仓库生成或发布逻辑后，运行 `bash scripts/build-repo.sh` 和 `bash scripts/verify-repo.sh`。
- 修改 GitHub Actions 工作流后，使用 `actionlint` 验证工作流语法。
- 不得因为沙箱限制而跳过必要的测试、冒烟测试、设备探测、依赖安装或其他验证。
