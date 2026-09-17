# Worker 开发说明

Worker 仅使用 npm 和 TypeScript；仓库维护逻辑使用根目录的 uv Python 项目。不要在 `workers/` 中混用 Python 依赖或 Python 检查命令。

## 本地运行目录

Wrangler 的配置、缓存、日志和临时状态不应写入仓库目录。执行本目录的类型检查、测试或构建前，使用 `/tmp` 下的专用临时目录：

```console
worker_temp_dir="$(mktemp -d /tmp/my-flathub-worker.XXXXXX)"
trap 'rm -rf -- "$worker_temp_dir"' EXIT
export XDG_CONFIG_HOME="$worker_temp_dir/config"
export WRANGLER_LOG_PATH="$worker_temp_dir/wrangler/logs"

npm run typecheck --prefix workers
npm test --prefix workers
npm run build --prefix workers
```

不要使用固定的 `/tmp` 子目录，以免多个本地任务相互覆盖。命令结束后应清理该临时目录；上面的 `trap` 会在当前 shell 退出时自动清理。
