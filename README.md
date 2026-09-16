# My Flathub

这是一个通过 GitHub Actions 构建、签名并发布到 Cloudflare R2 的 Flatpak monorepo。首版发布 `x86_64/stable`，R2 bucket 的根目录就是 OSTree repository。

## 添加和使用源

```console
flatpak remote-add --if-not-exists anlor \
  https://flatpak.anlor.top/repo.flatpakrepo
flatpak remote-ls anlor
flatpak install anlor org.example.FlatpakHello
```

## 软件包列表

- [org.example.FlatpakHello](packages/org.example.FlatpakHello/README.md)
- [io.github._2dust.v2rayN](packages/io.github._2dust.v2rayN/README.md)

## 运维

### GPG 发布密钥

建议生成只用于本源、没有口令的独立密钥。密钥泄露时应立即停止发布、轮换密钥并向所有用户重新分发 `.flatpakrepo`；已安装 remote 的信任密钥不会自动替换。

```console
gpg --batch --pinentry-mode loopback --passphrase '' \
  --quick-generate-key "My Flathub Release <flatpak@example.com>" ed25519 sign 2y
gpg --armor --export-secret-keys "My Flathub Release" > private.asc
gpg --export "My Flathub Release" > public-key.gpg
```

`--passphrase ''` 会生成无口令密钥，使 GitHub Actions 能在没有 `pinentry` 的非交互环境中完成签名。请仅将该密钥用于此仓库的发布，并严格保护对应的 Secret。

将 `private.asc` 的完整内容保存为 GitHub `production` environment secret `FLATPAK_GPG_PRIVATE_KEY`，不要提交私钥。公钥会在发布时由私钥导出并嵌入 `repo.flatpakrepo`。

### GitHub 配置

创建名为 `production` 的 Environment，并限制只能由 `main` 分支部署。

Environment secrets：

| 名称 | 说明 |
| --- | --- |
| `R2_ACCESS_KEY_ID` | 专用 R2 bucket 的 S3 Access Key ID |
| `R2_SECRET_ACCESS_KEY` | 对应 Secret Access Key |
| `FLATPAK_GPG_PRIVATE_KEY` | ASCII-armored 发布私钥 |

Environment variables：

| 名称 | 示例 |
| --- | --- |
| `R2_ACCOUNT_ID` | Cloudflare Account ID |
| `R2_BUCKET` | `my-flathub` |
| `FLATPAK_REPO_URL` | `https://flatpak.example.com/`，必须以 `/` 结尾 |
| `FLATPAK_REMOTE_NAME` | `my-flathub` |
| `FLATPAK_REPO_TITLE` | `My Flathub` |

另外创建 repository secret `FLATPAK_UPDATE_TOKEN`。它应是专用机器人账号的 fine-grained PAT，仅授权本仓库的 `Contents: Read and write`、`Pull requests: Read and write`；`Metadata: Read` 会自动附带。不要授予 Actions、Workflows 或 Administration 权限。设置到期日和轮换提醒。

建议为 `main` 启用分支保护，要求“Flatpak 持续集成”通过且必须由 PR 合并。external-data-checker 每日 03:17 UTC 为每个有更新的应用创建 PR；PAT 创建的 PR 会走与人工 PR 相同的常规 CI，但不会自动合并。

### Cloudflare R2 配置

1. 创建一个只存放此 Flatpak repo 的专用 bucket。发布使用严格镜像，bucket 中的任何额外对象都可能被删除。
2. 创建仅限该 bucket 的 Object Read & Write S3 API 凭据，并填入上述 Secrets。
3. 将自定义域名绑定到 bucket，等待证书状态变为 Active，并关闭 `r2.dev` 入口。
4. 创建 Cache Rules：
   - `/objects/*` 和 `/deltas/*`：Cache Everything，Edge TTL 一年；对象以 `Cache-Control: public, max-age=31536000, immutable` 上传。
   - 其他路径：Bypass cache，尤其是 `summary`、`summary.sig`、`refs/*`、`config`、AppStream 和 `repo.flatpakrepo`。

Flatpak CLI 不需要浏览器 CORS。发布脚本使用 R2 S3 endpoint `https://<account-id>.r2.cloudflarestorage.com`，因此不需要 `wrangler.toml`。

### 发布过程

PR 只构建和验证，不接触发布 Secrets。合并到 `main` 或手动运行“发布 Flatpak 仓库”工作流后，工作流会：

1. 从 R2 恢复当前 repo，首次发布则初始化 `archive-z2` repo。
2. 构建并签署所有应用，生成 AppStream、签名 summary 和 static deltas。
3. 保留当前及上一个版本并执行 prune。
4. 本地执行 `ostree fsck`、GPG 安装验证和示例程序 smoke test。
5. 先上传 objects/deltas，再更新其他元数据，最后更新 summary。
6. 使用 `rclone sync --delete-after` 删除远端多余对象并核对内容。
7. 通过公网域名检查描述文件、summary 和 `flatpak remote-ls`。

workflow 使用 concurrency 锁，两个发布不会同时写 bucket。更新可变元数据与删除旧对象之间仍存在很小的客户端竞态窗口；当前通过保留上一版本、最后删除及禁用可变元数据缓存来降低风险。
