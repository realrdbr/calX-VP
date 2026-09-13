"""Exercise startup failure cleanup without invoking Docker."""
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


class StartAllTests(unittest.TestCase):
    def run_script(self, mode, *, fail_up=False, fail_sync=False, backups=False):
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
            result = subprocess.run(['bash', str(root / 'start-all.sh'), mode] + (['--backups'] if backups else []),
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
