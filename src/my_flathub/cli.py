"""`my-flathub` 命令行入口。"""

from __future__ import annotations

import json
from pathlib import Path

import click

from . import core, preview


def call(function: object, *args: object) -> None:
    try:
        if not callable(function):
            raise TypeError("内部命令未定义")
        function(*args)
    except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise click.ClickException(str(error)) from error


@click.group()
def cli() -> None:
    """构建、验证和发布 My Flathub 仓库。"""


@cli.command("discover-manifests")
@click.option("--json", "as_json", is_flag=True, help="输出 JSON 数组。")
def discover_manifests_command(as_json: bool) -> None:
    """发现 packages/ 下的 manifest。"""
    manifests = core.discover_manifests(Path("packages"))
    values = [path.as_posix() for path in manifests]
    click.echo(json.dumps(values, ensure_ascii=False) if as_json else "\n".join(values))


@cli.command("validate-manifests")
def validate_manifests_command() -> None:
    """验证 manifest、MetaInfo 和 Flatpak lint 规则。"""
    call(core.validate_manifests, core.root_path())


@cli.command("build-repo")
def build_repo_command() -> None:
    """构建全部软件包到 OSTree 仓库。"""
    call(core.build_repository, core.root_path())


@cli.command("verify-repo")
def verify_repo_command() -> None:
    """验证 OSTree 仓库并运行示例应用。"""
    call(core.verify_repository, core.root_path())


@cli.command("finalize-repo")
def finalize_repo_command() -> None:
    """生成正式仓库元数据和 static deltas。"""
    call(core.finalize_repository)


@cli.command("generate-flatpakrepo")
def generate_flatpakrepo_command() -> None:
    """生成 repo.flatpakrepo。"""
    call(core.generate_flatpakrepo)


@cli.command("prepare-preview-repo")
def prepare_preview_repo_command() -> None:
    """签署 PR 测试仓库并生成发布元数据。"""
    call(core.prepare_preview_repository, core.root_path())


@cli.group("r2")
def r2_group() -> None:
    """从 R2 恢复或向 R2 发布仓库。"""


@r2_group.command("pull")
def r2_pull_command() -> None:
    call(core.r2_repository, "pull")


@r2_group.command("push")
def r2_push_command() -> None:
    call(core.r2_repository, "push")


@cli.command("probe-public-repo")
def probe_public_repo_command() -> None:
    """验证公开仓库可下载和列出。"""
    call(core.probe_public_repository)


@cli.group("preview")
def preview_group() -> None:
    """发布或清理 PR 测试仓库。"""


@preview_group.command("publish")
def preview_publish_command() -> None:
    call(preview.run_cli, "publish")


@preview_group.command("cleanup")
@click.option("--pr", "number", type=click.IntRange(min=1))
def preview_cleanup_command(number: int | None) -> None:
    call(preview.run_cli, "cleanup", number)
