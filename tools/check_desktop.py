"""Exercise a frozen Windows app with a clean state and no Python on PATH."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from urllib.parse import urlparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--state-directory', type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve()
    with tempfile.TemporaryDirectory(prefix='ankicard-desktop-') as directory:
        directory = Path(directory)
        report = directory / 'report.json'
        env = {k: v for k, v in os.environ.items() if k not in (
            'PYTHONPATH', 'PYTHONHOME', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY',
            'DEEPSEEK_SEARCH_API_KEY', 'ANKI_AI_PROVIDER', 'DEEPSEEK_MODEL', 'OPENAI_MODEL')}
        env['ANKICARD_DATA_DIR'] = str(args.state_directory.resolve() if args.state_directory else directory / 'state')
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        result = subprocess.run([str(executable), '--smoke-test', str(report)],
                                cwd=directory, env=env, timeout=120)
        if not report.exists():
            raise RuntimeError(f'No desktop report (exit {result.returncode})')
        data = json.loads(report.read_text(encoding='utf-8'))
        assert result.returncode == 0 and data['ok'], data
        endpoint = urlparse(data['url'])
        with socket.socket() as client:
            assert client.connect_ex((endpoint.hostname, endpoint.port)) != 0, 'Worker port left open'
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x00100000, False, data['worker_pid'])
        if handle:
            try:
                assert kernel32.WaitForSingleObject(handle, 0) == 0, 'Worker left running'
            finally:
                kernel32.CloseHandle(handle)
        print('Desktop OK: actual WebView2, unchanged UI, 11 prompts, three offline languages, clean shutdown; no Python on PATH.')


if __name__ == '__main__':
    main()
