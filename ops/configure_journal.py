"""Configure host-wide journal retention. Default: preview only, never source .env."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def retention_days(env_file: Path) -> int:
    raw = '7'
    for line in env_file.read_text().splitlines():
        match = re.fullmatch(r'\s*(?:export\s+)?LOG_RETENTION_DAYS\s*=\s*(.*?)\s*', line)
        if match:
            value = re.fullmatch(r'''(?:"([0-9]+)"|'([0-9]+)'|([0-9]+))\s*(?:#.*)?''', match.group(1))
            if not value:
                raise ValueError('LOG_RETENTION_DAYS muss eine ganze Zahl zwischen 1 und 365 sein.')
            raw = next(group for group in value.groups() if group is not None)
    days = int(raw)
    if not 1 <= days <= 365:
        raise ValueError('LOG_RETENTION_DAYS muss zwischen 1 und 365 liegen.')
    return days


def configuration(days: int) -> dict[str, str]:
    if not isinstance(days, int) or not 1 <= days <= 365:
        raise ValueError('Ungültige Aufbewahrungsfrist')
    return {
        '/etc/logrotate.d/nginx':
            '# Managed by cal11 startup; applies to nginx files in this directory.\n'
            '/var/log/nginx/*.log {\n'
            f'    daily\n    rotate {days}\n    maxage {days}\n'
            '    missingok\n    ifempty\n    compress\n    delaycompress\n'
            '    create\n    sharedscripts\n    postrotate\n'
            '        if /usr/bin/systemctl is-active --quiet nginx.service; then\n'
            '            /usr/bin/systemctl kill --kill-who=main --signal=USR1 nginx.service\n'
            '        fi\n    endscript\n}\n',
        '/etc/systemd/journald.conf.d/90-cal11-retention.conf':
            f'# Applies to the entire host system journal.\n[Journal]\nMaxRetentionSec={days}day\nMaxFileSec=1h\n',
        '/etc/systemd/system/cal11-journal-retention.service':
            '[Unit]\nDescription=Rotate and expire host journal logs\n'
            '[Service]\nType=oneshot\n'
            f'ExecStart=/usr/bin/journalctl --rotate --vacuum-time={days}d\n',
        '/etc/systemd/system/cal11-journal-retention.timer':
            '[Unit]\nDescription=Hourly host journal retention\n'
            '[Timer]\nOnCalendar=hourly\nPersistent=true\nAccuracySec=1min\n'
            '[Install]\nWantedBy=timers.target\n',
    }


def ensure_configuration(env_file: Path):
    env_file = env_file.resolve()
    files = configuration(retention_days(env_file))
    host = Path('/etc/machine-id').read_text().strip()
    fingerprint = hashlib.sha256((host + json.dumps(files, sort_keys=True)).encode()).hexdigest()
    marker = env_file.parent / '.local-state' / 'journal-retention'
    if marker.is_file() and marker.read_text().strip() == fingerprint:
        if all(Path(name).is_file() and Path(name).read_text() == content for name, content in files.items()):
            enabled = subprocess.run(['systemctl', 'is-enabled', '--quiet', 'cal11-journal-retention.timer']).returncode == 0
            active = subprocess.run(['systemctl', 'is-active', '--quiet', 'cal11-journal-retention.timer']).returncode == 0
            logs_enabled = subprocess.run(['systemctl', 'is-enabled', '--quiet', 'logrotate.timer']).returncode == 0
            logs_active = subprocess.run(['systemctl', 'is-active', '--quiet', 'logrotate.timer']).returncode == 0
            if enabled and active and logs_enabled and logs_active:
                return
    print('[start-all] Richte die Aufbewahrung für das gesamte Systemjournal und nginx-Dateilogs ein. sudo fragt bei Bedarf nach deinem Passwort.', flush=True)
    command = [sys.executable, str(Path(__file__).resolve()), '--install', '--env-file', str(env_file)]
    if os.geteuid() != 0:
        command.insert(0, 'sudo')
    subprocess.run(command, check=True)
    marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(fingerprint + '\n')
    temporary.replace(marker)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=Path(__file__).resolve().parent.parent / '.env')
    parser.add_argument('--ensure', action='store_true', help='Configure once using sudo and remember successful installation locally')
    parser.add_argument('--install', action='store_true', help='Install and activate host-wide retention (requires root)')
    args = parser.parse_args()
    if args.ensure:
        ensure_configuration(args.env_file)
        return
    files = configuration(retention_days(args.env_file))
    if not args.install:
        for filename, content in files.items():
            print(f'# {filename}\n{content}')
        return
    if os.geteuid() != 0 or not Path('/run/systemd/system').is_dir():
        raise RuntimeError('Installation muss als root auf dem systemd-Server ausgeführt werden.')
    if not Path('/usr/bin/journalctl').is_file():
        raise RuntimeError('/usr/bin/journalctl fehlt.')
    # Validate prerequisites before writing any host configuration.
    subprocess.run(['systemctl', 'cat', 'logrotate.timer'], check=True, stdout=subprocess.DEVNULL)
    nginx_rule = Path('/etc/logrotate.d/nginx')
    nginx_backup = Path('/etc/nginx-logrotate.cal11-original')
    if nginx_rule.is_file() and not nginx_backup.exists() and not nginx_rule.read_text().startswith('# Managed by cal11'):
        nginx_backup.write_bytes(nginx_rule.read_bytes())
        nginx_backup.chmod(0o600)
    for filename, content in files.items():
        target = Path(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        target.chmod(0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'restart', 'systemd-journald'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'cal11-journal-retention.timer'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'logrotate.timer'], check=True)
    print('Hostweite Journal-Aufbewahrung eingerichtet. Projektcontainer mit docker compose up -d --build neu erstellen.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
