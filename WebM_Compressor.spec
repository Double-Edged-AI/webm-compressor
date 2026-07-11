# -*- mode: python ; coding: utf-8 -*-
import os
import customtkinter
from PyInstaller.utils.hooks import collect_all

# Resolve customtkinter's data files from the active environment (portable —
# works on any machine instead of a hardcoded site-packages path).
CTK_PATH = os.path.dirname(customtkinter.__file__)

# tkinterdnd2 ships the native TkDnD Tcl extension as data — collect all of it.
tkdnd_datas, tkdnd_binaries, tkdnd_hidden = collect_all('tkinterdnd2')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=tkdnd_binaries,
    datas=[(CTK_PATH, 'customtkinter/'), ('assets/icon.ico', 'assets'), ('assets/icon_256.png', 'assets'), ('assets/fonts', 'assets/fonts')] + tkdnd_datas,
    hiddenimports=['comtypes', 'comtypes.client'] + tkdnd_hidden,
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
    name='WebM_Compressor',
    icon='assets/icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    name='WebM_Compressor',
)
