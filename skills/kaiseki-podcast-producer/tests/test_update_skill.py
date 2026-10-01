"""Offline tests for version ordering, release verification, and safe replacement."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import update_skill


class Response(io.BytesIO):
    def __init__(self, data: bytes, url: str):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url


def make_skill(directory: Path, version: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / "kaiseki-podcast-producer"
    shutil.copytree(SKILL, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (dest / "VERSION").write_text(version + "\n", encoding="utf-8")
    entry = (dest / "SKILL.md").read_text(encoding="utf-8")
    import re
    entry = re.sub(r"(?m)^(\s+version:)\s*[^\s]+$", rf"\g<1> {version}", entry, count=1)
    (dest / "SKILL.md").write_text(entry, encoding="utf-8")
    (dest / "CHANGELOG.md").write_text(f"# 更新记录\n\n## {version}\n\n- 离线测试发行版。\n", encoding="utf-8")
    return dest


def package_skill(skill_dir: Path) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                archive.writestr(path.relative_to(skill_dir).as_posix(), path.read_bytes())
    return output.getvalue()


def release_manifest(version: str, archive: bytes, *, digest: str | None = None) -> dict:
    return {
        "version": version,
        "downloadUrl": f"{update_skill.RELEASE_BASE}{version}/{update_skill.SKILL_NAME}-v{version}.zip",
        "sha256": digest or hashlib.sha256(archive).hexdigest(),
        "publishedAt": "2026-10-01T00:00:00Z",
        "releaseNotes": ["离线测试发行版。"],
    }


class OfflineOpener:
    def __init__(self, manifest: dict, archive: bytes, redirect: str | None = None):
        self.manifest = json.dumps(manifest).encode("utf-8")
        self.archive = archive
        self.redirect = redirect

    def __call__(self, request, timeout):
        url = request.full_url
        if url == update_skill.LATEST_URL:
            return Response(self.manifest, url)
        if url.startswith(update_skill.RELEASE_BASE):
            return Response(self.archive, self.redirect or url)
        raise AssertionError(f"unexpected URL: {url}")


class UpdateSkillTests(unittest.TestCase):
    def test_semver_orders_numeric_prereleases_and_stable_build(self):
        self.assertLess(update_skill.version_key("1.0.0-rc.2"), update_skill.version_key("1.0.0-rc.10"))
        self.assertLess(update_skill.version_key("1.0.0-rc.10+build.1"), update_skill.version_key("1.0.0"))
        self.assertEqual(update_skill.version_key("1.0.0+build.1"), update_skill.version_key("1.0.0+build.2"))

    def test_sha_mismatch_keeps_installed_version(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            installed = make_skill(base, "1.0.0")
            candidate = make_skill(base / "candidate", "1.0.1")
            archive = package_skill(candidate)
            manifest = release_manifest("1.0.1", archive, digest="0" * 64)
            with self.assertRaisesRegex(update_skill.UpdateError, "SHA-256"):
                update_skill.check_and_update(installed, opener=OfflineOpener(manifest, archive))
            self.assertEqual((installed / "VERSION").read_text().strip(), "1.0.0")

    def test_zip_slip_is_rejected_before_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            installed = make_skill(base, "1.0.0")
            candidate = make_skill(base / "candidate", "1.0.1")
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for path in sorted(candidate.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(candidate).as_posix())
                archive.writestr("../escaped.txt", "bad")
            payload = output.getvalue()
            manifest = release_manifest("1.0.1", payload)
            with self.assertRaisesRegex(update_skill.UpdateError, "路径.*越界"):
                update_skill.check_and_update(installed, opener=OfflineOpener(manifest, payload))
            self.assertEqual((installed / "VERSION").read_text().strip(), "1.0.0")
            self.assertFalse((base / "escaped.txt").exists())

    def test_valid_release_updates_complete_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            installed = make_skill(base, "1.0.0")
            candidate = make_skill(base / "candidate", "1.0.1")
            archive = package_skill(candidate)
            manifest = release_manifest("1.0.1", archive)
            result = update_skill.check_and_update(installed, opener=OfflineOpener(manifest, archive))
            self.assertIn("已从 1.0.0 更新到 1.0.1", result)
            self.assertEqual((installed / "VERSION").read_text().strip(), "1.0.1")
            self.assertTrue((installed / "references/research.md").is_file())
            self.assertTrue((installed / "scripts/pack_menu.py").is_file())

    def test_untrusted_redirect_keeps_installed_version(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            installed = make_skill(base, "1.0.0")
            candidate = make_skill(base / "candidate", "1.0.1")
            archive = package_skill(candidate)
            manifest = release_manifest("1.0.1", archive)
            opener = OfflineOpener(manifest, archive, "https://attacker.invalid/skill.zip")
            with self.assertRaisesRegex(update_skill.UpdateError, "重定向"):
                update_skill.check_and_update(installed, opener=opener)
            self.assertEqual((installed / "VERSION").read_text().strip(), "1.0.0")

    def test_offline_and_staging_permission_failure_preserve_installed_version(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            installed = make_skill(base, "1.0.0")
            offline = lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline"))
            with self.assertRaisesRegex(update_skill.UpdateError, "获取最新版本失败"):
                update_skill.check_and_update(installed, opener=offline)
            candidate = make_skill(base / "candidate", "1.0.1")
            archive = package_skill(candidate)
            manifest = release_manifest("1.0.1", archive)
            with patch.object(update_skill.tempfile, "mkdtemp", side_effect=PermissionError("read-only")):
                with self.assertRaisesRegex(update_skill.UpdateError, "更新失败"):
                    update_skill.check_and_update(installed, opener=OfflineOpener(manifest, archive))
            self.assertEqual((installed / "VERSION").read_text().strip(), "1.0.0")

    def test_failed_directory_swap_rolls_back_previous_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            installed = make_skill(base, "1.0.0")
            candidate = make_skill(base / "candidate", "1.0.1")
            archive = package_skill(candidate)
            manifest = release_manifest("1.0.1", archive)
            original_rename = Path.rename

            def reject_staged_install(path, target):
                if ".stage-" in path.name:
                    raise PermissionError("simulated replacement failure")
                return original_rename(path, target)

            with patch.object(Path, "rename", new=reject_staged_install):
                with self.assertRaisesRegex(update_skill.UpdateError, "更新失败"):
                    update_skill.check_and_update(installed, opener=OfflineOpener(manifest, archive))
            self.assertEqual((installed / "VERSION").read_text().strip(), "1.0.0")
            self.assertTrue((installed / "scripts/pack_menu.py").is_file())

    def test_current_version_does_not_download_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            installed = make_skill(Path(temp), "1.0.0")

            class ManifestOnly:
                def __call__(self, request, timeout):
                    if request.full_url != update_skill.LATEST_URL:
                        raise AssertionError("up-to-date check must not fetch a ZIP")
                    return Response(json.dumps(release_manifest("1.0.0", b"")).encode(), request.full_url)

            self.assertEqual(update_skill.check_and_update(installed, opener=ManifestOnly()), "已是最新版本 1.0.0")

    def test_semver_build_metadata_is_not_prerelease_and_invalid_identifiers_rejected(self):
        self.assertEqual(update_skill.version_key("1.0.0+build-with-hyphen")[3], 1)
        for version in ("1.0.0-rc..1", "1.0.0-rc.01"):
            with self.subTest(version=version), self.assertRaises(update_skill.UpdateError):
                update_skill.version_key(version)


if __name__ == "__main__":
    unittest.main()
