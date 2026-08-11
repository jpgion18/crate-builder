# -*- mode: python ; coding: utf-8 -*-
# Build with: pyinstaller desktop_app.spec
# Produces dist/CrateBuilder (folder) on Windows/Linux, dist/CrateBuilder.app on macOS.
import sys

block_cipher = None

a = Analysis(
    ["desktop_app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("templates", "templates"),
        ("static", "static"),
        ("VERSION", "."),
    ],
    hiddenimports=[
        "mutagen",
        "rapidfuzz",
        "spotipy",
        "dotenv",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CrateBuilder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CrateBuilder",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="CrateBuilder.app",
        bundle_identifier="com.crate-builder.desktop",
    )
