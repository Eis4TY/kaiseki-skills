#!/usr/bin/env python3
"""Build and round-trip validate a v3 import ZIP. No uploads or network calls."""
import argparse
import hashlib
import io
from pathlib import Path
import zipfile
from contract import (InputError, check_menu, check_research, check_tracks, extract_playlist, extract_script,
                      json_bytes, load_research, loads, preview_cloud_compile, read_json, report, bind_research)

MAX_BYTES = 500 * 1024  # 上传包体积上限 500KB
MAX_DECOMPRESSED_BYTES = 30 * 1024 * 1024  # 解压总量上限（zip 炸弹防护；JSON 压缩比高，与上传上限解耦）
PROFILES = {"kaiseki-v3": ("netease",), "portable-v3": ("netease", "youtube")}

# 压缩工具混入的系统条目（Finder 的 __MACOSX/资源叉、Windows 缩略图缓存等），一律忽略
ZIP_JUNK_FILES = {".DS_Store", "Thumbs.db"}


def normalize_zip_names(names: list[str]) -> dict[str, str]:
    """清洗 ZIP 条目名：丢弃系统垃圾条目与目录占位，剥掉单一根文件夹。

    Finder「右键压缩文件夹」会产出 `文件夹/menu.json` 并混入 `__MACOSX/`、
    `.DS_Store`、`._xxx` 等条目——清洗后统一回到根目录平铺。
    返回 清洗名 -> 原始名 的映射；全部条目嵌在同一层目录下时剥掉该目录。
    """
    mapping: dict[str, str] = {}
    for orig in names:
        parts = [p for p in orig.split("/") if p]
        if not parts or orig.endswith("/"):
            continue  # 目录占位条目，无内容
        if parts[0] == "__MACOSX" or parts[-1].startswith("._") or parts[-1] in ZIP_JUNK_FILES:
            continue
        mapping["/".join(parts)] = orig
    roots = {n.split("/")[0] for n in mapping}
    if len(roots) == 1 and all("/" in n for n in mapping):
        mapping = {n.split("/", 1)[1]: orig for n, orig in mapping.items()}
    return mapping


def matches_playlist(actual, expected):
    """比较 playlist.json 是否与 menu.json 导出的逻辑歌单一致。

    向后兼容：早期打包工具未向 playlist.json 的 tracks 写入 sourceUrls / platformLinks。
    只要核心字段（id/provider/providerTrackId/title/artist/durationSeconds/recordingId）及顺序严格一致即放行。
    """
    if actual == expected:
        return True
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    if {k: v for k, v in actual.items() if k != "tracks"} != {k: v for k, v in expected.items() if k != "tracks"}:
        return False
    actual_tracks = actual.get("tracks")
    expected_tracks = expected.get("tracks")
    if not isinstance(actual_tracks, list) or not isinstance(expected_tracks, list) or len(actual_tracks) != len(expected_tracks):
        return False
    core_keys = {"id", "provider", "providerTrackId", "title", "artist", "durationSeconds", "recordingId"}
    for a, e in zip(actual_tracks, expected_tracks):
        if not isinstance(a, dict) or not isinstance(e, dict):
            return False
        if {k: a.get(k) for k in core_keys} != {k: e.get(k) for k in core_keys}:
            return False
        for opt_key in ("sourceUrls", "platformLinks"):
            if opt_key in a and a[opt_key] != e.get(opt_key):
                return False
    return True


def validate_bundle(data):
    """Re-read the actual ZIP and compare every derived payload with its source."""
    if len(data) > MAX_BYTES:
        raise InputError("ZIP 超过导入限制 500KB")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # 系统垃圾条目（__MACOSX/.DS_Store 等）与根文件夹包装在清洗时剥掉；契约外的多余文件忽略
        orig_of = normalize_zip_names(zf.namelist())
        names = list(orig_of)
        required = {"menu.json", "script.json", "playlist.json", "bundle.json"}
        if len(set(names)) != len(names) or not required <= set(names):
            raise InputError("ZIP 文件重复或缺少必需 JSON")
        if sum(x.file_size for x in zf.infolist()) > MAX_DECOMPRESSED_BYTES:
            raise InputError("ZIP 解压内容超过 30MB")
        docs = {name: loads(zf.read(orig_of[name])) for name in required}
        doc, manifest = docs["menu.json"], docs["bundle.json"]
        if not isinstance(manifest, dict):
            raise InputError("bundle.json 顶层必须为对象")
        errors = check_menu(doc)
        if errors:
            raise InputError("\n".join(errors))
        profile = manifest.get("targetProfile")
        if profile not in PROFILES or manifest.get("rulesVersion") != "sound-rules-v3" or manifest.get("format") != "kaiseki.menu-bundle/3":
            raise InputError("bundle.json 格式/目标能力版本不匹配")
        if docs["script.json"] != extract_script(doc):
            raise InputError("script.json 与 menu.json 内嵌口播不一致")
        if not matches_playlist(docs["playlist.json"], extract_playlist(doc, PROFILES[profile])):
            raise InputError("playlist.json 与音乐池身份、顺序、时长不一致")
        track_errors = check_tracks(extract_playlist(doc, PROFILES[profile])["tracks"])
        if track_errors:
            raise InputError("\n".join(track_errors))
        # 校验和只覆盖契约内文件（必需 JSON 与封面）；多余文件已忽略，不参与比对
        contract_files = [n for n in names
                          if n == "menu.json" or n == "script.json" or n == "playlist.json"
                          or n in ("cover.png", "cover.jpg", "cover.webp")]
        expected = {name: hashlib.sha256(zf.read(orig_of[name])).hexdigest() for name in contract_files}
        if manifest.get("sha256") != expected:
            raise InputError("ZIP 内容校验和不一致")
    return docs


