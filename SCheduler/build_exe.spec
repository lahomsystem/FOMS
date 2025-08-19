# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

block_cipher = None
script_dir = Path.cwd()

# 추가할 데이터 파일들
added_files = [
    (str(script_dir / 'main_app.py'), '.'),
    (str(script_dir / 'address_converter.py'), '.'),
    (str(script_dir / 'map_generator.py'), '.'),
    (str(script_dir / 'address_learning.py'), '.'),
    (str(script_dir / 'address_editor.py'), '.'),
    (str(script_dir / 'web_address_learner.py'), '.'),
    (str(script_dir / 'config.py'), '.'),
    (str(script_dir / 'requirements.txt'), '.'),
]

# JSON 파일이 있으면 추가
json_file = script_dir / 'address_learning_data.json'
if json_file.exists():
    added_files.append((str(json_file), '.'))

a = Analysis(
    ['launcher.py'],
    pathex=[str(script_dir)],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'streamlit',
        'pandas',
        'folium',
        'streamlit_folium',
        'requests',
        'openpyxl',
        'xlsxwriter',
        'pyarrow',
        'altair',
        'plotly',
        'matplotlib',
        'numpy',
        'scikit-learn',
        'beautifulsoup4',
        'lxml',
        'html.parser'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='주소변환시스템',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None
) 