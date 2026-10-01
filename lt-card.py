#!/usr/bin/env python3
"""生成 LeetCode 题号卡片。

用法：
    python3 lt-card.py <难度> <题号> [-o 输出文件] [-s 倍率]

    python3 lt-card.py medium 1190
    python3 lt-card.py 中等 1190 -o /tmp/1190.png
    python3 lt-card.py easy 1 -s 2          # 输出 2400x1200

难度可用 easy/medium/hard，也可用 简单/中等/困难（大小写随意）。
输出默认写在当前目录：leetcode-<题号>-<难度>.png

**不带参数直接运行就进入交互式提问**，方便 IDE 里点运行三角（那边不会传参数）：

    $ python3 lt-card.py
    LeetCode 卡片生成器 —— 回车确认，输入 q 退出

    难度 (easy / medium / hard) > medium
    题号 (例如 1190) > 1190
    medium #1190 -> /path/leetcode-1190-medium.png

两个参数只要给了一个，另一个就会问。都给了就一个都不问，保持可管道、可批处理。

实现说明
--------
底图直接复用同目录的 {easy,medium,hard}_card.png（Logo + 难度胶囊已画好），
只把题号用 Hepta Slab Light 叠到中间的空白区。

底图现在是 1200x600（2:1），中间 1024x564 那块是原始画面，四周 88px / 18px 是
后来补的白边（见 CONTENT_* 常量）。题号要贴在原始画面里，所以位置按
"内容区偏移 + 内容区内的标定坐标" 算，不能直接拿底图宽度去缩放。

内容区内的坐标是这样标定出来的：拿 示例1190.png / 示例1614.png 反推 ——
把 "1190"、"1614" 用这个字体反复渲染、和示例做 RMSE 比对，最优解是
1024x564 里字号 206.8、墨迹左上角落在 (289, 262.5)，且是左对齐
（居中对齐的误差要大 4 倍）。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent

FONT = HERE / "Hepta Slab Light.ttf"

# 底图尺寸，以及原始画面（内容区）在底图里的位置，见模块 docstring
TEMPLATE_W = 1200
TEMPLATE_H = 600
CONTENT_X = 88.0
CONTENT_Y = 18.0

# 内容区内的标定值，基准是原始画面 1024x564
REF_W = 1024.0
REF_POINTSIZE = 206.8
REF_INK_LEFT = 289.0
REF_INK_TOP = 262.5

TEMPLATES = {
    "easy": "easy_card.png",
    "medium": "medium_card.png",
    "hard": "hard_card.png",
}

# 难度别名 -> 规范名
ALIASES = {
    "简单": "easy", "容易": "easy", "e": "easy", "1": "easy",
    "中等": "medium", "中": "medium", "m": "medium", "2": "medium",
    "困难": "hard", "难": "hard", "h": "hard", "3": "hard",
}


def die(msg: str) -> "None":
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def magick(args: list[str]) -> str:
    """跑一条 magick 命令，返回 stdout。"""
    proc = subprocess.run(
        ["magick", *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        die(f"magick 执行失败：{' '.join(args)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


DIFF_HINT = "可用：easy / medium / hard（或 简单 / 中等 / 困难）"

USAGE = "python3 lt-card.py <难度> <题号>"


def normalize_difficulty(raw: str) -> str | None:
    """认得出就返回规范名，认不出返回 None（交给调用方决定是报错还是重问）。"""
    key = raw.strip().lower()
    key = ALIASES.get(key, key)
    return key if key in TEMPLATES else None


def normalize_number(raw: str) -> str | None:
    num = raw.strip().lstrip("#")
    if not num.isdigit() or int(num) <= 0:
        return None
    return str(int(num))


def resolve_difficulty(raw: str) -> str:
    key = normalize_difficulty(raw)
    if key is None:
        die(f"认不出的难度 {raw!r}；{DIFF_HINT}")
    return key


def parse_number(raw: str) -> str:
    num = normalize_number(raw)
    if num is None:
        die(f"题号得是正整数，收到 {raw!r}")
    return num


def ink_bbox(path: Path) -> tuple[int, int, int, int]:
    """返回图片非透明区域的 (x, y, w, h)；整张全透明时退出。"""
    try:
        geom = magick([str(path), "-format", "%@", "info:"])
    except SystemExit:
        die("题号渲染出来是空白的，可能是字体文件损坏")
    # 形如 456x161+13+48
    size, x, y = geom.split("+")
    w, h = size.split("x")
    return int(x), int(y), int(w), int(h)


def build(number: str, difficulty: str, scale: float, out: Path, center: bool) -> None:
    template = HERE / TEMPLATES[difficulty]

    for path in (FONT, template):
        if not path.is_file():
            die(f"缺少文件：{path}")

    tw, th = magick([str(template), "-format", "%w %h", "info:"]).split()
    if (int(tw), int(th)) != (TEMPLATE_W, TEMPLATE_H):
        die(
            f"{template.name} 是 {tw}x{th}，脚本按 {TEMPLATE_W}x{TEMPLATE_H} 标定的。"
            " 换了底图的话，改一下 TEMPLATE_* / CONTENT_* 常量。"
        )

    # 题号贴在内容区里，位置 = 内容区偏移 + 内容区内的标定坐标
    ink_left = CONTENT_X + REF_INK_LEFT
    ink_top = CONTENT_Y + REF_INK_TOP

    # 1) 透明底上把题号画出来（按标定尺寸，不做缩放）
    text_png = out.with_name(out.name + ".num.tmp.png")
    magick([
        "-background", "none",
        "-fill", "black",
        "-density", "72",
        "-font", str(FONT),
        "-pointsize", f"{REF_POINTSIZE:.3f}",
        f"label:{number}",
        str(text_png),
    ])

    # 2) 量出墨迹左上角，反推需要贴到哪儿
    ix, iy, iw, _ = ink_bbox(text_png)
    dy = round(ink_top) - iy
    if center:
        # 示例里的 4 位数是左对齐的，位数少的时候左对齐会显得偏，这时用 -c 居中
        dx = round(CONTENT_X + (REF_W - iw) / 2) - ix
    else:
        dx = round(ink_left) - ix

    # 3) 叠到底图上
    magick([
        str(template),
        "(", str(text_png), "-geometry", f"+{dx}+{dy}", ")",
        "-composite",
        str(out),
    ])
    text_png.unlink(missing_ok=True)

    # 4) 需要的话整体缩放
    if scale != 1.0:
        magick([str(out), "-filter", "Lanczos", "-resize", f"{scale * 100:g}%", str(out)])


def ask(prompt: str, normalize: Callable[[str], str | None], hint: str) -> str:
    """交互式问一个值，认不出就重问；Ctrl-C / Ctrl-D / 输入 q 都能干净退出。"""
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            # IDE 的运行按钮有时给的是个空的 stdin，别丢个 traceback 出去
            print()
            print(f"没读到输入。要不直接用命令行参数：{USAGE}", file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            print()
            sys.exit(130)

        if raw.strip().lower() in ("q", "quit", "exit", "退出"):
            print("已取消")
            sys.exit(0)

        value = normalize(raw)
        if value is not None:
            return value

        print(f"  {hint}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="生成 LeetCode 题号卡片（不给参数就直接问）",
        usage="lt-card.py [难度] [题号] [-o 输出] [-s 倍率] [-c]",
    )
    ap.add_argument(
        "difficulty", nargs="?",
        help="easy / medium / hard（或 简单 / 中等 / 困难）；不给就交互式问",
    )
    ap.add_argument("number", nargs="?", help="题号，例如 1190；不给就交互式问")
    ap.add_argument("-o", "--out", help="输出文件，默认 ./leetcode-<题号>-<难度>.png")
    ap.add_argument(
        "-s", "--scale", type=float, default=1.0,
        help=f"缩放倍率，默认 1.0（原始 {TEMPLATE_W}x{TEMPLATE_H}）",
    )
    ap.add_argument(
        "-c", "--center", action="store_true",
        help="题号水平居中（位数少时好看；示例里的 4 位数是左对齐的）",
    )
    args = ap.parse_args()

    if not shutil.which("magick"):
        die("找不到 magick 命令，请先装 ImageMagick 7")

    if args.scale <= 0:
        die("倍率得是正数")

    # 少哪个就问哪个，两个都给了就完全不问（保持脚本可管道、可批处理）
    if args.difficulty is None or args.number is None:
        print("LeetCode 卡片生成器（输入 q 退出）")
        print()

    difficulty = (
        ask("难度 (easy / medium / hard) > ", normalize_difficulty, DIFF_HINT)
        if args.difficulty is None
        else resolve_difficulty(args.difficulty)
    )
    number = (
        ask("题号 (例如 1190) > ", normalize_number, "题号得是正整数，例如 1190")
        if args.number is None
        else parse_number(args.number)
    )

    out = Path(args.out).expanduser() if args.out else Path.cwd() / (
        f"leetcode-{number}-{difficulty}.png"
    )
    out = out.resolve()

    build(number, difficulty, args.scale, out, args.center)
    print(f"{difficulty:<6} #{number} -> {out}")


if __name__ == "__main__":
    main()
