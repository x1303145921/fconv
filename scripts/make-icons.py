"""
fconv 图标生成器

沿用外部参考 logo 里的字母 f 形态（assets/icon-source.webp），流程：

  1. 定位参考图的圆形区域，裁成正方形（去掉周边棋盘格）
  2. 按「接近白 / 接近圆底色」把像素分开，得到 f 的软遮罩（圆外置零）
  3. 光学补偿：绕中心把 f 放大一点（参考图里 f 只占圆径 25%，小尺寸会糊）
  4. 把遮罩描成矢量轮廓（Moore 边界跟踪 + RDP 简化，闭环先切两段再简化）
  5. 位图与矢量都从这份轮廓渲染，保证两边同源：
       - 位图：超采样绘制黑圆 + 白 f，再降采样，边缘才脆
       - 矢量：直接写 SVG（圆用 circle 元素，f 用 path）
  6. 导出 icon.png / icon-256.png / icon.ico / favicon 全套

用法： python scripts/make-icons.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SRC = ASSETS / "icon-source.webp"

SS = 4                  # 超采样倍数
MASTER = 1024           # 主图边长
TILE = "#111110"        # 圆底色（暖偏移黑）
GLYPH = "#ffffff"
GLYPH_ZOOM = 1.15       # 光学补偿
TRACE_SIDE = 2048       # 描摹分辨率
TRACE_EPS = 0.6         # RDP 简化阈值（描摹坐标系内）
SMOOTH_WIN = 15         # 轮廓平滑窗口（奇数）
SMOOTH_PASS = 3         # 平滑遻数
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


# ------------------------------------------------------------ 参考图解析
def load_reference():
    """返回 (f 的软遮罩 L 图, 圆底色 RGB)"""
    im = Image.open(SRC).convert("RGB")
    w, h = im.size
    px = im.load()

    # 1) 圆底色 = 出现最多的高饱和颜色
    sat = Counter()
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            if max(r, g, b) - min(r, g, b) > 60:
                sat[(r // 8 * 8, g // 8 * 8, b // 8 * 8)] += 1
    if not sat:
        raise SystemExit("[错误] 参考图里找不到有饱和度的圆形底色")
    base = sat.most_common(1)[0][0]

    # 2) 圆的外接框
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - base[0]) < 70 and abs(g - base[1]) < 70 and abs(b - base[2]) < 70:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise SystemExit("[错误] 没找到圆底色像素")
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    side = max(x1 - x0, y1 - y0)
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    left = cx - side // 2
    top = cy - side // 2
    crop = im.crop((left, top, left + side, top + side))

    # 3) 双色投影 —— f 的软遮罩
    W = (255, 255, 255)
    dx = [W[i] - base[i] for i in range(3)]
    denom = sum(v * v for v in dx) or 1
    cw, ch = crop.size
    cpx = crop.load()
    mask = Image.new("L", (cw, ch), 0)
    mpx = mask.load()
    for y in range(ch):
        for x in range(cw):
            p = cpx[x, y]
            t = sum((p[i] - base[i]) * dx[i] for i in range(3)) / denom
            mpx[x, y] = 0 if t < 0 else (255 if t > 1 else int(t * 255))

    # 4) 圆外一律置零。不做这步，圆外的透明棋盘格会被当成白色，
    #    描摹出来的轮廓就变成整个圆而不是那个 f。
    inside = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(inside).ellipse([0, 0, cw - 1, ch - 1], fill=255)
    mask = Image.composite(mask, Image.new("L", (cw, ch), 0), inside)

    return mask, base


def zoom_glyph(mask: Image.Image, factor: float) -> Image.Image:
    """绕中心放大字形（形态不变，只调比例）"""
    s0 = mask.size[0]
    z = int(round(s0 * factor))
    zed = mask.resize((z, z), Image.LANCZOS)
    off = (s0 - z) // 2
    out = Image.new("L", (s0, s0), 0)
    out.paste(zed, (off, off))
    return out


# ------------------------------------------------------------ 轮廓描摹
def _rdp(pts, eps):
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]
    bx, by = pts[-1]
    idx, dmax = 0, 0.0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        num = abs((by - ay) * x - (bx - ax) * y + bx * ay - by * ax)
        den = ((by - ay) ** 2 + (bx - ax) ** 2) ** 0.5 or 1
        d = num / den
        if d > dmax:
            idx, dmax = i, d
    if dmax > eps:
        left = _rdp(pts[: idx + 1], eps)
        right = _rdp(pts[idx:], eps)
        return left[:-1] + right
    return [pts[0], pts[-1]]


def _simplify_closed(loop, eps):
    """闭环先切成两段开口折线再简化 —— 否则首尾重合会把整圈折没。"""
    pts = list(loop)
    if len(pts) > 2 and pts[0] == pts[-1]:
        pts.pop()
    if len(pts) < 4:
        return pts
    x0, y0 = pts[0]
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - x0) ** 2 + (pts[i][1] - y0) ** 2)
    if far == 0:
        return pts
    a = _rdp(pts[: far + 1], eps)
    b = _rdp(pts[far:] + [pts[0]], eps)
    return a[:-1] + b[:-1]


def _smooth_closed(pts, window, passes):
    """环形滑动平均 —— 去掉低分辨率源图带来的轮廓抖动。"""
    if window < 3 or len(pts) < window * 2:
        return pts
    half = window // 2
    cur = list(pts)
    for _ in range(passes):
        n = len(cur)
        out = []
        for i in range(n):
            sx = sy = 0.0
            for j in range(-half, half + 1):
                x, y = cur[(i + j) % n]
                sx += x
                sy += y
            out.append((sx / window, sy / window))
        cur = out
    return cur


def trace(mask: Image.Image, side: int, epsilon: float):
    """Moore 邻域边界跟踪 + RDP，返回轮廓点（坐标在 side×side 网格内）"""
    big = mask.resize((side, side), Image.LANCZOS).point(lambda v: 255 if v > 128 else 0)
    px = big.load()

    def solid(x, y):
        return 0 <= x < side and 0 <= y < side and px[x, y] > 0

    start = None
    for y in range(side):
        for x in range(side):
            if solid(x, y):
                start = (x, y)
                break
        if start:
            break
    if not start:
        raise SystemExit("[错误] 遮罩是空的")

    # 方向表：0=东 1=东南 2=南 3=西南 4=西 5=西北 6=北 7=东北
    nbr = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    contour = [start]
    cur = start
    back = 6            # 概念上从北侧进入
    for _ in range(side * side * 8):
        nxt = None
        for k in range(8):
            d = (back + 1 + k) % 8
            cand = (cur[0] + nbr[d][0], cur[1] + nbr[d][1])
            if solid(cand[0], cand[1]):
                nxt = cand
                back = (d + 4) % 8
                break
        if nxt is None:
            break
        contour.append(nxt)
        cur = nxt
        if cur == start and len(contour) > 8:
            break

    print(f"  原始轮廓点 {len(contour)}")
    smooth = _smooth_closed(contour, SMOOTH_WIN, SMOOTH_PASS)
    return _simplify_closed(smooth, epsilon)


def path_of(pts128) -> str:
    return " ".join(
        ("M" if i == 0 else "L") + f"{x:.2f} {y:.2f}" for i, (x, y) in enumerate(pts128)
    ) + " Z"


# ------------------------------------------------------------ 主流程
def main() -> int:
    if not SRC.exists():
        print(f"[错误] 缺少参考图：{SRC}")
        return 1

    print("解析参考图 …")
    mask, base = load_reference()
    print(f"  圆底色 = rgb{base}  遮罩尺寸 = {mask.size}")

    if GLYPH_ZOOM != 1.0:
        mask = zoom_glyph(mask, GLYPH_ZOOM)
        print(f"  光学补偿 x{GLYPH_ZOOM}")

    # --- 描摹矢量轮廓（位图与矢量都从它来，保证同源）---
    print("描摹矢量轮廓 …")
    pts = trace(mask, TRACE_SIDE, TRACE_EPS)
    k = 128.0 / TRACE_SIDE
    pts128 = [(p[0] * k, p[1] * k) for p in pts]
    print(f"  轮廓点 {len(pts)}")

    # --- 主图：超采样渲染轮廓 ---
    print("渲染主图 …")
    big = MASTER * SS
    sf = big / 128.0
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.ellipse([0, 0, big - 1, big - 1], fill=TILE)      # 圆内填充，四角留透明
    d.polygon([(x * sf, y * sf) for x, y in pts128], fill=GLYPH)
    master = tile.resize((MASTER, MASTER), Image.LANCZOS)

    master.save(ASSETS / "icon.png")
    print(f"  [ok] icon.png ({MASTER}x{MASTER})")
    master.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon-256.png")
    print("  [ok] icon-256.png")

    # --- ICO ---
    # 每个尺寸都从 1024 主图单独降采样（而不是先缩到 256 再缩），
    # 小尺寸的圆边与 f 笔画明显更干净，不再出现块状锯齿。
    frames = sorted(
        (master.resize((s, s), Image.LANCZOS) for s in ICO_SIZES),
        key=lambda f: f.size[0],
    )
    ico_top, ico_rest = frames[-1], frames[:-1]
    ico_top.save(ASSETS / "icon.ico", format="ICO", append_images=ico_rest)
    ico_top.save(ASSETS / "favicon.ico", format="ICO", append_images=ico_rest)
    print(f"  [ok] icon.ico / favicon.ico ({'/'.join(map(str, ICO_SIZES))})")

    for s in (16, 32, 48, 64):
        master.resize((s, s), Image.LANCZOS).save(ASSETS / f"favicon-{s}x{s}.png")
    master.resize((180, 180), Image.LANCZOS).save(ASSETS / "apple-touch-icon.png")
    print("  [ok] favicon-16/32/48/64.png · apple-touch-icon.png")

    # --- 矢量 ---
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" '
        'width="{w}" height="{w}" role="img" aria-label="fconv">\n'
        "  <title>fconv</title>\n"
        f'  <circle cx="64" cy="64" r="64" fill="{TILE}"/>\n'
        f'  <path fill="{GLYPH}" d="{path_of(pts128)}"/>\n'
        "</svg>\n"
    )
    (ASSETS / "icon.svg").write_text(svg.format(w=128), encoding="utf-8")
    (ASSETS / "favicon.svg").write_text(svg.format(w=32), encoding="utf-8")
    print("  [ok] icon.svg / favicon.svg")

    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
