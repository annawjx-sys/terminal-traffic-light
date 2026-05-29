#!/usr/bin/env python3
"""生成像素猫咪图标和 macOS .app 应用包"""

import os
import struct
import subprocess
import zlib

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TerminalTrafficLight.app")
CONTENTS_DIR = os.path.join(APP_DIR, "Contents")
MACOS_DIR = os.path.join(CONTENTS_DIR, "MacOS")
RESOURCES_DIR = os.path.join(CONTENTS_DIR, "Resources")
ICONSET_DIR = os.path.join(RESOURCES_DIR, "AppIcon.iconset")

# ── 像素猫咪 16x16 设计 ──────────────────────────────────
# 0=透明 1=黑色 3=白色(眼白) 4=绿色(眼珠) 5=粉色(鼻子) 6=深灰(内耳)
CAT_PIXELS = [
    [0,0,1,1,0,0,0,0,0,0,0,0,1,1,0,0],  # 耳尖
    [0,1,6,1,1,0,0,0,0,0,1,1,6,1,1,0],  # 内耳
    [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],  # 头顶
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],  # 头
    [1,1,3,3,4,1,1,1,1,1,1,4,3,3,1,1],  # 眼睛
    [1,1,3,3,3,1,1,1,1,1,1,3,3,3,1,1],  # 眼睛
    [1,1,1,1,1,1,5,5,5,5,1,1,1,1,1,1],  # 鼻子
    [1,1,1,1,1,1,1,5,5,1,1,1,1,1,1,1],  # 嘴
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],  # 下巴
    [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],  # 脸
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0],  # 脖子
    [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],  # 身体
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],  # 身体+尾巴
    [0,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0],  # 身体
    [0,1,1,0,0,1,1,1,1,1,0,0,1,1,0,0],  # 爪子
    [0,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0],  # 爪子
]

COLOR_MAP = {
    0: (0, 0, 0, 0),         # 透明
    1: (30, 30, 30, 255),    # 黑色
    3: (255, 255, 255, 255), # 眼白
    4: (80, 200, 120, 255),  # 绿色眼珠
    5: (255, 150, 150, 255), # 粉色鼻子
    6: (80, 60, 70, 255),    # 内耳（深粉灰）
}


def _make_png(width, height, pixels_rgba):
    """从 RGBA 像素数据生成 PNG 字节。"""
    rows = []
    for y in range(height):
        row = b"\x00"  # filter: None
        for x in range(width):
            r, g, b, a = pixels_rgba[y * width + x]
            row += bytes([r, g, b, a])
        rows.append(row)
    raw = b"".join(rows)

    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    buf = b"\x89PNG\r\n\x1a\n"
    buf += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    buf += chunk(b"IDAT", zlib.compress(raw, 9))
    buf += chunk(b"IEND", b"")
    return buf


def generate_cat_png(size):
    """生成指定大小的像素猫咪 PNG（放大像素风格）。"""
    pixel_size = size // 16
    # 补齐到精确 size
    actual = pixel_size * 16
    pixels = []
    for y in range(actual):
        for x in range(actual):
            cy = y // pixel_size
            cx = x // pixel_size
            if cy < 16 and cx < 16:
                color = COLOR_MAP[CAT_PIXELS[cy][cx]]
            else:
                color = (0, 0, 0, 0)
            pixels.append(color)
    return _make_png(actual, actual, pixels)


def create_iconset():
    """创建 macOS iconset 目录。"""
    os.makedirs(ICONSET_DIR, exist_ok=True)
    sizes = {
        "icon_16x16.png": 16,
        "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32,
        "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512,
        "icon_512x512@2x.png": 1024,
    }
    for name, size in sizes.items():
        path = os.path.join(ICONSET_DIR, name)
        with open(path, "wb") as f:
            f.write(generate_cat_png(size))
    return ICONSET_DIR


def create_icns():
    """从 iconset 生成 .icns 文件。"""
    iconset_path = create_iconset()
    icns_path = os.path.join(RESOURCES_DIR, "AppIcon.icns")
    result = subprocess.run(
        ["iconutil", "-c", "icns", iconset_path, "-o", icns_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"iconutil error: {result.stderr}")
        return False
    return True


def create_app_bundle():
    """创建 .app 应用包。"""
    # 创建目录结构
    for d in [CONTENTS_DIR, MACOS_DIR, RESOURCES_DIR]:
        os.makedirs(d, exist_ok=True)

    # 复制主脚本到 MacOS/
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terminal_traffic_light.py")
    dst = os.path.join(MACOS_DIR, "terminal_traffic_light")
    with open(src, "r") as f:
        content = f.read()
    # 修改图标路径：使用 .app 内的 Resources/icons
    content = content.replace(
        'icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")',
        'icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Resources", "icons")',
    )
    with open(dst, "w") as f:
        f.write(content)
    os.chmod(dst, 0o755)

    # 复制图标目录到 Resources/
    src_icons = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
    dst_icons = os.path.join(RESOURCES_DIR, "icons")
    os.makedirs(dst_icons, exist_ok=True)
    for name in ["red.png", "yellow.png", "green.png"]:
        src_file = os.path.join(src_icons, name)
        dst_file = os.path.join(dst_icons, name)
        if os.path.exists(src_file):
            with open(src_file, "rb") as sf:
                with open(dst_file, "wb") as df:
                    df.write(sf.read())

    # 生成 .icns 图标
    if not create_icns():
        print("Warning: icns generation failed, dock icon will be default")

    # 写 Info.plist
    plist = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>TerminalTrafficLight</string>
    <key>CFBundleDisplayName</key>
    <string>Terminal Traffic Light</string>
    <key>CFBundleIdentifier</key>
    <string>com.annawei.terminal-traffic-light</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleExecutable</key>
    <string>terminal_traffic_light</string>
    <key>LSUIElement</key>
    <false/>
    <key>LSBackgroundOnly</key>
    <false/>
</dict>
</plist>'''
    with open(os.path.join(CONTENTS_DIR, "Info.plist"), "w") as f:
        f.write(plist)

    print(f"App bundle created: {APP_DIR}")
    print(f"Launch with: open {APP_DIR}")


if __name__ == "__main__":
    # 先生成一个预览图标
    preview = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cat_preview.png")
    with open(preview, "wb") as f:
        f.write(generate_cat_png(256))
    print(f"Preview: {preview}")

    create_app_bundle()
