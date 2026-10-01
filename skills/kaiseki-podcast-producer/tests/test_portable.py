"""Observable delivery invariants, including relocation without site-packages."""
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from contract import (SKILL_DIR, InputError, bind_research, check_menu, check_research, check_tracks,
                      enrich_song, extract_playlist, json_bytes, load_research, loads,
                      preview_cloud_compile, read_json)
from pack_menu import build_bundle, validate_bundle


def example():
    return read_json(SKILL_DIR / "assets/menu.example.json")


def research_fixture():
    doc = example()
    facts = []
    for i in range(1, 21):
        f = copy.deepcopy(doc["factPool"][0])
        f["id"] = f"F{i:02d}"
        facts.append(f)
    songs = []
    for i in range(1, 11):
        s = copy.deepcopy(doc["musicPool"][0])
        s.update(songId=f"S{i:02d}", title=f"合成测试歌曲{i}")
        s["platformLinks"]["netease"] = f"https://music.163.com/song?id={i}"
        songs.append(s)
    return {"topic": "合成结构测试", "plan": ["核对字段", "核对引用"], "facts": facts,
            "stories": [{"id": f"A{i:02d}", "title": "测试故事", "summary": "测试铺垫到兑现",
                         "factIds": ["F01"], "sourceUrls": ["https://example.org/test"]} for i in range(1, 9)],
            "musicPool": songs,
            "topics": [{"id": f"T{i}", "中心论点": "合成论点", "支撑": {"事实": ["F01"], "轶事": ["A01"], "歌曲": ["S01"]}} for i in range(1, 4)],
            "conflicts": [], "unconfirmed": [], "gaps": [], "sources": ["https://example.org/test"]}


def write_research(path):
    path.mkdir(parents=True)
    pack = research_fixture()
    for name, keys in {"facts.json": ("topic", "plan", "facts", "conflicts", "unconfirmed", "gaps", "sources"),
                       "stories.json": ("stories",), "music_pool.json": ("musicPool",), "topics.json": ("topics",)}.items():
        (path/name).write_bytes(json_bytes({k: pack[k] for k in keys}))
    for name in ("research_plan.md", "lead_log.md"):
        (path/name).write_text("自检合成材料，不涉及网络", encoding="utf-8")


