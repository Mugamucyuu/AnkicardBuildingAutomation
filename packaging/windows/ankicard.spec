"""Build only shipped code/assets, never local preferences, jobs or keys."""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parents[1]
datas = collect_data_files('webview')
datas += [(str(root / 'vocab_app' / name), 'vocab_app/' + name) for name in ('web', 'resources')]
datas += [(str(root / name), '.') for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md')]
datas += [(str(root / 'build/windows/THIRD_PARTY_LICENSES.txt'), '.')]
datas += [(str(root / 'packaging/windows/licenses'), 'licenses')]
a = Analysis([str(root / 'run_desktop.py')], pathex=[str(root)], datas=datas,
             hiddenimports=['webview.platforms.edgechromium', 'webview.platforms.winforms'],
             excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'tkinter', 'pytest', 'unittest'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Ankicard',
          debug=False, strip=False, upx=False, console=False,
          version=str(root / 'build/windows/version_info.txt'),
          icon=str(root / 'packaging/windows/ankicard.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Ankicard')