def build_bundle(doc, profile="kaiseki-v3", cover=None):
    errors = check_menu(doc)
    if errors:
        raise InputError("\n".join(errors))
    errors = check_tracks(extract_playlist(doc, PROFILES[profile])["tracks"])
    if errors:
        raise InputError("\n".join(errors))
    payload = {"menu.json": json_bytes(doc), "script.json": json_bytes(extract_script(doc)),
               "playlist.json": json_bytes(extract_playlist(doc, PROFILES[profile]))}
    if cover:
        path = Path(cover)
        data = path.read_bytes()
        if path.suffix.lower() == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
            name = "cover.png"
        elif path.suffix.lower() in (".jpg", ".jpeg") and data.startswith(b"\xff\xd8\xff"):
            name = "cover.jpg"
        elif path.suffix.lower() == ".webp" and len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            name = "cover.webp"
        else:
            raise InputError("--cover 须为内容与扩展名匹配的 WebP/PNG/JPEG 图片")
        payload[name] = data
    payload["bundle.json"] = json_bytes({"format": "kaiseki.menu-bundle/3", "rulesVersion": "sound-rules-v3",
                                         "targetProfile": profile,
                                         "sha256": {k: hashlib.sha256(v).hexdigest() for k, v in payload.items()}})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in payload.items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    data = buf.getvalue()
    validate_bundle(data)
    return data


def print_preview(doc):
    """云端编译预演警告（保守语速估长，非门禁）与压歌/重传注意事项。"""
    warnings = preview_cloud_compile(doc)
    if warnings:
        print("云端编译预演警告（按保守语速预估 TTS 时长，实测以云端为准）：")
        for w in warnings:
            print(f"- {w}")
    if any(i.get("endConstraint") for b in doc["timeline"] for i in b["items"]):
        print("提示：含压歌约束的菜单需归档（archive）模式后端；在线试验模式上传后将被拒绝。")
    print("提示：云端拒绝同 menu_id 同版本号重传；重新上传前把 menu_id 升到新的 -vN。")


def main():
    ap = argparse.ArgumentParser(description="检查、打包并复验 v3 菜单；不上传、不发布")
    ap.add_argument("menu", nargs="?")
    ap.add_argument("--research", help="正式打包必填：六文件调研包目录")
    ap.add_argument("-o", "--output")
    ap.add_argument("--cover")
    ap.add_argument("--profile", choices=PROFILES, default="kaiseki-v3")
    ap.add_argument("--verify", metavar="ZIP", help="独立复验已有 ZIP；无需调研目录")
    args = ap.parse_args()
    try:
        if args.verify:
            docs = validate_bundle(Path(args.verify).read_bytes())
            print("ZIP v3 契约、正文、身份对位、校验和全部通过；未验证在线可用性")
            print_preview(docs["menu.json"])
            return 0
        if not args.menu or not args.research:
            ap.error("正式打包需要 menu 和 --research；已有 ZIP 使用 --verify")
        doc = read_json(args.menu)
        research = load_research(args.research)
        errors = check_research(research)
        if errors:
            return report(errors, "")
        if bind_research(doc, research) != doc:
            raise InputError("菜单与调研快照不一致，请先运行 finalize_menu.py；打包不会静默修改菜单")
        data = build_bundle(doc, args.profile, args.cover)
        out = Path(args.output) if args.output else Path(args.menu).resolve().parent.parent / (doc["menu_id"] + ".zip")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("xb") as f:
            f.write(data)
        print(f"已生成并复验 v3 菜单包：{out.resolve()}\nSHA256: {hashlib.sha256(data).hexdigest()}")
        print(f"目标能力 {args.profile}：需部署支持 sound-rules-v3 的后端；TTS、音源归档和音频 QA 在导入后执行。")
        print_preview(doc)
        return 0
    except (InputError, OSError, zipfile.BadZipFile) as exc:
        print(f"打包/复验失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
