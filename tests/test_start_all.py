"""Exercise startup failure cleanup without invoking Docker."""
import os
from pathlib import Path
import shutil
import subprocess
import signal
import time
from tempfile import TemporaryDirectory
import unittest


class StartAllTests(unittest.TestCase):
    def test_detached_survives_hangup_and_stops_with_optional_final_backup(self):
        source = Path(__file__).resolve().parents[1]
        for mode in ('docker', 'docker-proxy'):
            for backups, fail_final in ((False, False), (True, False), (True, True)):
                with self.subTest(mode=mode, backups=backups, fail_final=fail_final), TemporaryDirectory() as directory:
                    root = Path(directory)
                    (root / 'ops').mkdir()
                    shutil.copyfile(source / 'start-all.sh', root / 'start-all.sh')
                    shutil.copyfile(source / 'ops/detached_start.py', root / 'ops/detached_start.py')
                    (root / 'ops/configure_journal.py').write_text('')
                    (root / 'sync-ntfy-users.sh').write_text('exit 0\n')
                    (root / 'ops/backup.py').write_text('import os,sys,time\nfrom pathlib import Path\nwith Path(os.environ["TEST_CALLS"]).open("a") as f: f.write("BACKUP " + " ".join(sys.argv[1:]) + "\\n")\nif "--loop" in sys.argv: time.sleep(60)\nsys.exit(int(os.environ["TEST_FAIL_FINAL"]))\n')
                    docker = root / 'docker'
                    docker.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$TEST_CALLS"\n')
                    docker.chmod(0o755)
                    calls = root / 'calls'
                    env = {**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'], 'TEST_CALLS': str(calls), 'TEST_FAIL_FINAL': str(int(fail_final))}
                    command = ['bash', str(root / 'start-all.sh')]
                    try:
                        result = subprocess.run(command + [mode, '-d'] + (['--backups'] if backups else []),
                                                env=env, capture_output=True, text=True, timeout=8)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn('SSH-Verbindung', result.stdout)
                        self.assertNotIn('down', calls.read_text())
                        self.assertNotIn('logs -f', calls.read_text())
                        self.assertIn('logs --tail=100', calls.read_text())
                        # Locate the supervisor through its listening socket via /proc,
                        # rather than trusting a persistent PID file.
                        socket_path = str(root / '.local-state/start-all.sock')
                        inode = next(line.split()[6] for line in Path('/proc/net/unix').read_text().splitlines() if line.endswith(socket_path))
                        pid = None
                        for proc in Path('/proc').iterdir():
                            if not proc.name.isdigit():
                                continue
                            try:
                                if any(os.readlink(fd) == f'socket:[{inode}]' for fd in (proc / 'fd').iterdir()):
                                    pid = int(proc.name)
                                    break
                            except (PermissionError, FileNotFoundError, ProcessLookupError):
                                continue
                        self.assertIsNotNone(pid)
                        os.kill(pid, signal.SIGHUP)
                        time.sleep(.1)
                        os.kill(pid, 0)
                        duplicate = subprocess.run(command + ['-d'], env=env, capture_output=True, text=True, timeout=5)
                        self.assertEqual(duplicate.returncode, 1)
                        self.assertIn('Bereits aktiv', duplicate.stdout)
                    finally:
                        stopped = subprocess.run(command + ['--stop'], env=env, capture_output=True, text=True, timeout=8)
                    self.assertEqual(stopped.returncode, int(fail_final), stopped.stderr)
                    recorded = calls.read_text()
                    self.assertIn('compose ' + ('--profile proxy ' if mode == 'docker-proxy' else '') + 'down', recorded)
                    self.assertEqual('BACKUP --loop' in recorded, backups)
                    self.assertEqual('BACKUP \n' in recorded, backups)
                    if backups:
                        self.assertLess(recorded.index('BACKUP \n'), recorded.index('down'))
                    self.assertFalse((root / '.local-state/start-all.sock').exists())

    def run_script(self, mode, *, fail_up=False, fail_sync=False, backups=False, detached=False):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(Path(__file__).resolve().parents[1] / 'start-all.sh', root / 'start-all.sh')
            (root / 'sync-ntfy-users.sh').write_text('exit ' + ('9' if fail_sync else '0') + '\n')
            (root / 'ops').mkdir()
            (root / 'ops' / 'configure_journal.py').write_text('# Host setup is mocked in startup tests.\n')
            (root / 'ops' / 'backup.py').write_text('import os, sys, time\nfrom pathlib import Path\nwith Path(os.environ["TEST_CALLS"]).open("a") as f: f.write("BACKUP " + " ".join(sys.argv[1:]) + "\\n")\nif "--loop" in sys.argv: time.sleep(60)\n')
            docker = root / 'docker'
            docker.write_text('''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$TEST_CALLS"
if [[ " $* " == *" up "* && "$TEST_FAIL_UP" == 1 ]]; then exit 7; fi
if [[ "$*" == "compose ps -a -q ntfy" ]]; then echo test-ntfy-id; fi
if [[ "$*" == "compose logs -f" ]]; then sleep 0.1; fi
exit 0
''')
            docker.chmod(0o755)
            calls = root / 'calls'
            result = subprocess.run(['bash', str(root / 'start-all.sh'), mode] + (['--backups'] if backups else []) + (['-d'] if detached else []),
                                    env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'],
                                         'TEST_CALLS': str(calls), 'TEST_FAIL_UP': str(int(fail_up))},
                                    capture_output=True, text=True, timeout=5)
            return result, calls.read_text()

    def test_failed_start_keeps_containers_and_prints_health_diagnostics(self):
        for mode in ('docker', 'docker-proxy'):
            with self.subTest(mode=mode):
                result, calls = self.run_script(mode, fail_up=True)
                self.assertEqual(result.returncode, 7)
                self.assertNotIn('down', calls)
                self.assertIn('compose logs --no-color --tail=100', calls)
                self.assertIn('inspect --format', calls)
                self.assertIn('Container bleiben', result.stdout)

    def test_failed_sync_keeps_containers(self):
        result, calls = self.run_script('docker', fail_sync=True)
        self.assertEqual(result.returncode, 9)
        self.assertNotIn('down', calls)

    def test_detached_start_failure_does_not_claim_success_or_stop_containers(self):
        for fail in ('up', 'sync'):
            result, calls = self.run_script('docker', detached=True, fail_up=fail == 'up', fail_sync=fail == 'sync')
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('down', calls)
            self.assertNotIn('SSH-Verbindung', result.stdout)

    def test_successful_run_retains_existing_shutdown_behavior(self):
        for mode in ('docker', 'docker-proxy'):
            result, calls = self.run_script(mode)
            self.assertEqual(result.returncode, 0)
            self.assertIn('down', calls)

    def test_backups_require_flag_on_each_start(self):
        result, calls = self.run_script('docker', backups=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('BACKUP --loop', calls)
        self.assertIn('BACKUP \n', calls)
        self.assertLess(calls.index('BACKUP \n'), calls.index('compose down'))
        result, calls = self.run_script('docker')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('BACKUP ', calls)
