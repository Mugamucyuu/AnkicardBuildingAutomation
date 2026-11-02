"""Probe an installed app's real official-release updater using isolated test state.

Unlike check_update_install.py, this drives the installed app's own HTTP API,
update watcher and native shutdown. A stalled host is reported, never a pass.
Run only on a disposable test installation: --install may replace that app.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocab_app.desktop import DesktopServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--state-directory', type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    executable, state = args.executable.resolve(), args.state_directory.resolve()
    # Never terminate or overwrite the user's regular application from this probe.
    assert executable.is_relative_to(ROOT/'output') and state.is_relative_to(ROOT/'output')
    state.mkdir(parents=True, exist_ok=True)
    env = {**os.environ,'ANKICARD_DATA_DIR':str(state),'ANKICARD_DISABLE_UPDATE_CHECK':'1'}
    for key in ('DEEPSEEK_API_KEY','OPENAI_API_KEY','DEEPSEEK_SEARCH_API_KEY'):
        env.pop(key,None)
    process = subprocess.Popen([str(executable)],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    result = {'ok':False}
    try:
        deadline = time.monotonic()+45
        while not list(state.glob('desktop-*/ready.json')):
            assert process.poll() is None
            assert time.monotonic()<deadline, 'No local service'
            time.sleep(.1)
        server = DesktopServer(state)
        server.url = json.loads(next(state.glob('desktop-*/ready.json')).read_text())['url']
        bootstrap = server.request('/api/bootstrap')
        token = bootstrap['token']
        result['current_version'] = bootstrap['updates']['current_version']
        # Ensure the renderer has loaded before requesting an update.
        time.sleep(5)
        server.request('/api/updates/check',{},token)
        deadline = time.monotonic()+60
        while True:
            update = server.request('/api/updates')
            if update['state'] != 'checking':
                break
            assert time.monotonic()<deadline
            time.sleep(.2)
        result['check'] = update
        assert update['state']=='available', update
        if args.install:
            server.request('/api/updates/download',{},token)
            deadline=time.monotonic()+600
            while True:
                update=server.request('/api/updates')
                if update['state']!='downloading':
                    break
                assert time.monotonic()<deadline
                time.sleep(.5)
            result['download']=update
            assert update['state']=='ready', update
            server.request('/api/updates/install',{},token)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                result['install']=server.request('/api/updates')
                result['error']='native_shutdown_stalled'
                return 1
            deadline=time.monotonic()+240
            while not (state/'updates/last-result.json').exists():
                assert time.monotonic()<deadline, 'Installer helper did not finish'
                time.sleep(.5)
            result['install']=json.loads((state/'updates/last-result.json').read_text(encoding='utf-8-sig'))
            assert result['install']['ok'], result['install']
        result['ok']=True
        return 0
    except Exception as error:
        result['error']=repr(error)
        return 1
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(10)
        (state/'published-update-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True))


if __name__ == '__main__':
    raise SystemExit(main())