class PortableTests(unittest.TestCase):
    def test_valid_example_and_deterministic_zip(self):
        doc = example()
        self.assertEqual(check_menu(doc), [])
        data = build_bundle(doc)
        self.assertEqual(data, build_bundle(doc))
        docs = validate_bundle(data)
        self.assertEqual(len(docs["script.json"]["segments"]), 3)
        self.assertEqual(docs["playlist.json"]["tracks"][0]["provider"], "netease")

    def test_malformed_content_rejected_by_both_gates(self):
        for text in ("", "<#0.50#>开头", "结尾<#1.00#>", "前<#100.00#>后",
                     "前<#0.10#>，<#0.20#>后", "前<#broken"):
            with self.subTest(text=text):
                doc = example()
                doc["timeline"][0]["items"][1]["text"] = text
                self.assertTrue(check_menu(doc))
                with self.assertRaises(InputError):
                    build_bundle(doc)

    def test_flexible_pause_precision_and_editorial_text_are_allowed(self):
        for text in ("前<#1.2#>后", "事实F01不能朗读", "正文（轻声）"):
            with self.subTest(text=text):
                doc = example()
                doc["timeline"][0]["items"][1]["text"] = text
                self.assertEqual(check_menu(doc), [])
                build_bundle(doc)

    def test_all_voice_missing(self):
        doc = example()
        for b in doc["timeline"]:
            b["items"] = [i for i in b["items"] if i["kind"] == "music"]
        self.assertTrue(check_menu(doc))

    def test_draft_cannot_be_published_as_final(self):
        doc = example()
        doc["status"] = "draft"
        self.assertEqual(check_menu(doc, draft=True), [])
        with self.assertRaises(InputError):
            build_bundle(doc)

    def test_invalid_references_and_structure(self):
        mutations = [
            lambda d: d["timeline"].reverse(),
            lambda d: d["timeline"][0]["items"][0].update(songId="S99"),
            lambda d: d["timeline"][0]["items"][1]["start"].update(anchor="P2.end"),
            lambda d: d["timeline"][0]["items"][1]["start"].update(offsetSeconds=-1),
            lambda d: d["chapters"][0].update(blocks="B1-B99"),
            lambda d: d["musicPool"][0].update(lyricsSource={}),
        ]
        for mutate in mutations:
            doc = example()
            mutate(doc)
            self.assertTrue(check_menu(doc))

    def test_editorial_metadata_does_not_block_menu_structure(self):
        mutations = [
            lambda d: d["timeline"][0].update(density="dense"),
            lambda d: d["coverColors"]["colors"][0].update(h=90),
            lambda d: d["timeline"][0]["items"][1].update(factRefs=["F99"]),
            lambda d: d["timeline"][0]["items"][1]["start"].update(offsetSeconds=.001),
            lambda d: d["timeline"][0].update(voice={}),
        ]
        for mutate in mutations:
            doc = example()
            mutate(doc)
            self.assertEqual(check_menu(doc), [])

    def test_intro_requires_constraint(self):
        doc = example()
        voice = doc["timeline"][0]["items"][1]
        voice["start"] = {"anchor": "P1.start", "offsetSeconds": 1}
        self.assertTrue(check_menu(doc))
        voice["endConstraint"] = {"before": "P1.vocalStart", "marginSeconds": 2, "onViolation": "error"}
        doc["musicPool"][0]["vocalStartEstimateSeconds"] = 30
        self.assertEqual(check_menu(doc), [])

    def test_endconstraint_requires_derivable_vocal_entry(self):
        doc = example()
        voice = doc["timeline"][0]["items"][1]
        voice["start"] = {"anchor": "P1.start", "offsetSeconds": 1}
        voice["endConstraint"] = {"before": "P1.vocalStart", "marginSeconds": 2, "onViolation": "error"}
        self.assertTrue(any("进唱点" in e for e in check_menu(doc)))  # 歌词无时间戳且无估计
        doc["musicPool"][0]["lyrics"] = "[00:05.00]第一句人声歌词"
        self.assertEqual(check_menu(doc), [])                        # 带时间戳 LRC
        doc["musicPool"][0]["lyrics"] = "纯文本歌词，没有时间轴"
        doc["musicPool"][0]["vocalStartEstimateSeconds"] = 30
        self.assertEqual(check_menu(doc), [])                        # 显式估计
        doc["musicPool"][0]["vocalStartEstimateSeconds"] = 500       # 估计超出参考时长 61s
        self.assertTrue(any("进唱点" in e for e in check_menu(doc)))

    def test_ending_craft_is_editorial_guidance_not_a_structural_gate(self):
        # Ending 引用与告别句属于创作指导，结构校验允许编辑自由调整。
        doc = example()
        voice_only = copy.deepcopy(doc)  # 人声收尾合法：去掉收尾整曲后仍应通过
        voice_only["timeline"][2]["items"] = [i for i in voice_only["timeline"][2]["items"] if i["kind"] == "voice"]
        voice_only["musicPool"] = voice_only["musicPool"][:2]
        self.assertEqual(check_menu(voice_only), [])
        bad = copy.deepcopy(doc)
        bad["timeline"][2]["items"][0]["factRefs"] = ["F01"]
        self.assertEqual(check_menu(bad), [])
        free = copy.deepcopy(doc)  # 告别句每期现写：不含任何固定锚定也合法
        free["timeline"][2]["items"][0]["text"] = "压轴新料。<#0.80#>那张票根他一直夹在琴盒里。"
        self.assertEqual(check_menu(free), [])
        self.assertEqual(check_menu(doc), [])  # 原样例（音乐收尾形态）本身合规

    def test_recommendation_metadata_does_not_block_menu_structure(self):
        # 标签与实体字段不拦截菜单结构；结构字段仍由其他测试覆盖。
        doc = example()
        self.assertEqual(check_menu(doc), [])  # 样例：四维标签 + 齐备证据 + 可溯源实体
        tagless = copy.deepcopy(doc)  # 无标签菜单合法
        for key in ("tags", "artists", "related_entities", "tag_evidence"):
            tagless.pop(key, None)
        self.assertEqual(check_menu(tagless), [])
        free = copy.deepcopy(doc)  # 标签词自由生成：词表外的新词合法
        free["tags"]["genre"] = ["赛博朋克"]
        free["tag_evidence"]["赛博朋克"] = [1]
        free["tag_evidence"].pop("实验音乐")
        self.assertEqual(check_menu(free), [])
        bad = copy.deepcopy(doc)  # 未知维度
        bad["tags"]["风格"] = ["民谣"]
        self.assertEqual(check_menu(bad), [])
        bad = copy.deepcopy(doc)  # 证据块号越界
        bad["tag_evidence"]["实验音乐"] = [1, 9]
        self.assertEqual(check_menu(bad), [])
        bad = copy.deepcopy(doc)  # 缺证据
        bad["tag_evidence"].pop("技术工艺")
        self.assertEqual(check_menu(bad), [])
        bad = copy.deepcopy(doc)  # 证据多余键
        bad["tag_evidence"]["民谣"] = [1]
        self.assertEqual(check_menu(bad), [])
        bad = copy.deepcopy(doc)  # 实体无原文出处
        bad["artists"] = [{"name": "梁晓雪", "role": "main"}]
        self.assertEqual(check_menu(bad), [])
        bad = copy.deepcopy(doc)  # related 只装提及对象
        bad["related_entities"] = [{"name": "测试作者", "role": "main"}]
        self.assertEqual(check_menu(bad), [])
        bad = copy.deepcopy(doc)  # artists 全是提及时缺主讲
        bad["artists"] = [{"name": "测试作者", "role": "mentioned"}]
        self.assertEqual(check_menu(bad), [])
        bad = copy.deepcopy(doc)  # 旧扁平数组形态
        bad["tags"] = ["民谣", "雨夜"]
        self.assertEqual(check_menu(bad), [])
        self.assertEqual(check_menu(doc), [])

    def test_check_tracks_mirrors_cloud_trackref(self):
        tracks = extract_playlist(example())["tracks"]
        self.assertEqual(check_tracks(tracks), [])
        for mutate in (lambda t: t.update(provider="spotify"),
                       lambda t: t.update(providerTrackId=" "),
                       lambda t: t.update(durationSeconds=0),
                       lambda t: t.update(playbackUrl="https://tmp.example/a.mp3"),
                       lambda t: t.update(musicdl={"source": "x"})):
            with self.subTest(mutate=mutate):
                bad = copy.deepcopy(tracks)
                mutate(bad[0])
                self.assertTrue(check_tracks(bad))
        self.assertTrue(check_tracks(list(tracks) + [dict(tracks[0])]))  # id 重复

    def test_compile_preview_clean_on_example(self):
        self.assertEqual(check_menu(example()), [])
        self.assertEqual(preview_cloud_compile(example()), [])

    def test_compile_preview_flags_voice_overlap_after_repair(self):
        # 长口播→目标曲→压歌短口播：两级自愈把短口播前移后与长口播重叠，云端编译将拒绝
        doc = example()
        song = doc["musicPool"][0]
        song["lyrics"] = "[00:05.00]第一句人声歌词\n[00:30.00]第二句人声歌词"
        doc["musicPool"] = [song, doc["musicPool"][2]]  # S01 压歌目标曲 + S03 收尾整曲
        block = {
            "blockId": "B1", "type": "hook", "narrativeFunction": "开场", "emotionalTarget": "好奇",
            "density": "sparse", "contentDirections": ["测试程序执行顺序；创作时替换为真实内容方向。"],
            "items": [
                {"itemId": "B1-a", "kind": "voice", "start": {"anchor": "timeline.start", "offsetSeconds": 0},
                 "text": "长口播" * 40, "factRefs": [], "notes": ""},
                {"itemId": "P1", "kind": "music", "songId": "S01", "mode": "full",
                 "start": {"anchor": "B1-a.end", "offsetSeconds": 0}},
                {"itemId": "B1-b", "kind": "voice", "start": {"anchor": "P1.start", "offsetSeconds": 0},
                 "text": "短口播" * 40, "factRefs": [], "notes": "",
                 "endConstraint": {"before": "P1.vocalStart", "marginSeconds": 2.0, "onViolation": "error"}},
            ]}
        doc["timeline"] = [block, {
            "blockId": "B2", "type": "ending", "narrativeFunction": "收束", "emotionalTarget": "释然",
            "density": "sparse", "contentDirections": ["测试程序执行顺序；创作时替换为真实内容方向。"],
            "items": [{"itemId": "B2-a", "kind": "voice", "start": {"anchor": "B1-b.end", "offsetSeconds": 0},
                       "text": "结尾口播正文。", "factRefs": ["F03"], "notes": ""},
                      {"itemId": "P2", "kind": "music", "songId": "S03", "mode": "full",
                       "start": {"anchor": "B2-a.end", "offsetSeconds": 0}}]}]
        doc["emotionalCurve"] = ["好奇", "释然"]
        doc["chapters"] = [{"keyword": "分章关键词", "blocks": "B1", "summary": "备注"},
                           {"keyword": "分章关键词", "blocks": "B2", "summary": "备注"}]
        doc["tag_evidence"] = {"实验音乐": [1, 2], "技术工艺": [1, 2], "平静": [2], "释然": [2]}
        self.assertEqual(check_menu(doc), [])
        warnings = preview_cloud_compile(doc)
        self.assertTrue(any("人声重叠" in w for w in warnings))

    def test_platform_links_optional_and_identity_fallback(self):
        # f9e92c2 口径：平台链接允许缺失；无目标平台身份时 playlist 按 songId 回退，
        # 由云端在线模式改为搜源，本地不再拦截
        doc = example()
        song = doc["musicPool"][0]
        song["platformLinks"]["netease"] = None
        song["missingPlatformReasons"]["netease"] = "无该版本"
        song["platformLinks"]["youtube"] = "https://www.youtube.com/watch?v=abcdefghijk"
        build_bundle(doc)  # kaiseki-v3 无 netease 身份：回退而非拒绝
        tracks = extract_playlist(doc)["tracks"]
        self.assertEqual(tracks[0]["provider"], "youtube")
        song["platformLinks"]["netease"] = "https://evil.example/song?id=123"
        self.assertEqual(check_menu(doc), [])  # 链接真实性不属结构机检

    def test_research_complete_and_incomplete(self):
        pack = research_fixture()
        self.assertEqual(check_research(pack), [])
        for key in ("stories", "musicPool"):
            bad = copy.deepcopy(pack)
            bad[key] = []
            self.assertTrue(check_research(bad))
        # topics 已降为可选创作角度参考：空数组合法，不再拦截
        bad = copy.deepcopy(pack)
        bad["topics"] = []
        self.assertEqual(check_research(bad), [])
        pack["facts"][0]["id"] = "wrong"
        self.assertTrue(check_research(pack))

    def test_conflicts_data_and_source_independence(self):
        for change in ("data", "conflict", "subdomain"):
            pack = research_fixture()
            fact = pack["facts"][0]
            if change == "data":
                fact["type"] = "数据"
            else:
                fact["confidence"] = "双源确认"
                fact["sourceUrls"] = ["https://a.example.com/a", "https://b.example.com/b"] if change == "subdomain" else ["https://example.org/a", "https://example.net/b"]
                if change == "conflict":
                    pack["conflicts"] = ["F01 两种说法矛盾"]
            self.assertTrue(check_research(pack))

    def test_non_json_numbers_and_duplicate_keys(self):
        for value in ('{"x": NaN}', '{"x": Infinity}', '{"x": 1,"x": 2}'):
            with self.assertRaises(InputError):
                loads(value)

    def test_tampered_zip_rejected(self):
        data = build_bundle(example())
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as original, zipfile.ZipFile(buf, "w") as z:
            for name in original.namelist():
                blob = original.read(name)
                if name == "script.json":
                    blob = blob.replace("测试".encode(), "篡改".encode())
                z.writestr(name, blob)
        with self.assertRaises(InputError):
            validate_bundle(buf.getvalue())

    def test_lyrics_path_cannot_escape(self):
        with tempfile.TemporaryDirectory() as root:
            song = dict(example()["musicPool"][0], lyrics="", lyricsFile="../outside.txt")
            with self.assertRaises(InputError):
                enrich_song(song, root)

    def test_relocated_cli_roundtrip_without_site_packages(self):
        with tempfile.TemporaryDirectory(prefix="怀石 portable ") as temp:
            root = Path(temp)
            skill = root / "复制 skill"
            shutil.copytree(SKILL_DIR, skill, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
            research = root/"节目 数据"/"调研包"
            write_research(research)
            draft = root/"草稿.json"
            draft.write_bytes(json_bytes(example()))
            final, archive = root/"终稿.json", root/"菜单.zip"
            steps = [("check_research_pack.py", str(research)),
                     ("finalize_menu.py", str(draft), "--research", str(research), "-o", str(final)),
                     ("check_menu.py", str(final)),
                     ("pack_menu.py", str(final), "--research", str(research), "-o", str(archive)),
                     ("pack_menu.py", "--verify", str(archive))]
            for script, *args in steps:
                p = subprocess.run([sys.executable, "-X", "utf8", "-S", str(skill/"scripts"/script), *args], cwd=root,
                                   capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            before = archive.read_bytes()
            p = subprocess.run([sys.executable, "-X", "utf8", "-S", str(skill/"scripts/pack_menu.py"), str(final),
                                "--research", str(research), "-o", str(archive)], cwd=root, capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(before, archive.read_bytes())
            (research/"topics.json").unlink()
            with self.assertRaises(OSError):
                load_research(research)
