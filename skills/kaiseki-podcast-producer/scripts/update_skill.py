#!/usr/bin/env python3
"""Check and safely update this skill from its pinned public release feed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlparse
import zipfile

LATEST_URL = "https://raw.githubusercontent.com/Eis4TY/kaiseki-skills/main/latest.json"
RELEASE_BASE = "https://github.com/Eis4TY/kaiseki-skills/releases/download/producer-v"
SKILL_NAME = "kaiseki-podcast-producer"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 30 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
TIMEOUT_SECONDS = 8
TRUSTED_RESPONSE_HOSTS = {
    "raw.githubusercontent.com",
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
}
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


class UpdateError(Exception):
    pass


def version_key(version: str) -> tuple:
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise UpdateError(f"非法语义版本号：{version!r}")
    without_build = version.split("+", 1)[0]
    core, _, prerelease = without_build.partition("-")
    if prerelease and any(not part or (part.isdigit() and len(part) > 1 and part.startswith("0"))
                          for part in prerelease.split(".")):
        raise UpdateError(f"非法 SemVer prerelease：{version!r}")
    if "+" in version and any(not part for part in version.split("+", 1)[1].split(".")):
        raise UpdateError(f"非法 SemVer build metadata：{version!r}")
    major, minor, patch = (int(part) for part in core.split("."))
    prerelease_key = tuple((0, int(part)) if part.isdigit() else (1, part) for part in prerelease.split("."))
    # Stable releases sort above the corresponding prerelease; numeric identifiers sort numerically.
    return major, minor, patch, 1 if not prerelease else 0, prerelease_key


def read_local_version(skill_dir: Path) -> str:
    try:
        version = (skill_dir / "VERSION").read_text(encoding="utf-8").strip()
        entry = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise UpdateError(f"无法读取本地 skill 版本信息：{exc}") from exc
    version_key(version)
    frontmatter = entry.split("---", 2)
    if len(frontmatter) < 3 or not re.search(rf"(?m)^name:\s*['\"]?{re.escape(SKILL_NAME)}['\"]?\s*$", frontmatter[1]):
        raise UpdateError("SKILL.md frontmatter name 不是 Producer skill")
    match = re.search(r"(?ms)^metadata:\s*\n(?:^[ \t]+.*\n)*?^[ \t]+version:\s*['\"]?([^\s'\"]+)['\"]?\s*$", entry)
    if not match or match.group(1) != version:
        raise UpdateError("VERSION 与 SKILL.md metadata.version 不一致")
    return version


def _download(url: str, limit: int, opener) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "kaiseki-podcast-producer-updater/1"})
    with opener(request, timeout=TIMEOUT_SECONDS) as response:
        final_url = response.geturl() if hasattr(response, "geturl") else url
        parsed = urlparse(final_url)
        if parsed.scheme != "https" or parsed.hostname not in TRUSTED_RESPONSE_HOSTS:
            raise UpdateError("下载重定向到了不受信任的地址")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("远端文件超过大小限制")
    return data


def load_manifest(manifest_url: str, opener=urllib.request.urlopen) -> dict:
    if not manifest_url.startswith("https://raw.githubusercontent.com/Eis4TY/kaiseki-skills/"):
        raise UpdateError("版本清单来源不受信任")
    try:
        raw = _download(manifest_url, MAX_MANIFEST_BYTES, opener)
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, urllib.error.URLError, UnicodeError, json.JSONDecodeError) as exc:
        raise UpdateError(f"获取最新版本失败：{exc}") from exc
    if not isinstance(manifest, dict):
        raise UpdateError("latest.json 必须是 JSON 对象")
    version = manifest.get("version")
    version_key(version)
    expected_url = f"{RELEASE_BASE}{version}/{SKILL_NAME}-v{version}.zip"
    if manifest.get("downloadUrl") != expected_url:
        raise UpdateError("下载地址与固定发行仓库/版本不匹配")
    digest = manifest.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise UpdateError("latest.json 缺少有效 SHA-256")
    if not isinstance(manifest.get("publishedAt"), str) or not isinstance(manifest.get("releaseNotes"), (str, list)):
        raise UpdateError("latest.json 缺少 publishedAt 或 releaseNotes")
    return manifest


def _extract_verified_archive(archive: bytes, stage: Path, expected_version: str) -> None:
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise UpdateError("skill 压缩包超过大小限制")
    seen: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(archive)) as zf:
            entries = zf.infolist()
            for info in entries:
                name = info.filename
                if "\\" in name or name.startswith("/") or "\x00" in name:
                    raise UpdateError(f"压缩包含非法路径：{name!r}")
                raw_parts = name[:-1].split("/") if name.endswith("/") else name.split("/")
                if any(part in ("", ".", "..") for part in raw_parts):
                    raise UpdateError(f"压缩包路径含有歧义或越界片段：{name!r}")
                path = PurePosixPath(name)
                if any(part in ("", ".", "..") for part in path.parts) or (path.parts and ":" in path.parts[0]):
                    raise UpdateError(f"压缩包路径越界：{name!r}")
                normalized = path.as_posix().rstrip("/")
                if not normalized:
                    continue
                if normalized in seen:
                    raise UpdateError(f"压缩包包含重复路径：{normalized}")
                seen.add(normalized)
                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if file_type == stat.S_IFLNK or (file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR)):
                    raise UpdateError(f"压缩包包含链接或特殊文件：{name}")
                if info.flag_bits & 0x1:
                    raise UpdateError("不接受加密压缩包")
                total += info.file_size
                if info.file_size > MAX_FILE_BYTES or total > MAX_UNPACKED_BYTES:
                    raise UpdateError("压缩包解压内容超过大小限制")
            required = {
                "SKILL.md", "VERSION", "CHANGELOG.md", "assets/menu.example.json",
                "scripts/update_skill.py", "scripts/contract.py", "scripts/check_menu.py",
                "scripts/finalize_menu.py", "scripts/self_test.py", "scripts/check_research_pack.py",
                "scripts/pack_menu.py", "tests/test_portable.py", "schemas/research.schema.json",
                "schemas/menu-v3.schema.json", "references/portable-contract.md", "references/style.md",
                "references/research.md", "references/menu.md",
            }
            if not required <= seen:
                raise UpdateError("压缩包不是完整的 Producer skill，缺少必需文件")
            for info in entries:
                path = PurePosixPath(info.filename)
                if info.is_dir():
                    (stage / Path(*path.parts)).mkdir(parents=True, exist_ok=True)
                    continue
                dest = stage / Path(*path.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as source, dest.open("xb") as target:
                    shutil.copyfileobj(source, target, length=64 * 1024)
                mode = info.external_attr >> 16
                dest.chmod(0o755 if mode & 0o111 else 0o644)
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise UpdateError(f"skill 压缩包无法安全解压：{exc}") from exc
    if read_local_version(stage) != expected_version:
        raise UpdateError("压缩包内部版本与 latest.json 不一致")


def check_and_update(skill_dir: Path, *, manifest_url: str = LATEST_URL, opener=urllib.request.urlopen) -> str:
    skill_dir = skill_dir.resolve()
    current = read_local_version(skill_dir)
    manifest = load_manifest(manifest_url, opener)
    latest = manifest["version"]
    if version_key(latest) <= version_key(current):
        return f"已是最新版本 {current}"
    try:
        archive = _download(manifest["downloadUrl"], MAX_ARCHIVE_BYTES, opener)
    except (OSError, urllib.error.URLError, UpdateError) as exc:
        raise UpdateError(f"下载更新失败，保留当前版本 {current}：{exc}") from exc
    actual = hashlib.sha256(archive).hexdigest()
    if actual != manifest["sha256"]:
        raise UpdateError(f"SHA-256 不匹配，保留当前版本 {current}")

    parent = skill_dir.parent
    backup = parent / f".{SKILL_NAME}.backup-{os.getpid()}"
    stage: Path | None = None
    moved_old = False
    try:
        stage = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}.stage-", dir=parent))
        _extract_verified_archive(archive, stage, latest)
        if backup.exists():
            raise UpdateError("发现未清理的更新备份；为保护现有文件，停止更新")
        skill_dir.rename(backup)
        moved_old = True
        try:
            stage.rename(skill_dir)
        except OSError:
            backup.rename(skill_dir)
            moved_old = False
            raise
        try:
            shutil.rmtree(backup)
        except OSError:
            return f"已从 {current} 更新到 {latest}；旧版备份保留在 {backup}"
        return f"已从 {current} 更新到 {latest}"
    except (OSError, UpdateError) as exc:
        if moved_old and backup.exists() and not skill_dir.exists():
            try:
                backup.rename(skill_dir)
            except OSError as rollback_exc:
                raise UpdateError(f"更新失败且自动回滚失败，请保留备份 {backup}：{rollback_exc}") from exc
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError(f"更新失败，保留当前版本 {current}：{exc}") from exc
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="检查并安全更新怀石电台 Producer skill")
    ap.add_argument("--skill-dir", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    try:
        print(check_and_update(args.skill_dir))
    except UpdateError as exc:
        print(f"更新状态：{exc}。继续使用已安装版本。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
