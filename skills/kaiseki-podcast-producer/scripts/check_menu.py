#!/usr/bin/env python3
"""Validate a self-contained v3 menu, without repository dependencies."""
import argparse
from contract import InputError, check_menu, preview_cloud_compile, read_json, report


def main():
    ap = argparse.ArgumentParser(description="v3 菜单检查（--draft 放宽曲库字段/正文完备度）")
    ap.add_argument("menu")
    ap.add_argument("--draft", action="store_true")
    args = ap.parse_args()
    try:
        doc = read_json(args.menu)
        errors = check_menu(doc, args.draft)
        if errors:
            return report(errors, "")
        if args.draft:
            print("草稿结构通过；不能作为交付完成")
            return 0
        warnings = preview_cloud_compile(doc)
        if warnings:
            print("云端编译预演警告（按保守语速预估 TTS 时长，非门禁，实测以云端为准）：")
            for w in warnings:
                print(f"- {w}")
        print("v3 菜单静态检查通过；尚不代表在线音源或音频 QA 通过")
        return 0
    except (InputError, OSError) as exc:
        print(f"输入/环境错误：{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
