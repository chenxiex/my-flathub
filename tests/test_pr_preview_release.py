"""验证来自无特权 PR 工作流的仓库产物不能越界发布。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from my_flathub import preview as MODULE


class ValidateRepoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        for filename in ("config", "summary", "summary.sig"):
            (self.repo / filename).write_text("test", encoding="utf-8")
        (self.repo / "repo.flatpakrepo").write_text(
            "[Flatpak Repo]\nUrl=https://preview.example/pr/1/2-1/\nGPGKey=abc\n",
            encoding="utf-8",
        )

    def test_accepts_expected_repo(self):
        files = MODULE.validate_repo(self.repo, "https://preview.example/pr/1/2-1/")
        self.assertEqual(len(files), 4)

    def test_rejects_other_repo_url(self):
        with self.assertRaisesRegex(ValueError, "URL"):
            MODULE.validate_repo(self.repo, "https://preview.example/pr/9/2-1/")

    def test_rejects_symlink(self):
        (self.repo / "outside").symlink_to(Path(self.temp.name) / "outside")
        with self.assertRaisesRegex(ValueError, "文件类型"):
            MODULE.validate_repo(self.repo, "https://preview.example/pr/1/2-1/")


class ReleaseOrderTests(unittest.TestCase):
    def test_old_run_cannot_replace_newer_preview(self):
        entries = [
            {"tag_name": "pr-preview-12-345-1", "draft": False},
            {"tag_name": "pr-preview-12-346-1", "draft": False},
            {"tag_name": "pr-preview-13-900-1", "draft": False},
        ]
        with patch.object(MODULE, "releases", return_value=iter(entries)):
            self.assertTrue(MODULE.newer_release_exists("owner/repo", 12, 345, 2))


if __name__ == "__main__":
    unittest.main()
