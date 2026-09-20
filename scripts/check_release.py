"""开源前自检（发布守卫）。

一条命令把「能不能公开发布」这件事体检一遍：版本号是否对齐、
有没有把本机路径/密钥写进仓库、文档里的相对链接是否可达、
启动器编码对不对、图标资源是否齐全、`.gitignore` 有没有漏。

用法::

    python scripts/check_release.py          # 逐项检查，有问题退出码 1
    python scripts/check_release.py --strict # 把「软告警」也当失败（CI 用）

不依赖第三方包；Pillow 装了会额外校验 ICO 内含的尺寸，没装就跳过。
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Windows 控制台（cp1252 / cp936 等）默认编不出 UTF-8 中文，直接抛
# UnicodeEncodeError 把脚本打断（GitHub Actions 的 windows-latest 实测踩到）。
# 统一把输出流改成 UTF-8，管道重定向下同样生效。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - 非文本流时跳过
        pass

SKIP_DIRS = {
    ".git", "__pycache__", ".pytest_cache", "node_modules",
    "uploads", "dist-portable", "build", "dist", "_work", "_smoke",
}
TEXT_EXT = {".py", ".md", ".txt", ".toml", ".html", ".bat", ".vbs", ".yml", ".yaml", ".json", ".cfg"}

# 文档里会出现的「示例路径」，不算本机泄漏
PATH_ALLOWLIST = (
    r"D:\Tools\audio-extractor",
    r"C:\Users\me\report.md",
)

# 文档里作为「示例 / 历史文件名」出现的名字，本就不该存在于仓库
EXAMPLE_MENTIONS = frozenset({
    "x.png",           # 上传文件名净化的举例（../../x.png → x.png）
    "run_fconv.py",    # CHANGELOG 里提到的废弃旧文件名
    "app-icon.ico",    # 【音频提取器】项目里的图标路径（对照文档里引用）
})

REQUIRED_FILES = (
    "README.md", "README.txt", "README.en.md", "LICENSE", "CHANGELOG.md",
    "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md", "RELEASE.md",
    "THIRD-PARTY-NOTICES.txt", "pyproject.toml", "requirements.txt",
    "requirements-dev.txt", ".gitignore", ".editorconfig", ".gitattributes",
    "assets/icon.ico", "assets/icon.png", "assets/icon.svg", "assets/favicon.ico",
    "scripts/make_launchers.py", "scripts/make-icons.py", "scripts/build_vbs.py",
    ".github/workflows/ci.yml", ".github/ISSUE_TEMPLATE/bug_report.yml",
)

GITIGNORE_MUST_COVER = (
    "logs/", "src/uploads/", "dist-portable/", ".pytest_cache/",
    "__pycache__/", ".env",
)

LAUNCHERS = (
    "启动fconv.bat", "启动fconv-最小化.bat", "启动fconv.vbs",
    "停止fconv.bat", "安装到桌面.bat", "下载最新版.bat",
    "build-portable.bat", "start.bat", "README.txt",
)

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
ABS_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9/])[A-Za-z]:[\\/](?:Users|AutoClaw|Tools)[\\/][^\s\"'`),)]*"
)

results: list[tuple[bool, bool, str, str]] = []  # (ok, hard, 项目, 详情)


def record(ok: bool, hard: bool, title: str, detail: str = "") -> None:
    results.append((ok, hard, title, detail))


def walk_text_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() in TEXT_EXT or name in LAUNCHERS:
                yield path


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return io.open(path, encoding=encoding).read()
        except (UnicodeDecodeError, LookupError):
            continue
    return ""


# ------------------------------------------------------------------ 各项检查
def check_required_files() -> None:
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).exists()]
    record(not missing, True, "必需文件齐全", "缺少：" + ", ".join(missing) if missing else f"{len(REQUIRED_FILES)} 项全部存在")


def check_version_consistency() -> None:
    init_text = read_text(ROOT / "src/fconv/__init__.py")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    version = m.group(1) if m else None
    if not version:
        record(False, True, "版本号唯一来源可读", "src/fconv/__init__.py 里没找到 __version__")
        return

    pyproject = read_text(ROOT / "pyproject.toml")
    m2 = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    pv = m2.group(1) if m2 else None
    record(pv == version, True, "pyproject 版本与 __init__ 一致", f"__init__={version} pyproject={pv}")

    changelog = read_text(ROOT / "CHANGELOG.md")
    record(
        f"[{version}]" in changelog or f"v{version}" in changelog,
        True,
        "CHANGELOG 收录当前版本",
        f"查 [{version}] / v{version}",
    )

    index_html = read_text(ROOT / "src/web/index.html")
    record(
        version in index_html,
        False,
        "界面静态回退版本号同步",
        "index.html 里应有同样的版本号（运行时会被 /api/health 覆盖）",
    )

    launcher = ROOT / "下载最新版.bat"
    if launcher.exists():
        text = read_text(launcher)
        hard_coded = re.search(r'set\s+"VER=\d+\.\d+\.\d+"', text)
        record(
            hard_coded is None,
            False,
            "下载器不再写死版本号",
            "已改为运行时读 pyproject.toml" if hard_coded is None else f"发现写死：{hard_coded.group(0)}",
        )


def check_secrets_and_paths() -> None:
    secret_hits: list[str] = []
    path_hits: list[str] = []
    for path in walk_text_files():
        text = read_text(path)
        rel = path.relative_to(ROOT)
        for pattern in SECRET_PATTERNS:
            for hit in pattern.findall(text):
                secret_hits.append(f"{rel}: {hit[:40]}")
        for hit in ABS_PATH_PATTERN.findall(text):
            if any(allowed in hit for allowed in PATH_ALLOWLIST):
                continue
            path_hits.append(f"{rel}: {hit[:70]}")
    record(not secret_hits, True, "无密钥 / 令牌残留", "; ".join(secret_hits[:5]) or "干净")
    record(not path_hits, True, "无本机绝对路径", "; ".join(path_hits[:5]) or "干净")


def _strip_code_fences(text: str) -> str:
    """去掉 ``` 围栏代码块 —— 里面的路径是 CLI 示例，不是文档引用。"""
    return re.sub(r"```.*?```", "", text, flags=re.S)


def _mention_exists(name: str, doc_dir: Path, repo_suffixes: set[str]) -> bool:
    """名字能否解析到真实文件：相对文档目录 / 相对仓库根 / 仓库里的某个后缀。"""
    if not name or name.startswith("../") or name.startswith("/"):
        return True  # 跨出仓库的相对路径与绝对路径不归本检查管
    candidates = [doc_dir / name, ROOT / name]
    if any(c.exists() for c in candidates):
        return True
    cleaned = name.lstrip("./").replace("\\", "/")
    return any(suffix.endswith("/" + cleaned) for suffix in repo_suffixes)


def check_doc_links() -> None:
    broken: list[str] = []
    link_re = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
    # 文档里直接用反引号写文件名的（例如 docs 索引表），也顺手查一下
    name_re = re.compile(r"`([A-Za-z0-9_\-./\u4e00-\u9fff]+\.(?:md|txt|png|ico|svg|py|bat|vbs))`")

    repo_suffixes = set()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            repo_suffixes.add(str((Path(dirpath) / name).relative_to(ROOT)).replace("\\", "/"))

    for path in walk_text_files():
        if path.suffix.lower() != ".md":
            continue
        text = _strip_code_fences(read_text(path))
        rel = path.relative_to(ROOT)
        for target in link_re.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean = target.split("#")[0]
            if clean and not (path.parent / clean).resolve().exists():
                broken.append(f"{rel} -> {target}")
        for name in name_re.findall(text):
            if Path(name).name in EXAMPLE_MENTIONS:
                continue
            if not _mention_exists(name, path.parent, repo_suffixes):
                broken.append(f"{rel} 提到 {name}（找不到这个文件）")
    record(not broken, True, "文档内部链接可达", "; ".join(broken[:6]) or "全部可达")


def check_python_syntax() -> None:
    bad: list[str] = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = Path(dirpath) / name
            count += 1
            try:
                ast.parse(read_text(path), filename=str(path))
            except SyntaxError as exc:
                bad.append(f"{path.relative_to(ROOT)}:{exc.lineno} {exc.msg}")
    record(not bad, True, "Python 语法检查", "; ".join(bad[:5]) or f"{count} 个文件全部通过")


def check_gitignore() -> None:
    text = read_text(ROOT / ".gitignore")
    missing = [item for item in GITIGNORE_MUST_COVER if item not in text]
    record(not missing, True, ".gitignore 覆盖本机产物", "缺少：" + ", ".join(missing) if missing else f"{len(GITIGNORE_MUST_COVER)} 项已覆盖")


def check_launcher_encoding() -> None:
    bad: list[str] = []
    for name in LAUNCHERS:
        path = ROOT / name
        if not path.exists():
            bad.append(f"{name} 不存在")
            continue
        raw = path.read_bytes()
        try:
            raw.decode("gbk")
        except UnicodeDecodeError:
            bad.append(f"{name} 不是 GBK")
            continue
        if b"\r\n" not in raw:
            bad.append(f"{name} 不是 CRLF")
    record(not bad, True, "启动器编码（GBK + CRLF）", "; ".join(bad[:5]) or f"{len(LAUNCHERS)} 个文件全部合规")


def check_icons() -> None:
    ico = ROOT / "assets/icon.ico"
    if not ico.exists():
        record(False, True, "图标资源", "assets/icon.ico 不存在")
        return
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - 取决于环境
        record(True, False, "图标尺寸校验", "未安装 Pillow，跳过尺寸校验")
        return
    with Image.open(ico) as image:
        sizes = {size[0] for size in image.ico.sizes()}
    need = {16, 32, 48, 256}
    record(need <= sizes, True, "ICO 含常用尺寸", f"实含 {sorted(sizes)}")

    for name in ("favicon.ico", "icon.png", "icon-256.png", "favicon-16x16.png",
                 "favicon-32x32.png", "apple-touch-icon.png", "icon.svg", "favicon.svg"):
        if not (ROOT / "assets" / name).exists():
            record(False, True, "图标资源齐全", f"缺少 assets/{name}")
            return
    record(True, True, "图标资源齐全", "ico / png / svg 全尺寸齐备")


def check_no_local_artifacts_tracked() -> None:
    """本机产物可以存在于工作区，但不能已被 git 跟踪。"""
    git_dir = ROOT / ".git"
    if not git_dir.exists():
        record(True, False, "本机产物未入库", "非 git 工作区，跳过")
        return
    import subprocess

    try:
        listed = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=30
        ).stdout.splitlines()
    except Exception as exc:  # noqa: BLE001
        record(True, False, "本机产物未入库", f"git 不可用（{exc}），跳过")
        return
    forbidden = [
        line for line in listed
        if line.startswith(("logs/", "src/uploads/", "dist-portable/", ".pytest_cache/"))
        or line.endswith(("smoke_results.json", "benchmark_results.json"))
    ]
    record(not forbidden, True, "本机产物未入库", "; ".join(forbidden[:5]) or f"{len(listed)} 个已跟踪文件全部合规")


def main() -> int:
    parser = argparse.ArgumentParser(description="fconv 发布前自检")
    parser.add_argument("--strict", action="store_true", help="软告警也按失败处理（CI 用）")
    args = parser.parse_args()

    print("=" * 72)
    print("fconv 发布前自检")
    print("=" * 72)

    check_required_files()
    check_version_consistency()
    check_secrets_and_paths()
    check_doc_links()
    check_python_syntax()
    check_gitignore()
    check_launcher_encoding()
    check_icons()
    check_no_local_artifacts_tracked()

    hard_fail = 0
    soft_fail = 0
    for ok, hard, title, detail in results:
        mark = "PASS" if ok else ("FAIL" if hard else "WARN")
        if not ok:
            if hard:
                hard_fail += 1
            else:
                soft_fail += 1
        print(f"  [{mark}] {title}")
        if detail:
            print(f"         {detail}")

    print("-" * 72)
    print(f"通过 {sum(1 for r in results if r[0])} / 硬失败 {hard_fail} / 软告警 {soft_fail}")
    if hard_fail or (args.strict and soft_fail):
        print("结论：还不能发布，请先修掉上面的 FAIL/WARN。")
        return 1
    print("结论：可以发布。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
