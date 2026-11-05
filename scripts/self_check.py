"""First-run self-check: verify dependencies and give actionable next steps for non-technical users."""
from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path

def check_python():
    ok = sys.version_info >= (3, 10)
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return ok, f"Python {ver}", "" if ok else "安装 Python 3.10+：https://www.python.org/downloads/"

def check_node():
    node = shutil.which("node")
    if not node: return False, "未找到", "安装 Node.js 20+：https://nodejs.org/ 或联系 IT"
    try:
        ver = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=15).stdout.strip()
        major = int(ver.lstrip("v").split(".")[0])
        return (major >= 20), f"Node {ver}", "" if major >= 20 else f"升级到 Node 20+，当前 {ver}"
    except Exception: return False, "检测失败", "确认 node --version 可正常执行"

def check_python_deps():
    missing = []
    for mod, pip in [("openpyxl","openpyxl"),("xlrd","xlrd"),("PIL","Pillow"),("requests","requests")]:
        try: __import__(mod)
        except ImportError: missing.append(pip)
    if missing: return False, f"缺少: {', '.join(missing)}", f"运行: pip install {' '.join(missing)}"
    return True, "openpyxl, xlrd, Pillow, requests 已安装", ""

def check_webcli():
    ctx = Path(__file__).resolve().parents[1] / "scripts" / "browser_context.json"
    if ctx.exists(): return True, "browser_context.json 已配置（本机已跑过任务）", ""
    cands = [Path(os.environ.get("USERPROFILE","")) / ".o2" / "npm" / "node_modules" / "@jd" / "webcli"]
    if any(c.exists() for c in cands if c): return True, "WebCLI 已安装（首次任务时自动配置）", ""
    return False, "WebCLI 未安装", "运行: o2 install webcli"

def check_output_dir():
    root = Path.home() / "Desktop" / "京东链接搬运"
    try:
        root.parent.mkdir(parents=True, exist_ok=True)
        if os.access(str(root.parent), os.W_OK): return True, f"输出目录可用: {root}", ""
        return False, f"无写入权限: {root}", "检查桌面目录权限，或用 --root 指定其他目录"
    except Exception as e: return False, f"创建失败: {e}", "检查磁盘空间和目录权限"

def main():
    checks = [("Python 3.10+", check_python),("Node.js 20+", check_node),("Python 依赖", check_python_deps),
              ("WebCLI 浏览器桥接", check_webcli),("输出目录权限", check_output_dir)]
    all_ok = True
    print("=== jd-hot-link-collector 自检 ===\n")
    for name, fn in checks:
        ok, detail, fix = fn()
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
        if not ok:
            all_ok = False
            if fix: print(f"    → 下一步: {fix}")
    print()
    if all_ok:
        print("全部通过！把商品清单 Excel 发给 JoyCode，说「用 jd-hot-link-collector 采集」即可。")
    else:
        print("有缺项，按上面「下一步」处理后重新运行: python -X utf8 scripts/self_check.py")
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
