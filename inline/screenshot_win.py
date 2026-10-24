# -*- coding: utf-8 -*-
"""抓取指定标题窗口的截图（ctypes + GDI），输出 PNG，无第三方依赖。
用法: screenshot_win.py out.png <标题关键字> [scale]
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import zlib

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
SRCCOPY = 0x00CC0020


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


def find_windows(keyword):
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if keyword.lower() in buf.value.lower():
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            w, h = r.right - r.left, r.bottom - r.top
            if w > 300 and h > 200:
                found.append((hwnd, buf.value, r.left, r.top, w, h))
        return True

    cb = cb
    user32.EnumWindows(cb, 0)
    return found


def grab(path, x, y, w, h, scale=1):
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, w, h, hdc, x, y, SRCCOPY)

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    raw = bytearray(buf.raw)

    lines = []
    for yy in range(0, h, scale):
        row = bytearray([0])
        base = yy * w * 4
        for xx in range(0, w, scale):
            i = base + xx * 4
            row += bytes((raw[i + 2], raw[i + 1], raw[i]))
        lines.append(bytes(row))
    data = b"".join(lines)
    ow, oh = (len(lines[0]) - 1) // 3, len(lines)

    def chunk(tag, d):
        return struct.pack(">I", len(d)) + tag + d + struct.pack(">I", zlib.crc32(tag + d) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", ow, oh, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(data, 6)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdc)
    print("saved", path, ow, "x", oh)


if __name__ == "__main__":
    out = sys.argv[1]
    kw = sys.argv[2] if len(sys.argv) > 2 else "Cursor"
    sc = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    ws = find_windows(kw)
    for w in ws:
        print("win:", w[1][:60], "|", w[2], w[3], w[4], w[5])
    if not ws:
        print("no window matched")
        sys.exit(1)
    ws.sort(key=lambda t: t[4] * t[5], reverse=True)
    hwnd, title, x, y, w, h = ws[0]
    print("picked:", title[:60], "hwnd=", hwnd)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    import time
    time.sleep(1.2)
    rr = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rr))
    x, y, w, h = rr.left, rr.top, rr.right - rr.left, rr.bottom - rr.top
    dpi = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    grab(out, x * dpi, y * dpi, w * dpi, h * dpi, sc)
