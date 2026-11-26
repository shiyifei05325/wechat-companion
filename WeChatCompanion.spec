# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['mss.windows', 'pyautogui']
hiddenimports += collect_submodules('wechat_companion')
hiddenimports += collect_submodules('pyautogui')
hiddenimports += collect_submodules('pygetwindow')
hiddenimports += collect_submodules('requests')
# 全局热键 / OCR 及其 winrt 后端（部分模块为动态导入，需显式收集）
hiddenimports += collect_submodules('pynput')
hiddenimports += collect_submodules('winocr')
hiddenimports += collect_submodules('winrt')


a = Analysis(
    ['launcher.py'],
    pathex=['src'],
    binaries=[],
    datas=[('control', 'control'), ('assets', 'assets')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WeChatCompanion',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WeChatCompanion',
)
