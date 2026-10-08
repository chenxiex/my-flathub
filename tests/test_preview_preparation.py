"""预览 URL 校验、隔离签名环境和真实公钥导出的回归测试。"""

from __future__ import annotations

import base64
import configparser
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from my_flathub import core
from my_flathub.cli import cli


@pytest.mark.parametrize(
    "url",
    ["https://example.invalid/", "https://example.invalid/pr/4/123-1/", "https://[::1]:443/"],
)
def test_repository_url_accepts_https_paths(url: str) -> None:
    core.validate_https_url(url, source="环境变量 FLATPAK_REPO_URL")


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://example.invalid/",
        "https:///",
        "https://example.invalid",
        "https://example.invalid/pr/4",
        "https://example.invalid:bad/",
        "https://example.invalid:65536/",
        "https://example.invalid:0/",
        "https://example.invalid:/",
        "https://bad_host/",
        "https://%host/",
        "https://-host/",
        "https://host..invalid/",
        "https://user:password@example.invalid/",
        "https://example.invalid/?query=value",
        "https://example.invalid/#fragment",
        "https://example.invalid/?",
        "https://example.invalid/#",
        " https://example.invalid/",
        "https://example.invalid/path with space/",
        "https://example.invalid/\n",
        "https://example.invalid/\x00/",
    ],
)
def test_repository_url_rejects_invalid_inputs_with_source(url: str) -> None:
    source = "环境变量 FLATPAK_REPO_URL"
    with pytest.raises(ValueError, match=source):
        core.validate_https_url(url, source=source)


def test_preview_base_url_requires_root() -> None:
    core.validate_https_url("https://example.invalid/", source="配置", root_only=True)
    with pytest.raises(ValueError, match="环境变量 PR_PREVIEW_BASE_URL.*根"):
        core.validate_https_url(
            "https://example.invalid/pr/", source="环境变量 PR_PREVIEW_BASE_URL", root_only=True
        )


def test_generated_url_error_identifies_internal_stage(tmp_path: Path) -> None:
    env = {
        "REPO_DIR": str(tmp_path / "repo"),
        "GPG_KEY_ID": "key",
        "FLATPAK_REPO_URL": "https://example.invalid/pr/4",
    }
    source = "内部生成的 PR 预览仓库 URL（prepare-preview-repo）"
    with patch.object(core, "run_bytes") as export, pytest.raises(ValueError) as error:
        core.generate_flatpakrepo(env=env, url_source=source)
    assert source in str(error.value)
    assert "环境变量 FLATPAK_REPO_URL" not in str(error.value)
    export.assert_not_called()


@pytest.fixture
def preview_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config").write_text("[core]\nrepo_version=1\n", encoding="utf-8")
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    for name, value in {
        "REPO_DIR": str(repo),
        "RUNNER_TEMP": str(runner_temp),
        "PR_PREVIEW_BASE_URL": "https://example.invalid/",
        "PR_NUMBER": "4",
        "PR_HEAD_SHA": "a" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GPG_KEY_ID": "existing-key",
        "FLATPAK_REPO_URL": "https://existing.invalid/",
        "FLATPAK_REPO_TITLE": "已有仓库",
    }.items():
        monkeypatch.setenv(name, value)
    return tmp_path


