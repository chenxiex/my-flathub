# My Flathub

这是一个通过 GitHub Actions 构建、签名并发布到 Cloudflare R2 的 Flatpak
monorepo。首版发布 `x86_64/stable`，R2 bucket 的根目录就是 OSTree repository。

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

补丁、图标、Desktop 文件和本地辅助源码也应放入应用目录。新增应用后，发现脚本
会自动将它加入 CI、发布和上游版本检查，无需维护第二份应用列表。

远程 `archive`、`file` 和 `extra-data` 源必须提供 SHA256；Git 源必须固定完整
commit，不能追踪 branch。需要自动更新的源应添加标准 `x-checker-data`。

## 本地构建

系统安装 `flatpak-builder` 时运行：

```console
bash scripts/build-repo.sh
bash tests/verify-repo.sh
```

也可以使用 Flathub 的 Builder Flatpak：

```console
flatpak install flathub org.flatpak.Builder
flatpak run --filesystem="$PWD" --command=flatpak-builder \
  org.flatpak.Builder --force-clean --disable-rofiles-fuse \
  --install-deps-from=flathub build/org.example.FlatpakHello \
  packages/org.example.FlatpakHello/org.example.FlatpakHello.yaml
```

完整 monorepo 构建由 CI 使用固定 digest 的
`ghcr.io/flathub-infra/flatpak-github-actions:freedesktop-25.08` 执行。

## GPG 发布密钥

建议生成只用于本源、没有口令的独立密钥。密钥泄露时应立即停止发布、轮换密钥并
向所有用户重新分发 `.flatpakrepo`；已安装 remote 的信任密钥不会自动替换。

```console
gpg --batch --quick-generate-key "My Flathub Release <flatpak@example.com>" ed25519 sign 2y
gpg --armor --export-secret-keys "My Flathub Release" > private.asc
gpg --export "My Flathub Release" > public-key.gpg
```

将 `private.asc` 的完整内容保存为 GitHub `production` environment secret
`FLATPAK_GPG_PRIVATE_KEY`，不要提交私钥。公钥会在发布时由私钥导出并嵌入
`my-flathub.flatpakrepo`。

## GitHub 配置

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

另外创建 repository secret `FLATPAK_UPDATE_TOKEN`。它应是专用机器人账号的
fine-grained PAT，仅授权本仓库的 `Contents: Read and write`、
`Pull requests: Read and write`；`Metadata: Read` 会自动附带。不要授予 Actions、
Workflows 或 Administration 权限。设置到期日和轮换提醒。

建议为 `main` 启用分支保护，要求“Flatpak 持续集成”通过且必须由 PR 合并。
external-data-checker 每日 03:17 UTC 为每个有更新的应用创建 PR；PAT 创建的 PR 会
走与人工 PR 相同的常规 CI，但不会自动合并。

## Cloudflare R2 配置

1. 创建一个只存放此 Flatpak repo 的专用 bucket。发布使用严格镜像，bucket 中的
   任何额外对象都可能被删除。
2. 创建仅限该 bucket 的 Object Read & Write S3 API 凭据，并填入上述 Secrets。
3. 将自定义域名绑定到 bucket，等待证书状态变为 Active，并关闭 `r2.dev` 入口。
4. 创建 Cache Rules：
   - `/objects/*` 和 `/deltas/*`：Cache Everything，Edge TTL 一年；对象以
     `Cache-Control: public, max-age=31536000, immutable` 上传。
   - 其他路径：Bypass cache，尤其是 `summary`、`summary.sig`、`refs/*`、
     `config`、AppStream 和 `my-flathub.flatpakrepo`。

Flatpak CLI 不需要浏览器 CORS。发布脚本使用 R2 S3 endpoint
`https://<account-id>.r2.cloudflarestorage.com`，因此不需要 `wrangler.toml`。

## 发布过程

PR 只构建和验证，不接触发布 Secrets。合并到 `main` 或手动运行“发布 Flatpak 仓库”工作流
后，工作流会：

1. 从 R2 恢复当前 repo，首次发布则初始化 `archive-z2` repo。
2. 构建并签署所有应用，生成 AppStream、签名 summary 和 static deltas。
3. 保留当前及上一个版本并执行 prune。
4. 本地执行 `ostree fsck`、GPG 安装验证和示例程序 smoke test。
5. 先上传 objects/deltas，再更新其他元数据，最后更新 summary。
6. 使用 `rclone sync --delete-after` 删除远端多余对象并核对内容。
7. 通过公网域名检查描述文件、summary 和 `flatpak remote-ls`。

workflow 使用 concurrency 锁，两个发布不会同时写 bucket。更新可变元数据与删除旧
对象之间仍存在很小的客户端竞态窗口；当前通过保留上一版本、最后删除及禁用可变
元数据缓存来降低风险。

## 添加和使用源

发布成功后，用户运行：

```console
flatpak remote-add --if-not-exists my-flathub \
  https://flatpak.example.com/my-flathub.flatpakrepo
flatpak remote-ls my-flathub
flatpak install my-flathub org.example.FlatpakHello
```

如果发布失败，先查看失败发生在上传前还是上传后。上传前失败不会改变 R2；上传后
失败时重新运行“发布 Flatpak 仓库”工作流，它会先恢复当前远端状态并重新生成一致的 summary。
不要手工删除 `objects/` 或 `deltas/` 中的对象。
