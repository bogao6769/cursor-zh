# -*- coding: utf-8 -*-
"""把汉化脚本和额度挂件静态注入 Cursor 的 workbench 包（可重复执行）。

流程：剥离旧补丁 -> 与备份比对原始哈希 -> 逐块插入 -> 重算 product.json 校验值
"""
import base64
import hashlib
import json
import os
import re
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
DICT_PATH = os.path.join(TOOL, "dict", "zh-CN.json")
EXTRA_PATH = os.path.join(HERE, "dict-extra.json")
TPL_PATH = os.path.join(HERE, "translator.js")
WIDGET_PATH = os.path.join(TOOL, "quota", "widget.js")

TARGETS = [
    "vs/workbench/workbench.desktop.main.js",
    "vs/workbench/workbench.glass.main.js",
]
CHECKED = "vs/workbench/workbench.desktop.main.js"

BLOCK_RE = re.compile(
    rb"\n/\* cursor-zh-inline begin(?::[a-z\-]+)? \*/.*?/\* cursor-zh-inline end(?::[a-z\-]+)? \*/\n",
    re.S,
)


def b64sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode().rstrip("=")


def load_dict():
    raw = json.load(open(DICT_PATH, encoding="utf-8"))
    exact = {k: v for k, v in raw.get("exact", {}).items() if not k.startswith("_")}
    if os.path.exists(EXTRA_PATH):
        extra = json.load(open(EXTRA_PATH, encoding="utf-8"))
        for k, v in extra.get("exact", {}).items():
            if not k.startswith("_"):
                exact[k] = v
    return {
        "exact": exact,
        "patterns": raw.get("patterns", []),
        "suffixes": raw.get("suffixes", []),
        "skipSelectors": raw.get("skipSelectors", []),
        "attributes": raw.get("attributes", []),
        "segmentSeparators": raw.get("segmentSeparators", [", "]),
        "segmentJoiner": raw.get("segmentJoiner", "，"),
    }


def build_blocks():
    dict_obj = load_dict()
    tpl = open(TPL_PATH, encoding="utf-8").read()
    translator = tpl.replace("__DICT__", json.dumps(dict_obj, ensure_ascii=False, separators=(",", ":")))
    widget = open(WIDGET_PATH, encoding="utf-8").read()
    blocks = [("translator", translator), ("quota", widget)]
    out = b""
    for name, code in blocks:
        out += ("\n/* cursor-zh-inline begin:%s */\n" % name).encode()
        out += code.encode("utf-8")
        out += ("\n/* cursor-zh-inline end:%s */\n" % name).encode()
    print("blocks:", ", ".join(n for n, _ in blocks), "| payload:", len(out), "bytes",
          "| dict:", len(dict_obj["exact"]))
    return out


def main():
    prod_path = os.path.join(APP, "product.json")
    prod = json.load(open(prod_path, encoding="utf-8"))
    ver = prod.get("version") or "unknown"
    backup = os.path.join(TOOL, "backup", ver)
    if not os.path.isdir(backup):
        os.makedirs(backup)

    originals = {}
    for t in TARGETS:
        p = os.path.join(APP, "out", t)
        if not os.path.exists(p):
            print("skip (missing):", t)
            continue
        data = BLOCK_RE.sub(b"", open(p, "rb").read())
        originals[p] = data
        bk = os.path.join(backup, os.path.basename(p))
        if not os.path.exists(bk):
            shutil.copy2(p, bk)

    for p, data in originals.items():
        bk = os.path.join(backup, os.path.basename(p))
        if hashlib.sha256(data).hexdigest() != hashlib.sha256(open(bk, "rb").read()).hexdigest():
            raise SystemExit("剥离后与备份不一致，终止: %s" % os.path.basename(p))
    print("restore-check: OK")

    payload = build_blocks()

    for p, data in originals.items():
        idx = data.rfind(b"//# sourceMappingURL=")
        if idx == -1:
            idx = len(data)
        out = data[:idx] + payload + data[idx:]
        open(p, "wb").write(out)
        print("patched:", os.path.basename(p), len(data), "->", len(out))

    checked = os.path.join(APP, "out", CHECKED)
    old = prod["checksums"][CHECKED]
    new = b64sha(checked)
    if old != new:
        text = open(prod_path, encoding="utf-8").read()
        cnt = text.count('"%s"' % old)
        text = text.replace('"%s"' % old, '"%s"' % new)
        open(prod_path, "w", encoding="utf-8", newline="").write(text)
        print("checksum:", old[:12], "->", new[:12], "replaced:", cnt)

    ok = json.load(open(prod_path, encoding="utf-8"))["checksums"][CHECKED] == b64sha(checked)
    print("verify:", "OK" if ok else "FAILED")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
