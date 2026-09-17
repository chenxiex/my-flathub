# PR 测试仓库入口

`preview-repo.ts` 把标准 OSTree 文件路径映射到同一仓库的 GitHub 预览 Release 附件。Worker 只处理公开文件下载，不保存仓库数据，也不需要运行时密钥。

本地先执行 `npm ci --prefix workers`，再用 `npm run typecheck --prefix workers`、`npm test --prefix workers` 和 `npm run build --prefix workers` 检查类型、在 Workers 运行时测试并验证构建；CI 也会执行这些命令。运行时类型由 `wrangler types` 按 `workers/wrangler.toml` 生成。

## 部署与运维

1. 确认 `<预览域名>` 所属的 Cloudflare zone 已加入当前账号，并且该主机名没有已有的 CNAME 记录。预览入口应使用独立子域名，不要与正式仓库共用主机名。
2. 编辑 [wrangler.toml](wrangler.toml)并设置：

   ```toml
   [[routes]]
   pattern = "<预览域名>"
   custom_domain = true
   ```

   Cloudflare 会在部署 Custom Domain 时创建所需 DNS 记录和证书。
3. 在仓库根目录执行 `npm ci --prefix workers` 和 `npm run deploy --prefix workers`。首次部署需要按 Wrangler 提示登录 Cloudflare。部署完成后确认 `https://<预览域名>/` 可以通过 HTTPS 访问；根路径返回 404 是预期行为，仓库文件位于 `/pr/<PR号>/<运行ID>-<重试次数>/` 下。
4. 在 GitHub 仓库的 Actions variables 中设置 `PR_PREVIEW_BASE_URL` 为 `https://<预览域名>/`，**末尾保留 `/`**。发布工作流使用仓库自带的 `GITHUB_TOKEN`；无需添加生产 R2 或 GPG 密钥。
5. 确认仓库允许 Actions 工作流申请 `contents: write`、`pull-requests: write`、`actions: write` 权限。首次由外部贡献者提交的 PR 仍可能需要 GitHub 对工作流运行的批准。
6. 将这些工作流合并到 `main` 后创建测试 PR。`workflow_run` 只使用默认分支上的发布代码，因此实现功能的 PR 本身不会生成公开测试仓库。成功的新构建会更新 PR 评论并清理该 PR 的旧预览；PR 关闭时立即清理，每天的定时任务删除超过 5 天的 Release 和 tag。

自定义域名只作为预览入口，不影响正式仓库域名或 R2 bucket。PR CI 使用同一个 `PR_PREVIEW_BASE_URL`。

## 生命周期和限制

每次 CI 运行使用独立的 `pr/<PR号>/<运行ID>-<重试次数>/` 地址。成功的新构建会更新 PR 评论并删除该 PR 的旧预览；PR 关闭时立即清理，每天的定时任务删除超过 5 天的 Release 和 tag。安装后的预览 remote 在链接失效后无法更新，测试结束可按 PR 评论中的命令移除。
