#!/usr/bin/env python3
"""Validate all six research deliverables; never truncate or invent facts."""
import argparse
from contract import InputError, check_research, load_research, report


def main():
    ap = argparse.ArgumentParser(description="独立调研包机检（六文件及歌词）")
    ap.add_argument("directory")
    args = ap.parse_args()
    try:
        return report(check_research(load_research(args.directory)),
                      "调研包静态检查通过；来源真实性、独立性和创作配比仍须人工核实")
    except (InputError, OSError) as exc:
        print(f"输入/环境错误：{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
