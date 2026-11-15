#!/usr/bin/env python3
"""
版本更新工具：把版本號往前推一版，並記錄這次更新了哪些功能。

用法：
    python3 tools/bump_version.py "新增 XXX 功能" "修正 YYY 問題"
    python3 tools/bump_version.py --minor --title "任務流程改版" "新增 A" "調整 B"
    python3 tools/bump_version.py --major "..."

預設推進修訂號 (x.y.Z)；--minor 推進次版號 (x.Y.0)；--major 推進主版號 (X.0.0)。
會同時更新 version.py（VERSION 與 CHANGELOG）並重新產生 CHANGELOG.md。
只想依 version.py 重新產生 CHANGELOG.md 時：python3 tools/bump_version.py --sync
"""
import argparse
import datetime
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(ROOT, "version.py")
CHANGELOG_FILE = os.path.join(ROOT, "CHANGELOG.md")


def next_version(current: str, level: str) -> str:
    major, minor, patch = (int(x) for x in current.split("."))
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def write_markdown():
    sys.path.insert(0, ROOT)
    for name in ("version",):
        sys.modules.pop(name, None)
    import version
    lines = [f"# {version.APP_NAME} 更新紀錄", "",
             "此檔案由 `tools/bump_version.py` 依 `version.py` 產生，請勿手動編輯。", ""]
    for item in version.CHANGELOG:
        title = f" - {item['title']}" if item.get("title") else ""
        lines.append(f"## v{item['version']} ({item.get('date', '')}){title}")
        lines.append("")
        lines += [f"- {c}" for c in item.get("changes", [])]
        lines.append("")
    with open(CHANGELOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return version.VERSION


def main():
    parser = argparse.ArgumentParser(description="推進版本號並記錄更新內容")
    parser.add_argument("changes", nargs="*", help="這次更新的項目（每項一個引號字串）")
    parser.add_argument("--minor", action="store_true", help="推進次版號")
    parser.add_argument("--major", action="store_true", help="推進主版號")
    parser.add_argument("--title", default="", help="這一版的標題（可省略）")
    parser.add_argument("--sync", action="store_true", help="只重新產生 CHANGELOG.md")
    args = parser.parse_args()

    if args.sync:
        print(f"已依 version.py 重新產生 CHANGELOG.md (v{write_markdown()})")
        return
    if not args.changes:
        parser.error("請至少提供一項更新內容，例如: python3 tools/bump_version.py \"新增 XXX\"")

    with open(VERSION_FILE, "r", encoding="utf-8") as f:
        src = f.read()
    m = re.search(r'^VERSION = "(\d+\.\d+\.\d+)"', src, flags=re.M)
    if not m:
        sys.exit("找不到 version.py 中的 VERSION")
    current = m.group(1)
    new = next_version(current, "major" if args.major else "minor" if args.minor else "patch")

    def quote(text: str) -> str:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    entry = ["    {",
             f'        "version": "{new}",',
             f'        "date": "{datetime.date.today().isoformat()}",',
             f'        "title": {quote(args.title)},',
             '        "changes": [']
    entry += [f"            {quote(c)}," for c in args.changes]
    entry += ["        ],", "    },"]

    src = src.replace(m.group(0), f'VERSION = "{new}"', 1)
    marker = "CHANGELOG = [\n"
    if marker not in src:
        sys.exit("找不到 version.py 中的 CHANGELOG")
    src = src.replace(marker, marker + "\n".join(entry) + "\n", 1)
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(src)
    write_markdown()
    print(f"版本已更新: v{current} -> v{new}")
    for c in args.changes:
        print(f"  - {c}")


if __name__ == "__main__":
    main()
