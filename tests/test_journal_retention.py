from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from ops.configure_journal import configuration, retention_days


class JournalRetentionTests(unittest.TestCase):
    def test_reads_only_retention_without_executing_env(self):
        with TemporaryDirectory() as root:
            path = Path(root) / '.env'
            path.write_text('SECRET=$(do-not-execute)\nLOG_RETENTION_DAYS="14" # comment\n')
            self.assertEqual(retention_days(path), 14)
            for bad in ('0', '-1', '366', '$(touch /tmp/unsafe)', '7; echo unsafe', '7.5'):
                path.write_text(f'LOG_RETENTION_DAYS={bad}\n')
                with self.assertRaises(ValueError):
                    retention_days(path)

    def test_generated_files_share_retention_and_hourly_cleanup(self):
        files = configuration(7)
        self.assertIn('MaxRetentionSec=7day', files['/etc/systemd/journald.conf.d/90-cal11-retention.conf'])
        self.assertIn('--rotate --vacuum-time=7d', files['/etc/systemd/system/cal11-journal-retention.service'])
        self.assertIn('OnCalendar=hourly', files['/etc/systemd/system/cal11-journal-retention.timer'])
        self.assertIn('Persistent=true', files['/etc/systemd/system/cal11-journal-retention.timer'])
        nginx = files['/etc/logrotate.d/nginx']
        self.assertIn('/var/log/nginx/*.log', nginx)
        self.assertIn('rotate 7', nginx)
        self.assertIn('maxage 7', nginx)
        self.assertIn('ifempty', nginx)
        self.assertIn('--signal=USR1', nginx)

    def test_ensure_remembers_success_and_reconfigures_changed_retention(self):
        from unittest.mock import patch, Mock
        from ops.configure_journal import ensure_configuration
        with TemporaryDirectory() as root:
            env = Path(root) / '.env'
            env.write_text('LOG_RETENTION_DAYS=7\n')
            installed = Path(root) / 'installed'
            installed.write_text('days=7')
            with patch('ops.configure_journal.configuration', side_effect=lambda days: {str(installed): f'days={days}'}), patch('ops.configure_journal.subprocess.run', return_value=Mock(returncode=0)) as run:
                ensure_configuration(env)
                self.assertIn('--install', run.call_args.args[0])
                self.assertTrue((Path(root) / '.local-state/journal-retention').is_file())
                run.reset_mock()
                ensure_configuration(env)
                self.assertEqual(run.call_count, 4)
                self.assertTrue(all('--install' not in call.args[0] for call in run.call_args_list))
                env.write_text('LOG_RETENTION_DAYS=8\n')
                ensure_configuration(env)
                self.assertIn('--install', run.call_args.args[0])

    def test_failed_install_does_not_write_success_marker(self):
        from unittest.mock import patch
        from subprocess import CalledProcessError
        from ops.configure_journal import ensure_configuration
        with TemporaryDirectory() as root:
            env = Path(root) / '.env'
            env.write_text('LOG_RETENTION_DAYS=7\n')
            with patch('ops.configure_journal.subprocess.run', side_effect=CalledProcessError(1, 'sudo')):
                with self.assertRaises(CalledProcessError):
                    ensure_configuration(env)
            self.assertFalse((Path(root) / '.local-state/journal-retention').exists())
