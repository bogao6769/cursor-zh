# -*- coding: utf-8 -*-
"""把 Cursor 恢复到打补丁之前的状态。

用法：
  python restore.py          仅检查备份完整性（不写文件）
  python restore.py --apply  真正还原
"""
import base64
import hashlib
import json
import os
import shutil
import sys

DEFAULT_DIRS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\cursor\resources\app"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Cursor\resources\app"),
    r"C:\Program Files\Cursor\resources\app",
]


def resolve_app():
    env = os.environ.get("CURSOR_APP_DIR")
    if env:
        return env
    for d in DEFAULT_DIRS:
        if os.path.isfile(os.path.join(d, "product.json")):
            return d
    raise SystemExit("未找到 Cursor 安装目录；请设置环境变量 CURSOR_APP_DIR 指向 Cursor 的 resources\\app")


APP = resolve_app()
HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)

TARGETS = [
    "vs/workbench/workbench.desktop.main.js",
    "vs/workbench/workbench.glass.main.js",
]
CHECKED = "vs/workbench/workbench.desktop.main.js"


def b64sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode().rstrip("=")


def main():
    apply = "--apply" in sys.argv
    prod_path = os.path.join(APP, "product.json")
    prod = json.load(open(prod_path, encoding="utf-8"))
    ver = prod.get("version") or "unknown"
    backup = os.path.join(TOOL, "backup", ver)
    if not os.path.isdir(backup):
        raise SystemExit("找不到备份目录: %s" % backup)

    sums = {}
    sp = os.path.join(backup, "CHECKSUMS.txt")
    if os.path.exists(sp):
        for line in open(sp, encoding="utf-8"):
            parts = line.split()
            if len(parts) == 2:
                sums[parts[1]] = parts[0]

    ok = True
    for t in TARGETS:
        name = os.path.basename(t)
        bk = os.path.join(backup, name)
        if not os.path.exists(bk):
            print("缺少备份:", name)
            ok = False
            continue
        cur = b64sha(bk)
        tag = "OK" if sums.get(name) in (None, cur) else "MISMATCH"
        if tag != "OK":
            ok = False
        print("%-28s backup=%s %s" % (name, cur[:12], tag))

    if not apply:
        print("\n仅检查。加 --apply 执行还原（请先完全退出 Cursor）。")
        return 0 if ok else 2

    for t in TARGETS:
        name = os.path.basename(t)
        bk = os.path.join(backup, name)
        dst = os.path.join(APP, "out", t)
        if os.path.exists(bk):
            shutil.copy2(bk, dst)
            print("restored:", name)

    checked = os.path.join(APP, "out", CHECKED)
    old = json.load(open(prod_path, encoding="utf-8"))["checksums"][CHECKED]
    new = b64sha(checked)
    if old != new:
        text = open(prod_path, encoding="utf-8").read()
        cnt = text.count('"%s"' % old)
        text = text.replace('"%s"' % old, '"%s"' % new)
        open(prod_path, "w", encoding="utf-8", newline="").write(text)
        print("checksum:", old[:12], "->", new[:12], "replaced:", cnt)

    ok2 = json.load(open(prod_path, encoding="utf-8"))["checksums"][CHECKED] == b64sha(checked)
    print("verify:", "OK" if ok2 else "FAILED")
    return 0 if ok2 else 3


if __name__ == "__main__":
    sys.exit(main())
