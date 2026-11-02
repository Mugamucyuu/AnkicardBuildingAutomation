"""Lifecycle regressions for the Windows host, without Anki/model credentials."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlparse

from vocab_app.desktop import DesktopServer, SingleInstance
from vocab_app.settings import ROOT


@unittest.skipUnless(sys.platform == 'win32', 'Windows desktop lifecycle')
class DesktopTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='desktop 空格 ', dir=ROOT / 'output')
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_single_instance_lock_released_and_scoped_to_data_directory(self):
        first, second = SingleInstance(self.directory), SingleInstance(self.directory)
        third = SingleInstance(self.directory / 'another')
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            self.assertTrue(third.acquire())
            first.close()
            self.assertTrue(second.acquire())
        finally:
            first.close()
            second.close()
            third.close()

    def test_server_uses_free_port_ships_latest_routes_and_stops_on_close(self):
        server = DesktopServer(self.directory)
        try:
            server.start()
            self.assertIsNone(server.process.poll())
            bootstrap = server.request('/api/bootstrap')
            self.assertEqual(len(bootstrap['prompts']['stages']), 11)
            self.assertEqual(server.request('/api/jobs'), [])
            self.assertEqual(server.request('/api/parse', {'text': '猫,apple'}, bootstrap['token']),
                             {'words': ['猫', 'apple']})
            endpoint = urlparse(server.url)
        finally:
            server.close()
        self.assertIsNotNone(server.process.poll())
        with socket.socket() as client:
            self.assertNotEqual(client.connect_ex((endpoint.hostname, endpoint.port)), 0)
        self.assertEqual(list(self.directory.glob('desktop-*')), [])

    def test_worker_exits_if_host_is_killed(self):
        marker = self.directory / 'worker.json'
        code = ("from vocab_app.desktop import DesktopServer; import json,time; from pathlib import Path; "
                f"server=DesktopServer(Path({str(self.directory)!r})); server.start(); "
                f"Path({str(marker)!r}).write_text(json.dumps({{'url':server.url,'pid':server.process.pid}})); "
                "time.sleep(60)")
        host = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT)
        try:
            deadline = time.monotonic() + 20
            while not marker.exists() and time.monotonic() < deadline:
                self.assertIsNone(host.poll())
                time.sleep(.05)
            info = json.loads(marker.read_text())
            endpoint = urlparse(info['url'])
            host.kill()
            host.wait(timeout=5)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with socket.socket() as client:
                    if client.connect_ex((endpoint.hostname, endpoint.port)) != 0:
                        break
                time.sleep(.1)
            else:
                self.fail('Orphan worker port remains open after host death')
        finally:
            if host.poll() is None:
                host.kill()
                host.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
