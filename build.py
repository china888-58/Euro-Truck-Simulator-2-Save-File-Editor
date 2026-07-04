"""
ETS2 / ATS 存档编辑器 — PyInstaller 一键打包脚本
=====================================================
用法：
    python build.py            # 单文件 EXE（推荐）
    python build.py --onedir   # 单目录（启动更快）

打包产物：dist/ 下的 .exe 文件
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

# 应用元数据
APP_NAME = "EuroTruckSaveEditor"
ENTRY_SCRIPT = "main.py"
HIDDEN_IMPORTS = [
    "sii_parser",
    "bsii_parser",
    "editor",
    "Crypto",
    "Crypto.Cipher",
    "Crypto.Cipher.AES",
    "Crypto.Util.Padding",
]

# PyInstaller 共享参数
# 注意：PyInstaller 6+ 要求 --add-data 使用 = 语法
extra_args = []
if Path("app.ico").exists():
    extra_args += ["--icon=app.ico"]

COMMON_ARGS = [
    "--name", APP_NAME,
    "--clean",
    "--noconfirm",
    "--console",                   # 保留 console 以便看错误；如需 GUI-only 改为 --windowed
    # 隐藏 import（确保被 PyInstaller 收集）
    *[f"--hidden-import={m}" for m in HIDDEN_IMPORTS],
    # 图标（如存在则使用）
    *extra_args,
    # 主脚本（其余 .py 模块由 import 分析自动收集）
    ENTRY_SCRIPT,
]


def build_onefile() -> int:
    """单文件 EXE。"""
    args = COMMON_ARGS + ["--onefile"]
    return _run(args)


def build_onedir() -> int:
    """单目录。"""
    args = COMMON_ARGS + ["--onedir"]
    return _run(args)


def _run(args: list) -> int:
    print("=" * 60)
    print(f"打包命令：pyinstaller {' '.join(args)}")
    print("=" * 60)
    try:
        return subprocess.call([sys.executable, "-m", "PyInstaller"] + args)
    except FileNotFoundError:
        print("错误：未找到 PyInstaller。请运行： pip install pyinstaller")
        return 1


def cleanup() -> None:
    """清理临时构建目录。"""
    for d in ("build", "__pycache__"):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            print(f"已清理 {d}/")
    spec = f"{APP_NAME}.spec"
    if os.path.isfile(spec):
        os.remove(spec)
        print(f"已清理 {spec}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--onefile"
    if mode == "--clean":
        cleanup()
        return 0
    if mode == "--onedir":
        rc = build_onedir()
    elif mode in ("--onefile", ""):
        rc = build_onefile()
    else:
        print(f"未知参数：{mode}")
        print("用法：python build.py [--onefile|--onedir|--clean]")
        return 1
    if rc == 0:
        print("\n打包成功！产物位于 dist/ 目录下。")
        dist = Path("dist")
        if dist.exists():
            print("\n产物清单：")
            for p in dist.iterdir():
                print(f"  - {p}")
    else:
        print(f"\n打包失败，退出码 {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
