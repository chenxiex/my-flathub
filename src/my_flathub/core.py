"""Flatpak 仓库构建、验证和发布的可复用实现。"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as element_tree
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
HTTPS_ROOT_PATTERN = re.compile(r"https://[^/]+/")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class CommandError(RuntimeError):
    """外部命令执行失败。"""


def run(
    args: Sequence[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """运行外部命令，并把失败转换为带命令文本的异常。"""
    command = [str(part) for part in args]
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        input=input_text,
        capture_output=capture_output,
        check=False,
    )
    if result.returncode:
        details = result.stderr.strip() if capture_output else ""
        suffix = f"：{details}" if details else ""
        raise CommandError(f"命令失败：{' '.join(command)}{suffix}")
    return result


def run_bytes(
    args: Sequence[str | Path], *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[bytes]:
    """运行产生二进制输出的外部命令。"""
    command = [str(part) for part in args]
    result = subprocess.run(command, env=env, capture_output=True, check=False)
    if result.returncode:
        details = result.stderr.decode(errors="replace").strip()
        suffix = f"：{details}" if details else ""
        raise CommandError(f"命令失败：{' '.join(command)}{suffix}")
    return result


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise ValueError(f"缺少必需命令：{name}")


def root_path() -> Path:
    return Path.cwd()


def setting_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def discover_manifests(packages_dir: Path) -> list[Path]:
    if not packages_dir.is_dir():
        raise ValueError(f"软件包目录不存在：{packages_dir}")
    return sorted(
        path
        for path in packages_dir.glob("*/*")
        if path.is_file() and path.name == f"{path.parent.name}.yaml"
    )


@dataclass(frozen=True)
class FlatpakTools:
    """根据本机安装情况选择 Builder 和 linter 的调用路径。"""

    builder: tuple[str, ...]
    linter: tuple[str, ...]
    native_builder: bool

    @classmethod
    def create(cls, repository_root: Path) -> FlatpakTools:
        if shutil.which("flatpak-builder"):
            builder = ("flatpak-builder",)
            native_builder = True
        else:
            require_command("flatpak")
            result = subprocess.run(
                ["flatpak", "info", "org.flatpak.Builder"],
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode:
                raise ValueError(
                    "缺少 Flatpak Builder：请安装 flatpak-builder 或 org.flatpak.Builder"
                )
            builder = (
                "flatpak",
                "run",
                f"--filesystem={repository_root}",
                "--command=flatpak-builder",
                "org.flatpak.Builder",
            )
            native_builder = False
        if shutil.which("flatpak-builder-lint"):
            linter = ("flatpak-builder-lint",)
        elif not native_builder:
            linter = (
                "flatpak",
                "run",
                f"--filesystem={repository_root}",
                "--command=flatpak-builder-lint",
                "org.flatpak.Builder",
            )
        else:
            raise ValueError("缺少必需命令：flatpak-builder-lint")
        return cls(builder=builder, linter=linter, native_builder=native_builder)

    def build(
        self, *args: str | Path, capture_output: bool = False
    ) -> subprocess.CompletedProcess[str]:
        return run([*self.builder, *args], capture_output=capture_output)

    def lint(self, *args: str | Path) -> None:
        run([*self.linter, *args])


def manifest_app_id(manifest: dict[str, object]) -> str:
    app_id = manifest.get("app-id", manifest.get("id"))
    if not isinstance(app_id, str) or not app_id:
        raise ValueError("manifest 未设置 app-id")
    return app_id


def objects(value: object) -> Iterable[dict[str, object]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from objects(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from objects(nested)


def validate_manifest_data(
    manifest: dict[str, object], manifest_path: Path, package_name: str
) -> str:
    app_id = manifest_app_id(manifest)
    if app_id != package_name:
        raise ValueError(f"{manifest_path}：app-id“{app_id}”必须与目录名“{package_name}”一致")
    for key in ("runtime", "runtime-version", "sdk", "command"):
        if not isinstance(manifest.get(key), str) or not manifest[key]:
            raise ValueError(f"{manifest_path}：必须设置 runtime、runtime-version、sdk 和 command")
    for source in objects(manifest):
        source_type = source.get("type")
        if source_type in {"archive", "file", "extra-data"} and source.get("url"):
            sha256 = source.get("sha256")
            if not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
                raise ValueError(
                    f"{manifest_path}：每个远程 archive、file 或 extra-data 源都必须提供 SHA256"
                )
        if source_type == "git":
            commit = source.get("commit")
            if (
                "branch" in source
                or not isinstance(commit, str)
                or not GIT_COMMIT_PATTERN.fullmatch(commit)
            ):
                raise ValueError(f"{manifest_path}：Git 源必须使用完整提交哈希，且不得使用 branch")
    return app_id


def metainfo_component_id(path: Path) -> str:
    try:
        root = element_tree.parse(path).getroot()
    except element_tree.ParseError as error:
        raise ValueError(f"{path}：MetaInfo XML 无效：{error}") from error
    for child in root:
        if child.tag.rsplit("}", 1)[-1] == "id":
            return child.text or ""
    return ""


def lint_for_app(
    tools: FlatpakTools, repository_root: Path, app_id: str, *args: str | Path
) -> None:
    policy_path = repository_root / "tests/linter-repository-policy.json"
    exceptions_path = repository_root / "tests/linter-exceptions.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    exceptions = json.loads(exceptions_path.read_text(encoding="utf-8"))
    ignored = sorted(set(policy["ignored_error_codes"]) | set(exceptions.get(app_id, [])))
    with tempfile.NamedTemporaryFile(
        mode="w",
        prefix=".flatpak-lint-exceptions.",
        suffix=".json",
        dir=repository_root,
        encoding="utf-8",
        delete=False,
    ) as handle:
        json.dump({app_id: ignored}, handle)
        exceptions_file = Path(handle.name)
    try:
        tools.lint("--exceptions", "--user-exceptions", exceptions_file, "--appid", app_id, *args)
    finally:
        exceptions_file.unlink(missing_ok=True)


def validate_manifests(repository_root: Path) -> list[Path]:
    require_command("xmllint")
    tools = FlatpakTools.create(repository_root)
    manifests = discover_manifests(repository_root / "packages")
    if not manifests:
        raise ValueError("packages/ 下未发现 Flatpak manifest")
    seen: dict[str, Path] = {}
    for path in manifests:
        package_name = path.parent.name
        expected = path.parent / f"{package_name}.yaml"
        if path != expected:
            raise ValueError(f"{path}：文件路径必须为 {expected}")
        raw_manifest = tools.build("--show-manifest", path, capture_output=True).stdout
        manifest = json.loads(raw_manifest)
        if not isinstance(manifest, dict):
            raise ValueError(f"{path}：解析后的 manifest 必须是对象")
        app_id = validate_manifest_data(manifest, path, package_name)
        if app_id in seen:
            raise ValueError(f"{path}：app-id“{app_id}”重复，另见 {seen[app_id]}")
        seen[app_id] = path
        metainfo = path.parent / f"{app_id}.metainfo.xml"
        if not metainfo.is_file():
            raise ValueError(f"{path}：缺少必需的 MetaInfo 文件：{metainfo}")
        if metainfo_component_id(metainfo) != app_id:
            raise ValueError(
                f"{metainfo}：组件 ID“{metainfo_component_id(metainfo)}”与“{app_id}”不一致"
            )
        lint_for_app(tools, repository_root, app_id, "--gha-format", "manifest", path)
        tools.lint("--gha-format", "appstream", metainfo)
    print(f"已验证 {len(manifests)} 个 Flatpak manifest。")
    return manifests


def build_repository(repository_root: Path) -> None:
    tools = FlatpakTools.create(repository_root)
    manifests = validate_manifests(repository_root)
    repo_dir = setting_path("REPO_DIR", "repo")
    build_root = setting_path("BUILD_ROOT", "build")
    state_dir = setting_path("STATE_DIR", ".flatpak-builder")
    arch = os.environ.get("FLATPAK_ARCH", "x86_64")
    branch = os.environ.get("FLATPAK_BRANCH", "stable")
    runtime_repo = os.environ.get(
        "FLATPAK_RUNTIME_REPO", "https://dl.flathub.org/repo/flathub.flatpakrepo"
    )
    repo_dir.mkdir(parents=True, exist_ok=True)
    build_root.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    if not (repo_dir / "config").is_file():
        run(["ostree", f"--repo={repo_dir}", "init", "--mode=archive-z2"])
    run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", runtime_repo])
    for manifest in manifests:
        args: list[str | Path] = [
            f"--arch={arch}",
            f"--default-branch={branch}",
            "--disable-rofiles-fuse",
            "--disable-updates",
            "--force-clean",
            "--install-deps-from=flathub",
            f"--repo={repo_dir}",
            f"--state-dir={state_dir}",
        ]
        if tools.native_builder:
            args.append("--user")
        if key_id := os.environ.get("GPG_KEY_ID"):
            args.append(f"--gpg-sign={key_id}")
        tools.build(*args, build_root / manifest.parent.name, manifest)


def require_repo(repo_dir: Path) -> None:
    if not (repo_dir / "config").is_file():
        raise ValueError(f"未找到 OSTree 仓库：{repo_dir}")


def finalize_repository() -> None:
    key_id = os.environ.get("GPG_KEY_ID")
    if not key_id:
        raise ValueError("必须设置 GPG_KEY_ID")
    repo_dir = setting_path("REPO_DIR", "repo")
    require_repo(repo_dir)
    run(
        [
            "flatpak",
            "build-update-repo",
            f"--gpg-sign={key_id}",
            "--generate-static-deltas",
            "--prune",
            "--prune-depth=1",
            repo_dir,
        ]
    )


def generate_flatpakrepo() -> None:
    key_id = os.environ.get("GPG_KEY_ID")
    repo_url = os.environ.get("FLATPAK_REPO_URL", "")
    repo_title = os.environ.get("FLATPAK_REPO_TITLE", "My Flathub")
    if not key_id:
        raise ValueError("必须设置 GPG_KEY_ID")
    if not HTTPS_ROOT_PATTERN.fullmatch(repo_url):
        raise ValueError("FLATPAK_REPO_URL 必须是以“/”结尾的 HTTPS URL")
    exported = run_bytes(["gpg", "--batch", "--export", key_id]).stdout
    if not exported:
        raise ValueError(f"无法导出 {key_id} 对应的公钥")
    repo_dir = setting_path("REPO_DIR", "repo")
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "repo.flatpakrepo").write_text(
        "[Flatpak Repo]\n"
        f"Title={repo_title}\n"
        f"Url={repo_url}\n"
        "Comment=由 My Flathub 发布的应用程序\n"
        "Description=由 My Flathub monorepo 构建并发布的应用程序\n"
        f"GPGKey={base64.b64encode(exported).decode()}\n",
        encoding="utf-8",
    )


def prepare_preview_repository(repository_root: Path) -> None:
    base_url = os.environ.get("PR_PREVIEW_BASE_URL", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    head_sha = os.environ.get("PR_HEAD_SHA", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if not HTTPS_ROOT_PATTERN.fullmatch(base_url):
        raise ValueError("PR_PREVIEW_BASE_URL 必须是 HTTPS Worker 根地址，并以 / 结尾")
    if not all(
        value.isdecimal() and int(value) > 0 for value in (pr_number, run_id, run_attempt)
    ) or not SHA_PATTERN.fullmatch(head_sha):
        raise ValueError("PR 编号、运行 ID、重试次数或提交 SHA 无效")
    repo_dir = setting_path("REPO_DIR", "repo")
    require_repo(repo_dir)
    runner_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
    with tempfile.TemporaryDirectory(prefix="preview-gnupg.", dir=runner_temp) as key_directory:
        key_env = {**os.environ, "GNUPGHOME": key_directory}
        Path(key_directory).chmod(0o700)
        run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-generate-key",
                f"My Flathub PR #{pr_number} run {run_id}-{run_attempt}",
                "ed25519",
                "sign",
                "6d",
            ],
            env=key_env,
        )
        output = run(
            ["gpg", "--batch", "--with-colons", "--list-secret-keys"],
            env=key_env,
            capture_output=True,
        ).stdout
        key_id = next(
            (line.split(":")[9] for line in output.splitlines() if line.startswith("fpr:")), ""
        )
        if not key_id:
            raise ValueError("无法读取预览仓库签名密钥")
        arch = os.environ.get("FLATPAK_ARCH", "x86_64")
        refs = run(
            ["ostree", f"--repo={repo_dir}", "refs"], capture_output=True
        ).stdout.splitlines()
        for ref in refs:
            if ref.startswith(("appstream/", "appstream2/")):
                continue
            parts = ref.split("/")
            if (
                len(parts) != 4
                or parts[0] not in {"app", "runtime"}
                or parts[2] != arch
                or parts[3] != "test"
            ):
                raise ValueError(f"预览仓库中存在意外的 ref：{ref}")
            args = ["flatpak", "build-sign", f"--gpg-sign={key_id}", f"--arch={arch}"]
            if parts[0] == "runtime":
                args.append("--runtime")
            run([*args, repo_dir, parts[1], parts[3]], env=key_env)
        run(
            [
                "flatpak",
                "build-update-repo",
                f"--gpg-sign={key_id}",
                "--prune",
                "--prune-depth=0",
                repo_dir,
            ],
            env=key_env,
        )
        replacement = {
            "GPG_KEY_ID": key_id,
            "FLATPAK_REPO_URL": f"{base_url}pr/{pr_number}/{run_id}-{run_attempt}/",
            "FLATPAK_REPO_TITLE": f"My Flathub PR #{pr_number} 测试仓库",
        }
        original = {name: os.environ.get(name) for name in replacement}
        try:
            os.environ.update(replacement)
            generate_flatpakrepo()
        finally:
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        public_key = run_bytes(["gpg", "--batch", "--export", key_id], env=key_env).stdout
        (runner_temp / "preview-public.gpg").write_bytes(public_key)
    (repository_root / "preview.json").write_text(
        json.dumps(
            {
                "pr_number": int(pr_number),
                "run_id": int(run_id),
                "run_attempt": int(run_attempt),
                "head_sha": head_sha,
            }
        ),
        encoding="utf-8",
    )


RCLONE_FILTERS = (
    "--exclude",
    "/.lock",
    "--exclude",
    "/state/**",
    "--exclude",
    "/tmp/**",
    "--exclude",
    "/uncompressed-objects-cache/**",
)


def r2_repository(operation: str) -> None:
    values = {
        key: os.environ.get(key, "")
        for key in ("R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
    }
    for key, value in values.items():
        if not value:
            raise ValueError(f"必须设置 {key}")
    repo_dir = setting_path("REPO_DIR", "repo")
    environment = {
        **os.environ,
        "RCLONE_CONFIG_R2_TYPE": "s3",
        "RCLONE_CONFIG_R2_PROVIDER": "Cloudflare",
        "RCLONE_CONFIG_R2_ACCESS_KEY_ID": values["R2_ACCESS_KEY_ID"],
        "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY": values["R2_SECRET_ACCESS_KEY"],
        "RCLONE_CONFIG_R2_ENDPOINT": f"https://{values['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        "RCLONE_CONFIG_R2_NO_CHECK_BUCKET": "true",
    }
    remote = f"r2:{values['R2_BUCKET']}"
    if operation == "pull":
        repo_dir.mkdir(parents=True, exist_ok=True)
        run(["rclone", "copy", remote, repo_dir, "--fast-list", *RCLONE_FILTERS], env=environment)
        if (repo_dir / "config").is_file():
            (repo_dir / "refs/remotes").mkdir(parents=True, exist_ok=True)
            (repo_dir / "refs/mirrors").mkdir(parents=True, exist_ok=True)
        return
    if operation != "push":
        raise ValueError("用法：r2 pull|push")
    for required in ("config", "summary", "summary.sig"):
        if not (repo_dir / required).is_file():
            raise ValueError("发布前必须完成仓库元数据生成和签名")
    for directory in ("objects", "deltas"):
        source = repo_dir / directory
        if source.is_dir():
            run(
                [
                    "rclone",
                    "copy",
                    source,
                    f"{remote}/{directory}",
                    "--fast-list",
                    "--header-upload",
                    "Cache-Control: public, max-age=31536000, immutable",
                ],
                env=environment,
            )
    run(
        [
            "rclone",
            "copy",
            repo_dir,
            remote,
            "--fast-list",
            "--exclude",
            "/objects/**",
            "--exclude",
            "/deltas/**",
            "--exclude",
            "/summary",
            "--exclude",
            "/summary.sig",
            "--header-upload",
            "Cache-Control: no-cache",
            *RCLONE_FILTERS,
        ],
        env=environment,
    )
    for filename in ("summary.sig", "summary"):
        run(
            [
                "rclone",
                "copyto",
                repo_dir / filename,
                f"{remote}/{filename}",
                "--header-upload",
                "Cache-Control: no-cache",
            ],
            env=environment,
        )
    run(
        ["rclone", "sync", repo_dir, remote, "--fast-list", "--delete-after", *RCLONE_FILTERS],
        env=environment,
    )
    run(["rclone", "check", repo_dir, remote, "--fast-list", *RCLONE_FILTERS], env=environment)


def verify_repository(repository_root: Path) -> None:
    repo_dir = setting_path("REPO_DIR", "repo")
    arch = os.environ.get("FLATPAK_ARCH", "x86_64")
    branch = os.environ.get("FLATPAK_BRANCH", "stable")
    test_app = os.environ.get("FLATPAK_TEST_APP", "org.example.FlatpakHello")
    require_repo(repo_dir)
    run(["ostree", f"--repo={repo_dir}", "fsck"])
    tools = FlatpakTools.create(repository_root)
    manifests = discover_manifests(repository_root / "packages")
    if not manifests:
        raise ValueError("packages/ 下未发现 Flatpak manifest")
    for manifest in manifests:
        app_id = manifest.parent.name
        lint_for_app(
            tools,
            repository_root,
            app_id,
            "--ref",
            f"app/{app_id}/{arch}/{branch}",
            "--gha-format",
            "repo",
            repo_dir,
        )
    with tempfile.TemporaryDirectory(prefix="my-flathub-test-") as test_root:
        environment = {**os.environ, "XDG_DATA_HOME": str(Path(test_root) / "data")}
        flatpak_args = ["flatpak", "remote-add", "--user"]
        if public_key := os.environ.get("FLATPAK_GPG_PUBLIC_KEY_FILE"):
            flatpak_args.append(f"--gpg-import={public_key}")
        else:
            flatpak_args.append("--no-gpg-verify")
        run([*flatpak_args, "my-flathub-test", f"file://{repo_dir.resolve()}"], env=environment)
        run(["flatpak", "remote-ls", "--user", "my-flathub-test"], env=environment)
        run(
            [
                "flatpak",
                "install",
                "--user",
                "--noninteractive",
                "my-flathub-test",
                f"{test_app}//{branch}",
            ],
            env=environment,
        )
        output = run(
            ["flatpak", "run", "--user", f"--arch={arch}", f"--branch={branch}", test_app],
            env=environment,
            capture_output=True,
        ).stdout.strip()
    if output != "来自 My Flathub 的问候！":
        raise ValueError(f"冒烟测试输出不符合预期：{output}")


def probe_public_repository() -> None:
    repo_url = os.environ.get("FLATPAK_REPO_URL", "")
    remote_name = os.environ.get("FLATPAK_REMOTE_NAME", "my-flathub")
    if not HTTPS_ROOT_PATTERN.fullmatch(repo_url):
        raise ValueError("FLATPAK_REPO_URL 必须是以“/”结尾的 HTTPS URL")
    for filename in ("repo.flatpakrepo", "summary"):
        run(
            [
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--retry",
                "5",
                "--retry-all-errors",
                "--output",
                "/dev/null",
                f"{repo_url}{filename}",
            ]
        )
    with tempfile.TemporaryDirectory(prefix="my-flathub-public-") as test_root:
        environment = {**os.environ, "XDG_DATA_HOME": str(Path(test_root) / "data")}
        run(
            [
                "flatpak",
                "remote-add",
                "--user",
                "--if-not-exists",
                remote_name,
                f"{repo_url}repo.flatpakrepo",
            ],
            env=environment,
        )
        run(["flatpak", "remote-ls", "--user", remote_name], env=environment)
