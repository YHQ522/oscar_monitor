"""生成应用图标 assets/oscar-monitor.ico（多尺寸），供 PyInstaller 打包使用。

用法: python make_icon.py
前置: pip install pillow
"""
from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("需要 pillow：python -m pip install pillow")

OUT = Path(__file__).resolve().parent / "assets" / "oscar-monitor.ico"
OUT.parent.mkdir(parents=True, exist_ok=True)

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圆角深色底
d.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=48, fill=(24, 42, 66, 255))

# 顶部标题条
d.rounded_rectangle([24, 24, SIZE - 24, 44], radius=10, fill=(80, 120, 200, 255))

# 显示屏（监控大屏）
d.rounded_rectangle(
    [40, 60, SIZE - 40, SIZE - 56],
    radius=12,
    fill=(13, 22, 36, 255),
    outline=(120, 170, 255, 255),
    width=6,
)

# 健康折线（绿色脉冲）
pts = [(56, 150), (96, 120), (128, 140), (160, 96), (200, 112), (220, 84)]
d.line(pts, fill=(80, 220, 140, 255), width=10, joint="curve")
for x, y in pts:
    d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(80, 220, 140, 255))

# 底脚
d.rounded_rectangle([110, SIZE - 48, 146, SIZE - 30], radius=9, fill=(80, 120, 200, 255))
d.rounded_rectangle([80, SIZE - 30, 176, SIZE - 20], radius=5, fill=(80, 120, 200, 255))

img.save(OUT, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"已生成图标: {OUT}")