@pytest.mark.parametrize("export_fails", [False, True])
def test_preview_preparation_keeps_global_environment(
    preview_environment: Path, export_fails: bool
) -> None:
    original = dict(os.environ)
    key = b"\x00\xffpublic-key"
    key_id = "B" * 40
    signing_homes: list[str] = []
    export_homes: list[str] = []

    def run(
        args: Sequence[str | Path], *, env: dict[str, str] | None = None, **_: object
    ) -> subprocess.CompletedProcess[str]:
        command = [str(arg) for arg in args]
        assert dict(os.environ) == original
        if command[0] in {"gpg", "flatpak"}:
            assert env is not None
            signing_homes.append(env["GNUPGHOME"])
        if "--list-secret-keys" in command:
            output = f"fpr:::::::::{key_id}:\n"
        elif command[0] == "ostree":
            output = "app/org.example.App/x86_64/test\nappstream/x86_64\n"
        else:
            output = ""
        return subprocess.CompletedProcess(command, 0, output, "")

    def export(
        args: Sequence[str | Path], *, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        assert dict(os.environ) == original
        assert env is not None
        export_homes.append(env["GNUPGHOME"])
        assert Path(env["GNUPGHOME"]).is_dir()
        if export_fails:
            raise core.CommandError("模拟导出失败")
        return subprocess.CompletedProcess([str(arg) for arg in args], 0, key, b"")

    with (
        patch.object(core, "run", side_effect=run),
        patch.object(core, "run_bytes", side_effect=export),
    ):
        if export_fails:
            with pytest.raises(core.CommandError, match=f"repo.flatpakrepo.*{key_id}.*公钥失败"):
                core.prepare_preview_repository(preview_environment)
        else:
            core.prepare_preview_repository(preview_environment)

    assert dict(os.environ) == original
    assert signing_homes and export_homes
    assert len(set(signing_homes + export_homes)) == 1
    assert not Path(signing_homes[0]).exists()
    if not export_fails:
        descriptor = configparser.ConfigParser(interpolation=None)
        descriptor.read(preview_environment / "repo/repo.flatpakrepo", encoding="utf-8")
        assert descriptor["Flatpak Repo"]["Url"] == "https://example.invalid/pr/4/123-2/"
        assert base64.b64decode(descriptor["Flatpak Repo"]["GPGKey"]) == key
        assert (preview_environment / "runner/preview-public.gpg").read_bytes() == key
        metadata = json.loads((preview_environment / "preview.json").read_text(encoding="utf-8"))
        assert metadata["pr_number"] == 4
        assert metadata["run_id"] == 123


def test_real_preview_key(preview_environment: Path) -> None:
    original = dict(os.environ)
    actual_run = core.run
    homes: list[str] = []

    def run(
        args: Sequence[str | Path], *, env: dict[str, str] | None = None, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        command = [str(arg) for arg in args]
        if command[0] == "gpg":
            assert env is not None
            homes.append(env["GNUPGHOME"])
            result = actual_run(command, env=env, capture_output=True)
            if "--list-secret-keys" in command:
                # 在临时目录删除前关闭本次生成密钥的 agent。
                actual_run(["gpgconf", "--kill", "gpg-agent"], env=env, capture_output=True)
            return result
        output = "app/org.example.App/x86_64/test\n" if command[0] == "ostree" else ""
        return subprocess.CompletedProcess(command, 0, output, "")

    with patch.object(core, "run", side_effect=run):
        core.prepare_preview_repository(preview_environment)

    assert dict(os.environ) == original
    assert len(set(homes)) == 1
    descriptor = configparser.ConfigParser(interpolation=None)
    descriptor.read(preview_environment / "repo/repo.flatpakrepo", encoding="utf-8")
    public_key = (preview_environment / "runner/preview-public.gpg").read_bytes()
    assert public_key
    assert base64.b64decode(descriptor["Flatpak Repo"]["GPGKey"]) == public_key
    assert not Path(homes[0]).exists()


def test_invalid_preview_base_fails_before_key_creation(
    preview_environment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PR_PREVIEW_BASE_URL", "https://example.invalid/pr/")
    with (
        patch.object(core, "run") as run,
        pytest.raises(ValueError, match="环境变量 PR_PREVIEW_BASE_URL"),
    ):
        core.prepare_preview_repository(preview_environment)
    run.assert_not_called()


def test_cli_url_error_identifies_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPG_KEY_ID", "key")
    monkeypatch.setenv("FLATPAK_REPO_URL", "https://example.invalid/repo")
    with patch.object(core, "run_bytes") as export:
        result = CliRunner().invoke(cli, ["generate-flatpakrepo"])
    assert result.exit_code == 1
    assert "环境变量 FLATPAK_REPO_URL 无效" in result.output
    assert "地址必须以 / 结尾" in result.output
    export.assert_not_called()


def test_generated_url_validation_precedes_signing(preview_environment: Path) -> None:
    actual_validate = core.validate_https_url

    def validate(url: str, *, source: str, root_only: bool = False) -> None:
        if source.startswith("内部生成"):
            raise ValueError(f"{source} 无效：模拟内部生成错误。")
        actual_validate(url, source=source, root_only=root_only)

    with (
        patch.object(core, "validate_https_url", side_effect=validate),
        patch.object(core, "run") as run,
        pytest.raises(ValueError, match="内部生成.*prepare-preview-repo"),
    ):
        core.prepare_preview_repository(preview_environment)
    run.assert_not_called()


def test_public_probe_accepts_repository_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLATPAK_REPO_URL", "https://example.invalid/repo/")
    with patch.object(core, "run") as run:
        core.probe_public_repository()
    downloads = [call.args[0][-1] for call in run.call_args_list[:2]]
    assert downloads == [
        "https://example.invalid/repo/repo.flatpakrepo",
        "https://example.invalid/repo/summary",
    ]
