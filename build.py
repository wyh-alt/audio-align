"""
用于将应用打包为exe的脚本
使用PyInstaller打包
"""

import os
import sys
import subprocess
import shutil

def build_exe():
    print("开始打包应用程序...")
    
    # 检查是否安装了PyInstaller
    try:
        import PyInstaller
        print("PyInstaller已安装")
    except ImportError:
        print("安装PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller安装完成")
    
    # 确保所需依赖已安装
    print("检查并安装依赖...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    
    # 为librosa和soundfile等音频处理库添加特殊处理
    # PyInstaller可能无法自动检测到这些库的所有依赖
    hidden_imports = [
        "--hidden-import=librosa",
        "--hidden-import=librosa.core",
        "--hidden-import=librosa.feature",
        "--hidden-import=librosa.effects",
        "--hidden-import=librosa.util",
        "--hidden-import=soundfile",
        "--hidden-import=scipy.signal",
        "--hidden-import=numpy",
        "--hidden-import=PyQt5",
        "--hidden-import=PyQt5.QtCore",
        "--hidden-import=PyQt5.QtWidgets",
        "--hidden-import=PyQt5.QtGui"
    ]
    
    # 构建命令行参数
    cmd = [
        "pyinstaller",
        "--name=原唱伴奏对齐工具",
        "--windowed",  # 不显示控制台窗口
        "--onefile",   # 打包为单个exe文件
        "--noconfirm", # 覆盖已存在的构建文件夹
        "--clean",     # 清理PyInstaller缓存
    ]
    
    # 添加图标(如果存在)
    if os.path.exists("icon.ico"):
        cmd.append("--icon=icon.ico")
    
    # 添加隐藏导入
    cmd.extend(hidden_imports)
    
    # 添加数据文件
    if os.path.exists("README.md"):
        cmd.append("--add-data=README.md;.")
    
    # 添加入口脚本
    cmd.append("main.py")
    
    # 执行打包命令
    print("正在打包，请稍等...")
    print("命令:", " ".join(cmd))
    subprocess.check_call(cmd)
    
    print("\n打包完成！")
    print("可执行文件位于 dist/原唱伴奏对齐工具.exe")
    print("双击即可运行程序")
    
    # 创建一个简单的批处理文件以便于运行
    create_launcher()

def create_launcher():
    """创建一个批处理文件作为启动器"""
    launcher_path = "运行原唱伴奏对齐工具.bat"
    with open(launcher_path, "w", encoding="utf-8") as f:
        f.write('@echo off\n')
        f.write('echo 正在启动原唱伴奏对齐工具...\n')
        f.write('start "" "dist\\原唱伴奏对齐工具.exe"\n')
    
    print(f"创建启动器: {launcher_path}")

if __name__ == "__main__":
    build_exe() 