@echo off
REM ============================================================
REM  ETS2 / ATS 存档编辑器 — Windows 一键打包脚本
REM  双击运行,或在命令行执行: build_exe.bat
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  欧卡/美卡 存档编辑器 EXE 打包
echo ============================================
echo.

REM 检查 Python
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python。请先安装 Python 3.8+ 并加入 PATH。
    pause
    exit /b 1
)

REM 安装 PyInstaller 和 pycryptodome（用于解密 ETS2 1.5+ 加密存档）
echo [1/3] 安装依赖（PyInstaller + pycryptodome）...
python -m pip install --upgrade pyinstaller pycryptodome || (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

REM 打包
echo.
echo [2/3] 开始打包...
python build.py --onefile || (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo [3/3] 完成！
echo   EXE 文件位于: dist\EuroTruckSaveEditor.exe
echo.
echo 将该 EXE 复制到任意位置运行即可。
echo 建议同时将您的 .sii 存档放在容易找到的位置。
echo.
pause
