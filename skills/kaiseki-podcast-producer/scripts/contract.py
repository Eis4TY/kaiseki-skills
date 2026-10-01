"""Portable sound-rules-v3 contract. Python 3.10+, standard library only.

No repository imports, network calls, environment changes or dependency bootstrap.
Schema validation supports exactly the keywords used by our bundled schemas;
this is deliberately not a general JSON Schema implementation.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
if not SCHEMA_DIR.is_dir():
    SCHEMA_DIR = SKILL_DIR / "schemas"
PLATFORMS = ("apple", "netease", "qq", "youtube", "spotify")
CONFIDENCE = ("双源确认", "单源可信", "孤证存疑", "传闻")
TAG_DIMENSIONS = ("genre", "theme", "mood", "scene")  # 标签四维分面（菜单可不带标签）


class InputError(ValueError):
    pass


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"JSON 重复键: {key}")
        result[key] = value
    return result


def loads(text):
    def reject(value):
        raise InputError(f"JSON 不允许非有限数值: {value}")
    try:
        return json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=reject)
    except (ValueError, UnicodeError) as exc:
        raise InputError(str(exc)) from exc


def read_json(path):
    return loads(Path(path).read_text(encoding="utf-8-sig"))


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def schema_errors(value, name):
    root = read_json(SCHEMA_DIR / name)
    errors = []

    def visit(v, s, p):
        if "$ref" in s:
            ref = s["$ref"]
            if not ref.startswith("#/$defs/"):
                raise InputError(f"不支持的 schema 引用: {ref}")
            visit(v, root["$defs"][ref.split("/")[-1]], p)
            return
        if "const" in s and v != s["const"]:
            errors.append(f"{p}: 必须为 {s['const']}")
        if "enum" in s and v not in s["enum"]:
            errors.append(f"{p}: 必须取 {s['enum']}")
        types = s.get("type", [])
        types = [types] if isinstance(types, str) else types
        def matches(t):
            return {"object": isinstance(v, dict), "array": isinstance(v, list),
                    "string": isinstance(v, str), "boolean": isinstance(v, bool),
                    "null": v is None, "number": type(v) in (int, float) and math.isfinite(v),
                    "integer": type(v) is int}.get(t, False)
        if types and not any(matches(t) for t in types):
            errors.append(f"{p}: 类型须为 {types}")
            return
        if isinstance(v, dict):
            for k in s.get("required", []):
                if k not in v:
                    errors.append(f"{p}/{k}: 缺少必填字段")
            for k, val in v.items():
                if k in s.get("properties", {}):
                    visit(val, s["properties"][k], f"{p}/{k}")
                # 未在 schema 声明的多余字段：不解析、不影响使用，忽略而非校验失败。
        if isinstance(v, list):
            for key, op in [("minItems", lambda x: len(v) < x), ("maxItems", lambda x: len(v) > x)]:
                if key in s and op(s[key]):
                    errors.append(f"{p}: 数量 {len(v)} 不满足 {key}={s[key]}")
            if s.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in v}) != len(v):
                errors.append(f"{p}: 不允许重复项")
            for i, item in enumerate(v):
                visit(item, s.get("items", {}), f"{p}/{i}")
        if isinstance(v, str):
            if "minLength" in s and len(v.strip()) < s["minLength"]:
                errors.append(f"{p}: 文本为空或过短")
            if "maxLength" in s and len(v) > s["maxLength"]:
                errors.append(f"{p}: 超过 {s['maxLength']} 字")
            if "pattern" in s and not re.search(s["pattern"], v):
                errors.append(f"{p}: 格式不匹配 {s['pattern']}")
        if type(v) in (float, int):
            for key, op in [("minimum", lambda x: v < x), ("maximum", lambda x: v > x)]:
                if key in s and op(s[key]):
                    errors.append(f"{p}: 不满足 {key}={s[key]}")
    visit(value, root, name)
    return errors


def is_url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value) or "..." in value:
        return False
    try:
        u = urlsplit(value)
        return u.scheme in ("https", "http") and bool(u.hostname) and not u.username and not u.password
    except ValueError:
        return False


def platform_of(url):
    if not is_url(url):
        return None
    host = urlsplit(url).hostname.lower()
    for key, domains in {"netease": ("music.163.com",), "qq": ("y.qq.com",),
                         "apple": ("music.apple.com",), "youtube": ("youtube.com", "youtu.be"),
                         "spotify": ("spotify.com",)}.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return key
    return None


def source_group(url):
    """Conservative grouping, NOT proof of editorial independence or a full PSL."""
    host = urlsplit(url).hostname.lower()
    bits = host.split(".")
    second_level = {"co.uk", "com.cn", "com.tw", "com.hk", "co.jp", "com.au", "co.nz", "com.br"}
    count = 3 if ".".join(bits[-2:]) in second_level else 2
    return ".".join(bits[-count:])


def check_facts(facts):
    errors = []
    ids = [f["id"] for f in facts]
    if len(set(ids)) != len(ids):
        errors.append("facts: ID 重复")
    for f in facts:
        fid = f["id"]
        urls = f["sourceUrls"]
        if not urls or not all(is_url(u) for u in urls):
            errors.append(f"{fid}: sourceUrls 必须是非空有效 HTTP(S) 地址列表")
        elif f["confidence"] == "双源确认" and len({source_group(u) for u in urls}) < 2:
            errors.append(f"{fid}: 双源确认至少需要两个独立站点；子域名不算独立来源")
        if f["type"] == "数据" and not re.search(r"(?:19|20)\d{2}|[一二三四五六七八九〇零]{4}年", f["text"]):
            errors.append(f"{fid}: 数据陈述必须带统计年份/时点")
        if f.get("conflicted") and f["confidence"] == "双源确认":
            errors.append(f"{fid}: 冲突事实必须降低置信度")
    return errors


def check_song(song):
    errors = []
    sid = song["songId"]
    # 音频与平台链接允许为空或未获取到，前端对应置灰即可；纯音乐等无词曲目合法
    if song.get("lyrics", "").strip() and not is_url(song.get("lyricsSource", {}).get("url")):
        errors.append(f"{sid}: 缺少歌词出处 lyricsSource.url")
    source = song.get("durationSource", "")
    if not is_url(source) or source_group(source) != "musicbrainz.org":
        errors.append(f"{sid}: durationSource 须指向核实参考时长的 MusicBrainz 版本页面")
    if not song.get("durationSeconds", 0) > 0:
        errors.append(f"{sid}: durationSeconds 须是正数参考时长，不是强制播放时长")
    return errors


def pause_errors(text, label):
    errors = []
    tokens = list(re.finditer(r"<#(.*?)#>", text, re.S))
    remainder = re.sub(r"<#.*?#>", "", text, flags=re.S)
    if "<#" in remainder or "#>" in remainder:
        errors.append(f"{label}: 停顿标记未闭合")
    pieces = re.split(r"<#.*?#>", text, flags=re.S)
    if tokens and any(not any(c.isalnum() for c in p) for p in pieces):
        errors.append(f"{label}: 停顿必须位于可发音文本之间，不能首尾、连续或仅由标点隔开")
    for match in tokens:
        token = match.group(1)
        if not re.fullmatch(r"\d{1,2}(?:\.\d{1,2})?", token) or not 0.01 <= float(token) <= 99.99:
            errors.append(f"{label}: 停顿须为 0.01–99.99 秒（最多两位小数）")
    return errors


def first_vocal_timestamp(lrc):
    """LRC 首句人声时间戳；跳过署名/纯音乐行。与后端 menu_v3.timing 同口径。"""
    values = []
    for line in (lrc or "").splitlines():
        marks = re.findall(r"\[(\d{1,3}):([0-5]\d(?:\.\d{1,3})?)\]", line)
        words = re.sub(r"\[[^\]]*\]", "", line).strip()
        if not marks or not any(c.isalnum() for c in words):
            continue
        if re.search(r"^(?:(?:作词|作曲|编曲|制作人|词|曲|演唱|混音|录音|监制|出品|发行|伴奏)\s*[:：]|(?:lyrics?\s*by|composed\s*by)\b|(?:纯音乐|music|instrumental)\s*$)", words, re.I):
            continue
        values.extend(int(m) * 60 + float(s) for m, s in marks)
    return min(values) if values else None


def vocal_entry_estimate(song):
    """进唱点保守估计（秒）：内嵌 LRC 首句时间戳或显式估计，统一再留 2s 余量。

    与云端 archive_vocal_entries 的菜单回退链同口径：云端优先用归档同版本 LRC，
    本地只能算这条回退链，故作为打包前置门禁（缺证据即拒），不冒充实测。"""
    first = first_vocal_timestamp(song.get("lyrics", ""))
    if first is not None:
        return max(0.0, first - 2.0)
    est = song.get("vocalStartEstimateSeconds")
    if isinstance(est, (int, float)) and est > 0:
        return max(0.0, float(est) - 2.0)
    return None


def check_menu(doc, draft=False):
    errors = schema_errors(doc, "menu-v3.schema.json")
    if errors:
        return errors
    if not draft and doc.get("status") != "final":
        errors.append("status: 正式交付必须为 final；草稿使用 --draft，不能直接打包")
    blocks = doc["timeline"]
    if [b["blockId"] for b in blocks] != [f"B{i}" for i in range(1, len(blocks) + 1)]:
        errors.append("timeline: 必须按 B1..Bn 连续升序，不能依赖排序修复")
    covered = []
    for ch in doc["chapters"]:
        m = re.fullmatch(r"B([1-9]\d*)(?:-B([1-9]\d*))?", ch["blocks"])
        if not m:
            errors.append("chapters: blocks 格式应为 B1 或 B1-B3")
            continue
        start, end = int(m[1]), int(m[2] or m[1])
        if start > end or end > len(blocks):
            errors.append(f"chapters: 范围越界 {ch['blocks']}")
        covered.extend(range(start, end + 1))
    if covered != list(range(1, len(blocks) + 1)):
        errors.append("chapters: 须按序无重叠覆盖全部块")
    pool_ids = [s["songId"] for s in doc["musicPool"]]
    pool_by_id = {s["songId"]: s for s in doc["musicPool"]}
    if len(set(pool_ids)) != len(pool_ids):
        errors.append("musicPool: songId 重复")
    flat = [item for block in blocks for item in block["items"]]
    all_ids = [x["itemId"] for x in flat]
    if len(set(all_ids)) != len(all_ids):
        errors.append("items: itemId 全局重复")
    seen = {}
    voice_count = 0
    for idx, item in enumerate(flat):
        iid, kind = item["itemId"], item["kind"]
        anchor, offset = item["start"]["anchor"], item["start"]["offsetSeconds"]
        if idx == 0 and anchor != "timeline.start":
            errors.append(f"{iid}: 首项须锚定 timeline.start")
        target = None
        if anchor != "timeline.start":
            target_id, _, edge = anchor.rpartition(".")
            target = seen.get(target_id)
            if target is None or edge not in ("start", "end"):
                errors.append(f"{iid}: start.anchor 必须引用此前 item 的 start/end")
        elif idx != 0:
            errors.append(f"{iid}: 仅首项可锚定 timeline.start")
        if offset < 0 and not (kind == "music" and target and target["kind"] == "music"
                               and anchor.endswith(".end") and -3 <= offset < 0):
            errors.append(f"{iid}: 负偏移仅允许 music 对此前 music.end 的 [-3,0) crossfade")
        if kind == "music":
            if item.get("songId") not in pool_ids or item.get("mode") != "full":
                errors.append(f"{iid}: 须引用 musicPool 歌曲并 mode=full")
            if any(k in item for k in ("text", "factRefs", "endConstraint")):
                errors.append(f"{iid}: music 不能携带 voice 字段")
        else:
            voice_count += 1
            if any(k in item for k in ("songId", "mode")):
                errors.append(f"{iid}: voice 不能携带 music 字段")
            if not draft and not item.get("text", "").strip():
                errors.append(f"{iid}: 缺口播正文")
            errors += pause_errors(item.get("text", ""), iid)
            if target and target["kind"] == "music" and anchor.endswith(".start"):
                if item.get("endConstraint", {}).get("before") != target["itemId"] + ".vocalStart":
                    errors.append(f"{iid}: 搭前奏须声明目标歌曲 vocalStart 收声约束")
            constraint = item.get("endConstraint")
            if constraint:
                tid = constraint["before"].removesuffix(".vocalStart")
                ct = seen.get(tid)
                if ct is None and idx + 1 < len(flat) and flat[idx+1]["itemId"] == tid:
                    ct = flat[idx+1]
                if not ct or ct["kind"] != "music":
                    errors.append(f"{iid}: endConstraint 只能指向已出现或紧随其后的 music")
                elif not draft:
                    # 云端编译对缺已核验进唱点的压歌一律拒绝；本地按同一回退链提前拦截
                    song = pool_by_id.get(ct.get("songId"))
                    entry = vocal_entry_estimate(song) if song else None
                    if entry is None:
                        errors.append(f"{iid}: 压歌目标 {tid} 缺少可核验进唱点（云端编译将拒绝）："
                                      "内嵌歌词须为带时间戳 LRC，或提供 vocalStartEstimateSeconds；否则改用干说")
                    elif entry > song.get("durationSeconds", 0):
                        errors.append(f"{iid}: 进唱点估计 {entry:g}s 超出 {ct.get('songId')} 参考时长，先核对歌词与版本")
            # Music beginning during a preceding voice is the other intro shape.
            if idx + 1 < len(flat):
                nxt = flat[idx + 1]
                if nxt["kind"] == "music" and nxt["start"]["anchor"] == iid + ".start":
                    if item.get("endConstraint", {}).get("before") != nxt["itemId"] + ".vocalStart":
                        errors.append(f"{iid}: 人声中进入音乐也须声明收声约束")
        seen[iid] = item
    if not voice_count:
        errors.append("timeline: 至少需要一段口播")
    return errors


def estimated_speech_seconds(text):
    """保守估长（非实测）：中文 TTS 常态约 4–5.5 字/秒，取慢速界，另计停顿标记秒数。"""
    pauses = sum(float(m) for m in re.findall(r"<#(\d{1,2}\.\d{2})#>", text or ""))
    body = re.sub(r"<#.*?#>", "", text or "", flags=re.S)
    return len(re.sub(r"\s", "", body)) / 4.0 + pauses


def preview_cloud_compile(doc):
    """按预估 TTS 时长预演云端 v3 编译判定，返回警告列表（非门禁）。

    复刻 compile_v3 的锚点排布与两级自愈（口播前移、歌曲顺延）及终检：
    负起点、进唱收声线、人声重叠、人声压歌无约束、歌歌重叠非声明。
    歌曲用参考时长、口播用保守估长；实测时长以云端为准，故只警示不拦截。"""
    pool_by_id = {s["songId"]: s for s in doc["musicPool"]}
    flat = [i for b in doc["timeline"] for i in b["items"]]
    durations = {i["itemId"]: round((float(pool_by_id[i["songId"]]["durationSeconds"])
                                     if i["kind"] == "music" else estimated_speech_seconds(i.get("text", ""))) * 1000)
                 for i in flat}
    song_of = {i["itemId"]: i["songId"] for i in flat if i["kind"] == "music"}
    entry_of = {sid: vocal_entry_estimate(song) for sid, song in pool_by_id.items()}

    def place(floors, caps):
        placed = {}
        for item in flat:
            iid = item["itemId"]
            if item["start"]["anchor"] == "timeline.start":
                base = 0
            else:
                aid, edge = item["start"]["anchor"].rsplit(".", 1)
                ref = placed[aid]
                base = ref[0] + (ref[1] if edge == "end" else 0)
            start = base + round(item["start"]["offsetSeconds"] * 1000)
            start = max(start, floors.get(iid, start))
            start = min(start, caps.get(iid, start))
            placed[iid] = (start, durations[iid])
        return placed

    floors, caps = {}, {}
    for _ in range(6):
        placed = place(floors, caps)
        progress = False
        for item in flat:
            iid, constraint = item["itemId"], item.get("endConstraint")
            if not constraint:
                continue
            tid = constraint["before"].removesuffix(".vocalStart")
            entry = entry_of.get(song_of.get(tid))
            if tid not in placed or entry is None or not 0 <= entry <= durations[tid] / 1000:
                continue
            target_start = placed[tid][0]
            deadline = target_start + round((entry - constraint["marginSeconds"]) * 1000)
            start, dur = placed[iid]
            violation = start + dur - deadline
            if violation <= 0:
                continue
            latest_start = deadline - dur
            if 0 <= latest_start < start and caps.get(iid) != start:
                caps[iid] = latest_start  # ① 口播前移
                progress = True
            elif floors.get(tid) != target_start:
                floors[tid] = target_start + violation  # ② 歌曲顺延
                progress = True
        if not progress:
            break

    def overlap(a, b):
        return a[0] < b[0] + b[1] and b[0] < a[0] + a[1]

    warnings = []
    for item in flat:
        iid, constraint = item["itemId"], item.get("endConstraint")
        if placed[iid][0] < 0:
            warnings.append(f"{iid}: 按预估时长起点为负，云端编译会直接拒绝")
        if not constraint:
            continue
        tid = constraint["before"].removesuffix(".vocalStart")
        entry = entry_of.get(song_of.get(tid))
        if entry is None or not 0 <= entry <= durations[tid] / 1000:
            warnings.append(f"{iid}: 压歌目标 {tid} 缺少可核验进唱点，云端编译将拒绝")
        elif placed[iid][0] + placed[iid][1] > placed[tid][0] + round((entry - constraint["marginSeconds"]) * 1000):
            warnings.append(f"{iid}: 预估口播在自动重排后仍越过 {tid} 进唱点安全收声线，云端按实测时长可能编译失败")
    for i, a in enumerate(flat):
        for b in flat[i + 1:]:
            if not overlap(placed[a["itemId"]], placed[b["itemId"]]):
                continue
            if a["kind"] == b["kind"] == "voice":
                warnings.append(f"{a['itemId']}/{b['itemId']}: 预估时长下人声重叠，云端编译会拒绝")
            for voice, music in ((a, b), (b, a)):
                if voice["kind"] == "voice" and music["kind"] == "music":
                    c = voice.get("endConstraint")
                    if not c or c["before"] != music["itemId"] + ".vocalStart":
                        warnings.append(f"{voice['itemId']}/{music['itemId']}: 预估时长下人声压歌但未声明进唱约束，云端编译会拒绝")
            if a["kind"] == b["kind"] == "music":
                early, late = (a, b) if placed[a["itemId"]][0] < placed[b["itemId"]][0] else (b, a)
                if late["start"]["anchor"] != early["itemId"] + ".end" or not -3 <= late["start"]["offsetSeconds"] < 0:
                    warnings.append(f"{early['itemId']}/{late['itemId']}: 预估时长下歌歌重叠未声明 crossfade，云端编译会拒绝")
    return warnings


def enrich_song(song, directory):
    song = dict(song)
    if not song.get("lyrics") and song.get("lyricsFile"):
        root = Path(directory).resolve()
        path = (root / song["lyricsFile"]).resolve()
        if not path.is_relative_to(root):
            raise InputError(f"{song['songId']}: lyricsFile 不得越过调研目录")
        song["lyrics"] = path.read_text(encoding="utf-8-sig")
    if "platformLinks" not in song:
        song["platformLinks"] = dict.fromkeys(PLATFORMS)
        for url in song.get("sourceUrls", []):
            platform = platform_of(url)
            if platform:
                if song["platformLinks"][platform] not in (None, url):
                    raise InputError(f"{song['songId']}: 同平台多版本，请显式选择 platformLinks.{platform}")
                song["platformLinks"][platform] = url
    if song.get("platformLinks"):
        existing_urls = list(song.get("sourceUrls") or [])
        for k in PLATFORMS:
            val = song["platformLinks"].get(k)
            if val and val not in existing_urls:
                existing_urls.append(val)
        if existing_urls:
            song["sourceUrls"] = existing_urls
    return song


def load_research(directory):
    root = Path(directory)
    if not root.is_dir():
        raise InputError("--research 须为含六个交付文件的目录；不再自动截断/迁移旧包")
    for name in ("research_plan.md", "lead_log.md"):
        if not (root/name).read_text(encoding="utf-8-sig").strip():
            raise InputError(f"{name} 不能为空")
    merged = {}
    expected = {"facts.json": ("topic", "plan", "facts", "conflicts", "unconfirmed", "gaps", "sources"),
                "stories.json": ("stories",), "music_pool.json": ("musicPool",), "topics.json": ("topics",)}
    for filename, keys in expected.items():
        obj = read_json(root/filename)
        if not isinstance(obj, dict):
            raise InputError(f"{filename}: 顶层必须为对象")
        for key in keys:
            if key not in obj:
                raise InputError(f"{filename}: 缺少 {key}")
            merged[key] = obj[key]
    errors = schema_errors(merged, "research.schema.json")
    if errors:
        raise InputError("\n".join(errors))
    merged["musicPool"] = [enrich_song(s, root) for s in merged["musicPool"]]
    return merged


def check_research(pack):
    errors = schema_errors(pack, "research.schema.json")
    if errors:
        return errors
    errors += check_facts(pack["facts"])
    if not all(is_url(u) for u in pack["sources"]):
        errors.append("sources: 必须是有效 HTTP(S) 来源 URL 列表")
    for group, field, prefix in [("facts", "id", "F"), ("stories", "id", "A"), ("musicPool", "songId", "S")]:
        ids = [x[field] for x in pack[group]]
        if ids != [f"{prefix}{i:02d}" for i in range(1, len(ids)+1)]:
            errors.append(f"{group}: ID 必须按 {prefix}01 起连续升序")
    fids = {f["id"] for f in pack["facts"]}
    aids = {s["id"] for s in pack["stories"]}
    sids = {s["songId"] for s in pack["musicPool"]}
    for story in pack["stories"]:
        if any(fid not in fids for fid in story["factIds"]):
            errors.append(f"{story['id']}: factIds 存在悬空引用")
        if not all(is_url(u) for u in story["sourceUrls"]):
            errors.append(f"{story['id']}: sourceUrls 非法")
    for song in pack["musicPool"]:
        errors += check_song(song)
    tids = [t["id"] for t in pack["topics"]]
    if len(set(tids)) != len(tids):
        errors.append("topics: ID 重复")
    for topic in pack["topics"]:
        if not (topic.get("中心论点") or topic.get("概念命题")):
            errors.append(f"{topic['id']}: 缺少中心论点/概念命题")
        for key, ids in [("事实", fids), ("轶事", aids), ("歌曲", sids)]:
            if any(i not in ids for i in topic["支撑"][key]):
                errors.append(f"{topic['id']}: 支撑.{key} 悬空引用")
    for conflict in pack["conflicts"]:
        refs = set(re.findall(r"F\d+", conflict))
        if not refs or not refs <= fids:
            errors.append("conflicts: 每条须写明有效 F 编号及各方说法/出处")
        for f in pack["facts"]:
            if f["id"] in refs and f["confidence"] == "双源确认":
                errors.append(f"{f['id']}: conflicts 中涉及的事实必须降级")
    return errors


def bind_research(doc, pack):
    """Deterministic, lossless enrichment: source data wins; IDs never renumbered."""
    if not isinstance(doc, dict) or not isinstance(doc.get("musicPool"), list) or not doc["musicPool"]:
        raise InputError("草稿须为 JSON 对象并含非空 musicPool 入选曲列表")
    doc = loads(json_bytes(doc))
    pool = {s["songId"]: s for s in pack["musicPool"]}
    songs = []
    for chosen in doc.get("musicPool", []):
        if not isinstance(chosen, dict) or not isinstance(chosen.get("songId"), str):
            raise InputError("musicPool 每项须为含 songId 的对象")
        sid = chosen.get("songId")
        if sid not in pool:
            raise InputError(f"入选曲 {sid} 不在调研音乐池")
        merged = dict(pool[sid])
        merged.update({k: v for k, v in chosen.items() if k in ("purpose", "playback")})
        songs.append(merged)
    doc["musicPool"] = songs
    # Full fact snapshot makes factRefs interpretable without the research directory.
    doc["factPool"] = pack["facts"]
    return doc


def display_tags(doc):
    """菜单展示用扁平标签：四维对象按 genre/theme/mood/scene 顺序摊平，旧扁平数组原样。"""
    tags = doc.get("tags") if isinstance(doc, dict) else None
    if isinstance(tags, dict):
        return [t for key in ("genre", "theme", "mood", "scene") for t in tags.get(key, [])]
    if tags is None:
        tags = doc.get("标签") or []
    return list(tags)


def extract_script(doc):
    return {"segments": [dict(id=i["itemId"], text=i["text"], factRefs=i["factRefs"], notes=i.get("notes", ""))
                         for b in doc["timeline"] for i in b["items"] if i["kind"] == "voice"]}


def provider_identity(url):
    platform = platform_of(url)
    if not platform:
        return None
    u = urlsplit(url)
    if platform == "netease":
        query = urlsplit(u.fragment).query if u.fragment else u.query
        ids = parse_qs(query).get("id", [])
        path = urlsplit(u.fragment).path if u.fragment else u.path
        if ids and re.fullmatch(r"[1-9]\d*", ids[0]) and path.rstrip("/") in ("song", "/song"):
            return "netease", ids[0]
    if platform == "youtube":
        if u.hostname == "youtu.be":
            vid = u.path.strip("/")
        elif u.path == "/watch":
            vid = parse_qs(u.query).get("v", [""])[0]
        else:
            vid = ""
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return "youtube", vid
    return None


def extract_playlist(doc, providers=("netease", "youtube")):
    tracks = []
    for index, song in enumerate(doc["musicPool"], 1):
        links = song.get("platformLinks") or {}
        choices = [provider_identity(links.get(p)) for p in providers if links.get(p)]
        identities = [x for x in choices if x]
        explicit = song.get("playback")
        identity = (explicit.get("provider"), explicit.get("providerTrackId")) if explicit else (identities[0] if identities else None)
        if identity is None:
            identity = ("netease", song.get("songId") or f"t{index}")
        tr = {
            "id": f"t{index}",
            "provider": identity[0],
            "providerTrackId": identity[1],
            "title": song["title"],
            "artist": song["artist"],
            "durationSeconds": song["durationSeconds"],
            "recordingId": song.get("recordingId"),
        }
        if song.get("sourceUrls"):
            tr["sourceUrls"] = song["sourceUrls"]
        if song.get("platformLinks"):
            tr["platformLinks"] = song["platformLinks"]
        tracks.append(tr)
    return {"playlistId": "playlist-" + doc["menu_id"].rsplit("-v", 1)[0],
            "version": int(doc["menu_id"].rsplit("-v", 1)[1]),
            "createdAt": doc["createdAt"] + "T00:00:00Z", "tracks": tracks}


TRACK_PROVIDERS = ("youtube", "netease", "fixture")  # 与云端 trackref.validate_tracks 同口径


def check_tracks(tracks):
    """TrackRef 校验，镜像云端上传对 playlist.json 的逐曲机检：
    provider 白名单、非空身份字段、正时长、禁临时播放字段、musicdl 稳定身份。"""
    errors = []
    seen_ids = set()
    slug = re.compile(r"^[a-z0-9]+([.-][a-z0-9]+)*$")
    for i, t in enumerate(tracks):
        label = f"playlist.tracks[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{label} 必须为对象")
            continue
        tid = t.get("id")
        if not tid or not slug.fullmatch(str(tid)):
            errors.append(f"{label}.id 非法歌单内 ID")
        elif tid in seen_ids:
            errors.append(f"{label}.id 重复: {tid}")
        else:
            seen_ids.add(tid)
        if t.get("provider") not in TRACK_PROVIDERS:
            errors.append(f"{label}.provider 非法（{TRACK_PROVIDERS}）")
        for key in ("providerTrackId", "title", "artist"):
            if not str(t.get(key) or "").strip():
                errors.append(f"{label}.{key} 缺失")
        dur = t.get("durationSeconds")
        if not isinstance(dur, (int, float)) or dur <= 0:
            errors.append(f"{label}.durationSeconds 必填且>0（音频普查/平台元数据口径）")
        for key in ("playbackUrl", "url", "streamUrl"):
            if key in t:
                errors.append(f"{label} 禁止包含临时播放字段 {key}")
        if "musicdl" in t:
            identity = t["musicdl"]
            if (not isinstance(identity, dict) or set(identity) != {"source", "identifier"}
                    or any(not isinstance(identity[k], str) or not identity[k].strip()
                           for k in ("source", "identifier"))):
                errors.append(f"{label}.musicdl 只允许 source/identifier 稳定身份")
    return errors


def report(errors, success):
    if errors:
        print("检查未通过：\n" + "\n".join(f"- {e}" for e in errors))
        return 1
    print(success)
    return 0
