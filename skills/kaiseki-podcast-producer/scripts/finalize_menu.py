#!/usr/bin/env python3
"""Bind selected song IDs and fact snapshot to a v3 draft; write a separate final."""
import argparse
from pathlib import Path
from contract import InputError, bind_research, check_menu, check_research, json_bytes, load_research, read_json, report


def main():
    ap = argparse.ArgumentParser(description="从调研包补齐内嵌歌词、平台链接、事实池，不改时序与台词")
    ap.add_argument("menu")
    ap.add_argument("--research", required=True)
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()
    try:
        research = load_research(args.research)
        errors = check_research(research)
        if errors:
            return report(errors, "")
        doc = bind_research(read_json(args.menu), research)
        doc["status"] = "final"
        errors = check_menu(doc)
        if errors:
            return report(errors, "")
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("xb") as f:
            f.write(json_bytes(doc))
        print(f"已生成自包含 v3 菜单：{out.resolve()}")
        return 0
    except (InputError, OSError) as exc:
        print(f"输入/环境错误：{exc}；输出已存在时请使用新版本/路径")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
