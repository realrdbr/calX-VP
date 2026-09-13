"""Daily encrypted Docker-stack backups. Host needs Python stdlib and Docker only."""
import argparse
from datetime import datetime, timezone, timedelta, time as clock_time
from calendar import monthrange
from zoneinfo import ZoneInfo
import shlex
import fcntl
import io
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(r'cal11-\d{8}T\d{6}Z-[0-9a-f]{8}\.tar\.gz\.enc')


def project_timezone(root=ROOT):
    value = os.environ.get('APP_TIMEZONE', '')
    if not value:
        for line in (root / '.env').read_text().splitlines():
            key, sep, raw = line.partition('=')
            if sep and key.strip() == 'APP_TIMEZONE':
                parts = shlex.split(raw, comments=True)
                value = parts[0] if parts else ''
    return ZoneInfo(value or 'Europe/Berlin')


def next_midnight(now):
    return datetime.combine(now.date() + timedelta(days=1), clock_time.min, tzinfo=now.tzinfo)


def month_later(value):
    year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def archives(directory):
    for path in directory.iterdir():
        if path.is_symlink():
            continue
        if path.is_file() and PATTERN.fullmatch(path.name):
            yield path
        elif path.is_dir() and re.fullmatch(r'\d{4}-\d{2}-\d{2}', path.name):
            for child in path.iterdir():
                if child.is_file() and not child.is_symlink() and PATTERN.fullmatch(child.name):
                    yield child


def organize(directory, zone):
    """Group existing flat archives without replacing an existing destination."""
    for source in list(directory.iterdir()):
        if source.is_symlink() or not source.is_file() or not PATTERN.fullmatch(source.name):
            continue
        try:
            created = datetime.strptime(source.name[6:22], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).astimezone(zone)
        except ValueError:
            continue
        destination = directory / created.date().isoformat()
        private_directory(destination)
        try:
            os.link(source, destination / source.name, follow_symlinks=False)
        except FileExistsError:
            continue
        source.unlink()


def prune(directory, now=None):
    now = now or datetime.now(ZoneInfo('Europe/Berlin'))
    for path in archives(directory):
        try:
            created = datetime.strptime(path.name[6:22], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).astimezone(now.tzinfo)
        except ValueError:
            continue
        if month_later(created) <= now:
            path.unlink()
    for path in directory.iterdir():
        if not path.is_symlink() and path.is_dir() and re.fullmatch(r'\d{4}-\d{2}-\d{2}', path.name) and not any(path.iterdir()):
            path.rmdir()


def private_directory(path):
    if path.is_symlink():
        raise RuntimeError('Backupverzeichnis darf kein Symlink sein.')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def backup(root=ROOT):
    os.umask(0o077)
    directory = root / 'backups'
    state = root / '.local-state'
    private_directory(directory)
    private_directory(state)
    with (state / 'backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        zone = project_timezone(root)
        organize(directory, zone)
        prune(directory, datetime.now(zone))
        key_path = state / 'backup.key'
        if not key_path.exists():
            if any(archives(directory)):
                raise RuntimeError('Backup-Schlüssel fehlt; vorhandene Backups zuerst prüfen.')
            with key_path.open('xb') as key_file:
                key_file.write(os.urandom(32))
        if key_path.is_symlink():
            raise RuntimeError('Backup-Schlüssel darf kein Symlink sein.')
        key_path.chmod(0o600)
        key = key_path.read_bytes()
        if len(key) != 32:
            raise RuntimeError('Ungültiger Backup-Schlüssel')
        if not (root / '.env').is_file():
            raise RuntimeError('.env für eine wiederherstellbare Sicherung fehlt.')
        compose = ['docker', 'compose']
        def export(service, command, target):
            with target.open('wb') as output:
                subprocess.run(compose + ['exec', '-T', service] + command,
                               cwd=root, stdout=output, check=True, timeout=3600)
        with tempfile.TemporaryDirectory(prefix='.pending-', dir=directory) as staging:
            staging = Path(staging)
            # Credential expansion happens inside the container, never on host CLI.
            export('mariadb', ['sh', '-c', 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mariadb-dump --user=root --single-transaction --quick --routines --events --triggers --databases "$MYSQL_DATABASE"'], staging / 'database.sql')
            snapshot = '''import io, sqlite3, tarfile, tempfile
from pathlib import Path
import sys
with tempfile.TemporaryDirectory() as temp:
    with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as archive:
        for name in ('auth.db', 'cache.db'):
            source = Path('/var/lib/ntfy') / name
            if not source.is_file(): raise RuntimeError('ntfy database missing')
            target = Path(temp) / name
            with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(target) as dest:
                src.backup(dest)
            archive.add(target, arcname=name)
'''
            export('vp', ['python', '-c', snapshot], staging / 'ntfy.tar')
            with tarfile.open(staging / 'payload.tar.gz', 'w:gz') as archive:
                for name in ('database.sql', 'ntfy.tar'):
                    archive.add(staging / name, arcname=name)
                # Secrets are included only inside the encrypted archive.
                def regular_only(member):
                    if not (member.isfile() or member.isdir()):
                        raise RuntimeError('Backupquelle enthält einen nicht unterstützten Dateityp.')
                    return member
                for name in ('.env', 'uploads', 'docker-compose.yml', 'ntfy/server.yml', 'proxy/nginx.conf'):
                    path = root / name
                    if path.exists():
                        archive.add(path, arcname=name, recursive=True, filter=regular_only)
                note = b'MariaDB transactional dump and independent SQLite online snapshots. Cross-service timestamps may differ. Restore only into an isolated empty stack. Archive contains secrets.\n'
                info = tarfile.TarInfo('RESTORE-NOTES.txt')
                info.size = len(note)
                archive.addfile(info, io.BytesIO(note))
            encrypted = staging / 'archive.enc'
            code = (root / 'ops/backup_crypto.py').read_text()
            with encrypted.open('wb') as output:
                process = subprocess.Popen(compose + ['exec', '-T', 'vp', 'python', '-c', code, 'stream-encrypt'], cwd=root, stdin=subprocess.PIPE, stdout=output)
                try:
                    process.stdin.write(key)
                    with (staging / 'payload.tar.gz').open('rb') as payload:
                        shutil.copyfileobj(payload, process.stdin)
                    process.stdin.close()
                    if process.wait(timeout=3600):
                        raise RuntimeError('Backup-Verschlüsselung fehlgeschlagen')
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
            completed = datetime.now(zone)
            day_folder = directory / completed.date().isoformat()
            private_directory(day_folder)
            name = 'cal11-' + completed.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + os.urandom(4).hex() + '.tar.gz.enc'
            encrypted.replace(day_folder / name)
            print('[backup] Verschlüsselte Sicherung erstellt: ' + name, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loop', action='store_true')
    parser.add_argument('--wait-first', action='store_true', help=argparse.SUPPRESS) # Compatibility with older startup scripts; loops now always wait for midnight.
    args = parser.parse_args()
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    zone = project_timezone()
    if args.loop:
        directory = ROOT / 'backups'
        private_directory(directory)
        organize(directory, zone)
        prune(directory, datetime.now(zone))
    while True:
        if args.loop:
            target = next_midnight(datetime.now(zone))
            print('[backup] Nächste Sicherung: ' + target.isoformat(), flush=True)
            while (remaining := target.timestamp() - time.time()) > 0:
                time.sleep(min(remaining, 60))
        try:
            backup()
        except Exception as error:
            print('[backup] Sicherung fehlgeschlagen: ' + type(error).__name__, flush=True)
            if not args.loop:
                raise SystemExit(1)
        if not args.loop:
            break
