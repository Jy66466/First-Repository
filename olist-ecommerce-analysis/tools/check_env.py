# -*- coding: utf-8 -*-
"""
check_env.py —— Python 环境自检（阶段2 第一步，本地运行，不联网、不改环境）

用法（在仓库根目录打开终端后执行）：
    python 阶段2_交付物/check_env.py
    # 或把本文件放到仓库 tools/ 下：
    python tools/check_env.py

输出：
    1) Python 版本 / 位数 / 操作系统 / 虚拟环境状态
    2) 依赖库是否已安装 + 版本号
    3) 缺失清单与下一步提示

说明：
    版本号通过 importlib.metadata 读取已安装包的元数据，不会真正 import 重型库，
    因此运行很快，也不会因为某个库初始化失败而中断检查。
"""

from __future__ import annotations

import os
import platform
import struct
import sys
from importlib import metadata

# Windows 控制台默认可能是 GBK，中文输出会报 UnicodeEncodeError，这里强制切 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 需要检查的包：import 名 -> pip 包名（大多数两者同名，个别不同）
REQUIRED = [
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("matplotlib", "matplotlib"),
    ("seaborn", "seaborn"),
    ("plotly", "plotly"),
    ("kaleido", "kaleido"),
    ("streamlit", "streamlit"),
    ("statsmodels", "statsmodels"),
    ("openpyxl", "openpyxl"),
    ("kaggle", "kaggle"),
]


def get_version(dist_name: str):
    """读取已安装包版本；未安装返回 None。"""
    try:
        return metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        return None
    except Exception as exc:  # 元数据损坏等极端情况
        return f"读取失败({exc.__class__.__name__})"


def main() -> int:
    print("=" * 62)
    print("Python 环境自检")
    print("=" * 62)

    # ---------- 1. 解释器与系统 ----------
    print(f"Python 版本 : {platform.python_version()}  (实现: {platform.python_implementation()})")
    print(f"位数        : {struct.calcsize('P') * 8} bit / {platform.architecture()[0]}")
    print(f"可执行文件  : {sys.executable}")
    print(f"操作系统    : {platform.system()} {platform.release()}  ({platform.version()})")
    print(f"虚拟环境    : {'是' if sys.prefix != getattr(sys, 'base_prefix', sys.prefix) else '否（直接用了系统 Python）'}")
    print(f"工作目录    : {os.getcwd()}")

    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 9):
        print("\n[警告] Python 版本低于 3.9，pandas 2.x / streamlit 新版本可能装不上，建议升级到 3.10 或 3.11。")

    # ---------- 2. 依赖库 ----------
    print("\n" + "-" * 62)
    print(f"{'库名':<16}{'状态':<10}版本")
    print("-" * 62)

    missing = []
    for import_name, dist_name in REQUIRED:
        version = get_version(dist_name)
        if version is None:
            print(f"{import_name:<16}{'未安装':<10}-")
            missing.append(dist_name)
        else:
            print(f"{import_name:<16}{'已安装':<10}{version}")

    # ---------- 3. 结论与下一步 ----------
    print("-" * 62)
    if missing:
        print(f"\n共 {len(missing)} 个库缺失：{', '.join(missing)}")
        print("安装命令（先激活虚拟环境）：")
        print("    pip install -r requirements.txt")
        print("或单独安装：")
        print(f"    pip install {' '.join(missing)}")
    else:
        print("\n全部依赖已就绪。")

    print("\n提示：kaggle 仅用于下载数据集，与画图无关；缺它不影响分析，只影响 01_load.py 的自动下载。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
