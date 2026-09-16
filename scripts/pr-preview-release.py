#!/usr/bin/env python3
"""发布和清理 PR 测试仓库；只在默认分支的特权工作流中运行。"""

import argparse
import configparser
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


TAG_PATTERN = re.compile(r"^pr-preview-([1-9][0-9]*)-([1-9][0-9]*)-([1-9][0-9]*)$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PATH_PART_PATTERN = re.compile(r"^[A-Za-z0-9._+-]+$")
COMMENT_MARKER = "<!-- my-flathub-pr-preview -->"
MAX_ASSETS = 1000
MAX_ASSET_BYTES = 2 * 1024**3


def gh(*args):
    result = subprocess.run(
        ["gh", *map(str, args)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"gh {' '.join(map(str, args))} 失败：{result.stderr.strip()}")
    return result.stdout


def gh_json(path, method="GET", fields=None):
    args = ["api", "--method", method, path]
    for key, value in (fields or {}).items():
        args.extend(["--raw-field", f"{key}={value}"])
    output = gh(*args)
    return json.loads(output) if output else None


def releases(repo):
    page = 1
    while True:
        batch = gh_json(f"repos/{repo}/releases?per_page=100&page={page}")
        if not batch:
            return
        yield from batch
        if len(batch) < 100:
            return
        page += 1


def delete_release(repo, tag):
    print(f"删除预览 Release：{tag}", flush=True)
    gh("release", "delete", tag, "--cleanup-tag", "--yes", "--repo", repo)


def delete_artifact(repo, run_id, name):
    artifacts = gh_json(f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    for artifact in artifacts:
        if artifact["name"] == name:
            gh_json(f"repos/{repo}/actions/artifacts/{artifact['id']}", "DELETE")
            return
    print(f"未找到需要删除的临时 artifact：{name}", flush=True)


def cleanup(repo, number=None, keep=None):
    now = dt.datetime.now(dt.timezone.utc)
    for release in releases(repo):
        tag = release["tag_name"]
        match = TAG_PATTERN.fullmatch(tag)
        if not match or tag == keep:
            continue
        if number is not None:
            if int(match.group(1)) != number:
                continue
        else:
            date_text = release["published_at"] or release["created_at"]
            created = dt.datetime.fromisoformat(date_text.replace("Z", "+00:00"))
            if now - created < dt.timedelta(days=5):
                continue
        delete_release(repo, tag)


def newer_release_exists(repo, number, run_id, attempt):
    for release in releases(repo):
        match = TAG_PATTERN.fullmatch(release["tag_name"])
        if match and not release["draft"] and int(match.group(1)) == number:
            if (int(match.group(2)), int(match.group(3))) >= (run_id, attempt):
                return True
    return False


def validate_repo(root, expected_url):
    if not root.is_dir() or root.is_symlink():
        raise ValueError("构建产物缺少 repo 目录")
    files = []
    for path in root.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError(f"产物含有不允许的文件类型：{path}")
        relative = path.relative_to(root)
        if not all(PATH_PART_PATTERN.fullmatch(part) and part not in (".", "..") for part in relative.parts):
            raise ValueError(f"产物含有不允许的路径：{relative}")
        if stat.S_ISREG(mode):
            if path.stat().st_size >= MAX_ASSET_BYTES:
                raise ValueError(f"单文件超过 GitHub Release 限制：{relative}")
            files.append((path, relative.as_posix()))
    if len(files) > MAX_ASSETS:
        raise ValueError(f"仓库需要 {len(files)} 个附件，超过每个 Release 的 {MAX_ASSETS} 个上限")

    for required in ("config", "summary", "summary.sig", "repo.flatpakrepo"):
        if not (root / required).is_file():
            raise ValueError(f"构建产物缺少 {required}")
    config = configparser.ConfigParser(interpolation=None)
    config.read(root / "repo.flatpakrepo", encoding="utf-8")
    if config.get("Flatpak Repo", "Url") != expected_url:
        raise ValueError("repo.flatpakrepo 中的 URL 与本次运行不符")
    if not config.get("Flatpak Repo", "GPGKey"):
        raise ValueError("repo.flatpakrepo 缺少 GPG 公钥")
    return sorted(files, key=lambda item: item[1])


def preview_app_ids(root):
    refs = root / "refs" / "heads" / "app"
    app_ids = sorted(path.name for path in refs.iterdir() if (path / "x86_64" / "test").is_file())
    if not app_ids or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", app_id) for app_id in app_ids):
        raise ValueError("预览仓库没有有效的 test 分支应用")
    return app_ids


def comment_on_pr(repo, number, body):
    comments = []
    page = 1
    while True:
        batch = gh_json(f"repos/{repo}/issues/{number}/comments?per_page=100&page={page}")
        comments.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    own = next(
        (
            item for item in reversed(comments)
            if COMMENT_MARKER in item["body"] and item["user"]["login"] == "github-actions[bot]"
        ),
        None,
    )
    if own:
        gh_json(f"repos/{repo}/issues/comments/{own['id']}", "PATCH", {"body": body})
    else:
        gh_json(f"repos/{repo}/issues/{number}/comments", "POST", {"body": body})


def publish(repo, base_url, event_file):
    event = json.loads(event_file.read_text(encoding="utf-8"))
    run = event["workflow_run"]
    if run["event"] != "pull_request" or run["conclusion"] != "success":
        raise ValueError("仅发布成功的 PR CI 构建")
    if run["path"] != ".github/workflows/ci.yml" or run["repository"]["full_name"] != repo:
        raise ValueError("工作流或仓库来源不符")
    run_id = int(run["id"])
    attempt = int(run["run_attempt"])
    artifact_name = f"pr-preview-repo-{attempt}"

    with tempfile.TemporaryDirectory(prefix="pr-preview-") as temp:
        temp_path = Path(temp)
        gh("run", "download", run_id, "--name", artifact_name,
           "--dir", temp_path / "artifact", "--repo", repo)
        artifact = temp_path / "artifact"
        metadata_path = artifact / "preview.json"
        if artifact.is_symlink() or not stat.S_ISREG(metadata_path.lstat().st_mode):
            raise ValueError("预览元数据必须是普通文件")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        number = metadata["pr_number"]
        head_sha = metadata["head_sha"]
        if not isinstance(number, int) or number <= 0 or not isinstance(head_sha, str) or not SHA_PATTERN.fullmatch(head_sha):
            raise ValueError("构建产物的 PR 元数据无效")
        if metadata["run_id"] != run_id or metadata["run_attempt"] != attempt:
            raise ValueError("构建产物的运行 ID 不符")

        pr = gh_json(f"repos/{repo}/pulls/{number}")
        if pr["state"] != "open" or pr["head"]["sha"] != head_sha:
            print("PR 已关闭或有了新提交，跳过过期构建", flush=True)
            delete_artifact(repo, run_id, artifact_name)
            return
        if run["head_sha"] != head_sha:
            raise ValueError("CI 运行的提交与 PR 不符")
        linked = run.get("pull_requests") or []
        if linked and not any(item["number"] == number for item in linked):
            raise ValueError("CI 运行未关联到产物声称的 PR")
        if newer_release_exists(repo, number, run_id, attempt):
            print("该 PR 已有更新的测试仓库，跳过过期构建", flush=True)
            delete_artifact(repo, run_id, artifact_name)
            return

        preview_id = f"{run_id}-{attempt}"
        tag = f"pr-preview-{number}-{preview_id}"
        url = f"{base_url}pr/{number}/{preview_id}/"
        files = validate_repo(artifact / "repo", url)
        app_ids = preview_app_ids(artifact / "repo")
        staged = temp_path / "assets"
        staged.mkdir()
        for path, relative in files:
            asset_name = "f-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()
            os.link(path, staged / asset_name)

        print(f"上传 {len(files)} 个仓库文件到 {tag}", flush=True)
        gh("release", "create", tag, "--draft", "--prerelease", "--target", "main",
           "--title", f"PR #{number} 测试构建 {preview_id}",
           "--notes", "临时测试仓库；请使用 PR 中的安装说明。", "--repo", repo)
        published = False
        try:
            asset_paths = sorted(staged.iterdir())
            for start in range(0, len(asset_paths), 20):
                gh("release", "upload", tag, "--repo", repo, *asset_paths[start:start + 20])

            current = gh_json(f"repos/{repo}/pulls/{number}")
            if current["state"] != "open" or current["head"]["sha"] != head_sha:
                print("上传期间 PR 已更新或关闭，丢弃过期构建", flush=True)
                delete_release(repo, tag)
                delete_artifact(repo, run_id, artifact_name)
                return
            if newer_release_exists(repo, number, run_id, attempt):
                print("上传期间出现更新的测试仓库，丢弃过期构建", flush=True)
                delete_release(repo, tag)
                delete_artifact(repo, run_id, artifact_name)
                return

            gh("release", "edit", tag, "--draft=false", "--repo", repo)
            published = True
            remote = f"my-flathub-pr-{number}-{run_id}-{attempt}"
            install_commands = "".join(
                f"flatpak install --user {remote} {app_id}//test\n" for app_id in app_ids
            )
            body = (
                f"{COMMENT_MARKER}\n"
                f"PR 测试仓库已生成：[查看临时 Release](https://github.com/{repo}/releases/tag/{tag})。"
                "仓库保留 5 天，PR 关闭或新构建发布后可能提前清理。\n\n"
                "```console\n"
                f"flatpak remote-add --user {remote} {url}repo.flatpakrepo\n"
                f"{install_commands}"
                "```\n\n"
                "测试结束后可用 `flatpak remote-delete --user " + remote + "` 移除仓库。"
                "预览应用来自 PR 内容，请仅在隔离的测试环境中运行。"
            )
            comment_on_pr(repo, number, body)
        except Exception:
            if not published:
                delete_release(repo, tag)
            raise
        delete_artifact(repo, run_id, artifact_name)
        cleanup(repo, number=number, keep=tag)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("publish", "cleanup"))
    parser.add_argument("--pr", type=int)
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("GITHUB_REPOSITORY 无效")
    if args.operation == "cleanup":
        cleanup(repo, number=args.pr)
        return
    base_url = os.environ["PR_PREVIEW_BASE_URL"]
    if not re.fullmatch(r"https://[^/]+/", base_url):
        raise ValueError("PR_PREVIEW_BASE_URL 必须是 HTTPS Worker 根地址")
    publish(repo, base_url, Path(os.environ["GITHUB_EVENT_PATH"]))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"PR 测试仓库操作失败：{error}", file=sys.stderr)
        sys.exit(1)
