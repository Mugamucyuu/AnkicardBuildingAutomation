"""Generate version resources and preserve licenses for frozen dependencies."""
from importlib.metadata import distribution
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocab_app import __version__


def main():
    target = ROOT / 'build/windows'
    target.mkdir(parents=True, exist_ok=True)
    version = tuple(int(x) for x in __version__.split('.')) + (0,)
    resource = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={version!r}, prodvers={version!r}, mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Mugamucyuu'),
    StringStruct('FileDescription', 'Ankicard Building Automation'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('ProductName', 'Ankicard Building Automation'),
    StringStruct('ProductVersion', '{__version__}'),
    StringStruct('OriginalFilename', 'Ankicard.exe'),
    StringStruct('LegalCopyright', 'MIT; see THIRD_PARTY_NOTICES.md')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
'''
    (target / 'version_info.txt').write_text(resource, encoding='utf-8')
    notices = ['Third-party licenses for the Windows frozen application',
               'See THIRD_PARTY_NOTICES.md for data and WebView2 notices.']
    for name in ('pywebview', 'pythonnet', 'clr_loader', 'cffi', 'pycparser',
                 'bottle', 'proxy_tools', 'typing_extensions', 'pyinstaller'):
        dist = distribution(name)
        notices.append(f'\n=== {name} {dist.version} ===\n')
        licenses = [f for f in dist.files or [] if
                    ('license' in f.name.lower() or 'copying' in f.name.lower()) and
                    not f.name.endswith('.py')]
        if not licenses:
            fallback = ROOT / 'packaging/windows/licenses' / (name + '.txt')
            if not fallback.exists():
                raise RuntimeError(f'Missing license text for {name}')
            notices.append(fallback.read_text(encoding='utf-8'))
        for item in licenses:
            notices.append(dist.locate_file(item).read_text(encoding='utf-8', errors='replace'))
    # CPython redistributors must retain the PSF license, too.
    candidates = [Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE_PYTHON.txt']
    license_path = next((p for p in candidates if p.is_file()), None)
    if not license_path:
        raise RuntimeError('CPython license not found')
    notices += ['\n=== CPython ===\n', license_path.read_text(encoding='utf-8')]
    for item in sorted((ROOT / 'packaging/windows/licenses').glob('*.txt')):
        if item.name != 'proxy_tools.txt':  # already recorded with the Python dependency
            notices += [f'\n=== {item.stem} ===\n', item.read_text(encoding='utf-8')]
    (target / 'THIRD_PARTY_LICENSES.txt').write_text('\n'.join(notices), encoding='utf-8')
    print(__version__)


if __name__ == '__main__':
    main()
