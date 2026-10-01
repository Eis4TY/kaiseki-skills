#!/usr/bin/env python3
"""Create deterministic Producer skill release assets without publishing them."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import zipfile

SKILL_NAME = "kaiseki-podcast-producer"
REPO = "Eis4TY/kaiseki-skills"
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
EXCLUDED_PARTS = {"__pycache__", ".git"}


def metadata_version(entry: str) -> str:
    match = re.search(r"(?ms)^metadata:\s*\n(?:^[ \t]+.*\n)*?^[ \t]+version:\s*['\"]?([^\s'\"]+)['\"]?\s*$", entry)
    if not match:
        raise ValueError("SKILL.md 缺少 metadata.version")
    return match.group(1)


def validate_version(version: str) -> None:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"VERSION 不是有效 SemVer：{version}")
    without_build = version.split("+", 1)[0]
    _, separator, prerelease = without_build.partition("-")
    if separator and any(not part or (part.isdigit() and len(part) > 1 and part.startswith("0"))
                         for part in prerelease.split(".")):
        raise ValueError(f"VERSION 的 prerelease 不符合 SemVer：{version}")
    if "+" in version and any(not part for part in version.split("+", 1)[1].split(".")):
        raise ValueError(f"VERSION 的 build metadata 不符合 SemVer：{version}")


def release_notes(changelog: str, version: str) -> list[str]:
    match = re.search(rf"(?ms)^##\s+{re.escape(version)}\s*\n(.*?)(?=^##\s+|\Z)", changelog)
    if not match:
        raise ValueError(f"CHANGELOG.md 缺少 {version} 条目")
    notes = [line.strip()[2:].strip() for line in match.group(1).splitlines() if line.strip().startswith("- ")]
    if not notes:
        raise ValueError(f"CHANGELOG.md 的 {version} 条目没有变更说明")
    return notes


def deterministic_zip(skill_dir: Path, version: str) -> bytes:
    files = []
    for path in skill_dir.rglob("*"):
        if any(part in EXCLUDED_PARTS for part in path.parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"不允许 skill 包含符号链接：{path}")
        if path.is_file():
            files.append(path)
    files.sort(key=lambda path: path.relative_to(skill_dir).as_posix())
    if not files:
        raise ValueError("skill 目录为空")
    from io import BytesIO
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(skill_dir).as_posix()
            data = path.read_bytes()
            mode = stat.S_IFREG | (0o755 if path.stat().st_mode & 0o111 else 0o644)
            info = zipfile.ZipInfo(relative, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description="构建怀石电台 Producer skill 的版本 ZIP 与 latest.json，不执行发布")
    default_public = Path(__file__).resolve().parents[1] / "skills" / SKILL_NAME
    default_business = Path(__file__).resolve().parents[1] / ".agents" / "skills" / SKILL_NAME
    default_skill = default_public if default_public.is_dir() else default_business
    parser.add_argument("--skill-dir", type=Path, default=default_skill)
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument("--published-at", help="ISO-8601 时间；用于复现 latest.json")
    args = parser.parse_args()
    skill_dir = args.skill_dir.resolve()
    try:
        if skill_dir.name != SKILL_NAME or not (skill_dir / "SKILL.md").is_file():
            raise ValueError(f"不是 {SKILL_NAME} skill 目录：{skill_dir}")
        version = (skill_dir / "VERSION").read_text(encoding="utf-8").strip()
        validate_version(version)
        entry = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        if not re.search(rf"(?m)^name:\s*['\"]?{re.escape(SKILL_NAME)}['\"]?\s*$", entry.split("---", 2)[1] if len(entry.split("---", 2)) > 1 else ""):
            raise ValueError("SKILL.md frontmatter name 不是 Producer skill")
        if metadata_version(entry) != version:
            raise ValueError("VERSION 与 SKILL.md metadata.version 不一致")
        notes = release_notes((skill_dir / "CHANGELOG.md").read_text(encoding="utf-8"), version)
        zip_data = deterministic_zip(skill_dir, version)
        if args.published_at:
            timestamp = datetime.fromisoformat(args.published_at.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("--published-at 必须带时区")
            published_at = timestamp.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        else:
            published_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        filename = f"{SKILL_NAME}-v{version}.zip"
        digest = hashlib.sha256(zip_data).hexdigest()
        manifest = {
            "version": version,
            "downloadUrl": f"https://github.com/{REPO}/releases/download/producer-v{version}/{filename}",
            "sha256": digest,
            "publishedAt": published_at,
            "releaseNotes": notes,
        }
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        (output / filename).write_bytes(zip_data)
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        (output / "latest.json").write_bytes(manifest_bytes)
        (output / "SHA256SUMS").write_text(f"{digest}  {filename}\n", encoding="ascii")
        print(f"已构建版本 {version}：{output / filename}")
        print(f"SHA-256: {digest}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
