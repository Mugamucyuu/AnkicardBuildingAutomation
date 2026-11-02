"""Exercise the real native close callback, cancellation, persistence and UI resume.

Only isolated offline jobs are used. Dialog answers are scripted; pywebview's
FormClosing event and renderer are real. No model calls or Anki writes.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def host(mode):
    from vocab_app import desktop
    import webview
    original_popen = subprocess.Popen
    def popen(command, **kwargs):
        if command[1:3] == ['-m', 'vocab_app.desktop']:
            command = [command[0], str(Path(__file__).resolve()), '--worker', *command[3:]]
        return original_popen(command, **kwargs)
    subprocess.Popen = popen
    original_create = webview.create_window
    loaded = threading.Event()
    answers, prompts = [], []
    controllers = []
    original_controller_init = desktop.CloseController.__init__
    def controller_init(self, *args):
        original_controller_init(self, *args)
        controllers.append(self)
    desktop.CloseController.__init__ = controller_init
    def wait_cancelled(count):
        deadline = time.monotonic() + 30
        while len(prompts) < count or controllers[0].lock.locked():
            assert time.monotonic() < deadline, 'Close cancellation did not settle'
            time.sleep(.1)
    def create(*args, **kwargs):
        kwargs['hidden'] = True
        window = original_create(*args, **kwargs)
        window.events.loaded += loaded.set
        def confirm(title, message):
            prompts.append(message)
            if not answers:
                raise AssertionError('Unexpected confirmation: ' + message)
            return answers.pop(0)
        window.create_confirmation_dialog = confirm
        return window
    webview.create_window = create
    original_start = webview.start
    report = Path(os.environ['ANKICARD_DATA_DIR']) / (mode + '.json')
    errors = []
    def drive():
        try:
            assert loaded.wait(60), 'Native renderer did not load within 60 seconds'
            window = webview.windows[0]
            ready = next(Path(os.environ['ANKICARD_DATA_DIR']).glob('desktop-*/ready.json'))
            server = desktop.DesktopServer(os.environ['ANKICARD_DATA_DIR'])
            server.url = json.loads(ready.read_text())['url']
            token = server.request('/api/bootstrap')['token']
            deadline = time.monotonic() + 30
            while not window.evaluate_js("Boolean(document.querySelector('#prompt-text').value)"):
                assert time.monotonic() < deadline, 'Prompt editor did not initialize'
                time.sleep(.1)
            if mode == 'interrupt':
                for lang, word in [('en','apple'),('ja','猫'),('ko','나무')]:
                    server.request('/api/jobs', {'language':lang,'text':word,'provider':'offline',
                        'mode':'independent','tag_source':'seed'}, token)
                answers.append(False)
                window.destroy()
                wait_cancelled(1)
                assert window.evaluate_js('document.title') == 'Vocabulary Studio'
                assert not (Path(os.environ['ANKICARD_DATA_DIR']) / 'interrupt.json').exists()
                # Dirty prompt cancellation must also leave the renderer responsive.
                window.evaluate_js("document.documentElement.dataset.promptDirty='true'")
                answers.append(False)
                window.destroy()
                wait_cancelled(2)
                assert 'prompt' in prompts[1].lower()
                assert window.evaluate_js('document.title') == 'Vocabulary Studio'
                window.evaluate_js("document.documentElement.dataset.promptDirty='false'")
                answers.append(True)
                window.destroy()
            else:
                assert window.evaluate_js("!document.querySelector('#page-jobs').hidden")
                assert window.evaluate_js("document.body.textContent.includes('继续生成')")
                # Resume through the rendered UI buttons, not direct service methods.
                window.evaluate_js("document.querySelectorAll('#jobs-list button').forEach(b=>{if(b.textContent==='继续生成')b.click()})")
                deadline = time.monotonic() + 20
                while True:
                    jobs = server.request('/api/jobs')
                    if all(j['status']=='complete' and j['items'][0]['status']=='ready' for j in jobs):
                        break
                    assert time.monotonic() < deadline, jobs
                    time.sleep(.1)
                window.destroy()
            report.write_text(json.dumps({'ok':True,'confirmations':len(prompts)}), encoding='utf-8')
        except Exception as error:
            errors.append(repr(error))
            report.write_text(json.dumps({'ok':False,'error':repr(error),'traceback':traceback.format_exc()}), encoding='utf-8')
            os._exit(1)  # Let the worker's real parent watcher clean up.
    def start(callback, **kwargs):
        return original_start(drive, **kwargs)
    webview.start = start
    result = desktop.main([])
    assert not errors, errors
    report.write_text(json.dumps({'ok':True,'confirmations':len(prompts)}), encoding='utf-8')
    return result


def main():
    if '--worker' in sys.argv:
        sys.argv.remove('--worker')
        from vocab_app.ui_service import UIService
        from vocab_app.desktop import main as desktop_main
        if os.environ.get('CLOSE_CHECK_HOLD') == '1':
            def hold(self, job_id, index, *args):
                job = self.jobs[job_id]
                self._status(job, job['items'][index], status='generating')
                threading.Event().wait(120)
            UIService._generate_item = hold
        return desktop_main(sys.argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=['interrupt','resume'])
    args = parser.parse_args()
    if args.host:
        return host(args.host)
    directory = Path(tempfile.mkdtemp(prefix='close-check-', dir=ROOT/'output'))
    env = {**os.environ,'ANKICARD_DATA_DIR':str(directory),'ANKICARD_DISABLE_UPDATE_CHECK':'1'}
    for key in ('DEEPSEEK_API_KEY','OPENAI_API_KEY','DEEPSEEK_SEARCH_API_KEY'):
        env.pop(key,None)
    for mode in ('interrupt','resume'):
        result = subprocess.run([sys.executable,str(Path(__file__).resolve()),'--host',mode],
            env={**env,'CLOSE_CHECK_HOLD':'1' if mode=='interrupt' else '0'},timeout=150)
        report = json.loads((directory/(mode+'.json')).read_text())
        assert result.returncode == 0 and report['ok'], report
        assert report['confirmations'] == (3 if mode == 'interrupt' else 0), report
        jobs = [json.loads(p.read_text(encoding='utf-8')) for p in (directory/'jobs').glob('*/job.json')]
        assert len(jobs)==3
        assert all(j['status']==('paused' if mode=='interrupt' else 'complete') for j in jobs), jobs
    print('Close OK: real FormClosing, cancel busy exit, cancel dirty exit, save and stop, restart and UI resume, idle exit.')
    print('Isolated state:', directory)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
