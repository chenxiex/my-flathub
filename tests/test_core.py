"""仓库维护命令的纯逻辑和命令编排测试。"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from my_flathub import core
from my_flathub.cli import cli


def test_discover_manifests_only_returns_package_manifests(tmp_path: Path) -> None:
    package = tmp_path / "packages" / "org.example.App"
    package.mkdir(parents=True)
    manifest = package / "org.example.App.yaml"
    manifest.write_text("app-id: org.example.App", encoding="utf-8")
    (package / "notes.yml").write_text("ignored", encoding="utf-8")

    assert core.discover_manifests(tmp_path / "packages") == [manifest]


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        (
            {
                "app-id": "org.example.App",
                "runtime": "x",
                "runtime-version": "1",
                "sdk": "x",
                "command": "app",
                "modules": [{"sources": [{"type": "archive", "url": "https://example.invalid/a"}]}],
            },
            "SHA256",
        ),
        (
            {
                "app-id": "org.example.App",
                "runtime": "x",
                "runtime-version": "1",
                "sdk": "x",
                "command": "app",
                "modules": [{"sources": [{"type": "git", "branch": "main", "commit": "a" * 40}]}],
            },
            "Git",
        ),
    ],
)
def test_validate_manifest_data_rejects_unpinned_sources(
    manifest: dict[str, object], message: str, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match=message):
        core.validate_manifest_data(manifest, tmp_path / "manifest.yaml", "org.example.App")


def test_validate_manifest_data_accepts_pinned_sources(tmp_path: Path) -> None:
    manifest: dict[str, object] = {
        "app-id": "org.example.App",
        "runtime": "x",
        "runtime-version": "1",
        "sdk": "x",
        "command": "app",
        "modules": [
            {
                "sources": [
                    {"type": "archive", "url": "https://example.invalid/a", "sha256": "a" * 64},
                    {"type": "git", "commit": "b" * 40},
                ]
            }
        ],
    }

    assert (
        core.validate_manifest_data(manifest, tmp_path / "manifest.yaml", "org.example.App")
        == "org.example.App"
    )


def test_cli_discovers_json_manifests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "packages" / "org.example.App"
    package.mkdir(parents=True)
    (package / "org.example.App.yaml").write_text("app-id: org.example.App", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["discover-manifests", "--json"])

    assert result.exit_code == 0
    assert result.output == '["packages/org.example.App/org.example.App.yaml"]\n'


def test_flatpak_tools_prefers_native_commands(tmp_path: Path) -> None:
    with patch.object(core.shutil, "which", side_effect=lambda name: f"/{name}"):
        tools = core.FlatpakTools.create(tmp_path)

    assert tools.native_builder is True
    assert tools.builder == ("flatpak-builder",)
    assert tools.linter == ("flatpak-builder-lint",)


def test_generate_flatpakrepo_preserves_binary_public_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    monkeypatch.setenv("REPO_DIR", str(repo))
    monkeypatch.setenv("GPG_KEY_ID", "key")
    monkeypatch.setenv("FLATPAK_REPO_URL", "https://example.invalid/")

    with patch.object(
        core,
        "run_bytes",
        return_value=subprocess.CompletedProcess([], 0, b"\xff", b""),
    ):
        core.generate_flatpakrepo()

    assert "GPGKey=/w==" in (repo / "repo.flatpakrepo").read_text(encoding="utf-8")


def test_r2_push_updates_summary_after_other_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for filename in ("config", "summary", "summary.sig"):
        (repo / filename).write_text("test", encoding="utf-8")
    monkeypatch.setenv("REPO_DIR", str(repo))
    monkeypatch.setenv("R2_ACCOUNT_ID", "account")
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "access")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    commands: list[list[str]] = []

    def record(args: Sequence[str | Path], **_: object) -> subprocess.CompletedProcess[str]:
        command = [str(value) for value in args]
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    with patch.object(core, "run", side_effect=record):
        core.r2_repository("push")

    copyto = [command[2] for command in commands if command[1] == "copyto"]
    assert copyto == [str(repo / "summary.sig"), str(repo / "summary")]
    assert commands[-2][1] == "sync"
    assert commands[-1][1] == "check"
