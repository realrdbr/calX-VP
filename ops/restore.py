"""Explicit, confirmed data restore; never restores arbitrary archive paths."""
import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
from backup import ROOT, backup, private_directory
from backup_archive import extract_regular



def relevant_config(path):
    import shlex
    keys = {'APP_ENCRYPTION_KEY', 'CALENDAR_PRIVATE_DATA_KEY', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_ROOT_PASSWORD'}
    values = {}
    for line in path.read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and key.strip() in keys:
            tokens = shlex.split(value, comments=True)
            values[key.strip()] = ' '.join(tokens)
    return values


def restore(archive):
    os.umask(0o077)
    directory = ROOT / 'backups'
    private_directory(directory)
    key = ROOT / '.local-state/backup.key'
    if not key.is_file():
        raise RuntimeError('Originaler Backup-Schlüssel .local-state/backup.key fehlt.')
    compose = ['docker', 'compose']
    with tempfile.TemporaryDirectory(prefix='.restore-', dir=directory) as temp:
        temp = Path(temp)
        # Use the project's VP image for cryptography; no host dependency install.
        code = (ROOT / 'ops/backup_crypto.py').read_text()
        subprocess.run(compose + ['run', '--rm', '--no-deps', '-T', '--user', f'{os.getuid()}:{os.getgid()}',
            '--volume', f'{key.resolve()}:/restore-key:ro',
            '--volume', f'{archive.resolve()}:/restore-input:ro',
            '--volume', f'{temp}:/restore-output', '--entrypoint', 'python',
            'vp', '-c', code, 'decrypt', '/restore-key', '/restore-input', '/restore-output/payload.tar.gz'], cwd=ROOT, check=True)
        extraction = 'from pathlib import Path\n' + (ROOT / 'ops/backup_archive.py').read_text()
        extraction += "\nextract_regular(Path('/restore-output/payload.tar.gz'), Path('/restore-output/files'))\n"
        extraction += "extract_regular(Path('/restore-output/files/ntfy.tar'), Path('/restore-output/ntfy'))\n"
        subprocess.run(compose + ['run', '--rm', '--no-deps', '-T', '--user', f'{os.getuid()}:{os.getgid()}', '--volume', f'{temp}:/restore-output',
            '--entrypoint', 'python', 'vp', '-c', extraction], cwd=ROOT, check=True)
        files = temp / 'files'
        if relevant_config(files / '.env') != relevant_config(ROOT / '.env'):
            raise RuntimeError('Datenbankzugang oder Verschlüsselungsschlüssel weichen ab. Konfiguration vor Wiederherstellung manuell abgleichen; keine Daten geändert.')
        if not (files / 'database.sql').is_file() or not all((temp / 'ntfy' / name).is_file() for name in ('auth.db', 'cache.db')):
            raise RuntimeError('Backup ist unvollständig.')
        print('WARNUNG: Kalenderdaten, Konten, Uploads und ntfy-Daten werden durch das Backup ersetzt.')
        if input('Zum Fortfahren WIEDERHERSTELLEN eingeben: ').strip() != 'WIEDERHERSTELLEN':
            raise RuntimeError('Wiederherstellung abgebrochen; keine Daten geändert.')
        subprocess.run(compose + ['up', '-d', '--wait'], cwd=ROOT, check=True)
        backup(ROOT)
        subprocess.run(compose + ['stop', 'app', 'vp', 'ntfy', 'ntfy-provisioner'], cwd=ROOT, check=True)
        with (files / 'database.sql').open('rb') as source:
            subprocess.run(compose + ['exec', '-T', 'mariadb', 'sh', '-c', 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mariadb --user=root'], cwd=ROOT, stdin=source, check=True)
        revoke = """export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
for table in app_sessions vp_only_sessions vp_sessions; do
  exists=$(mariadb --user=root --batch --skip-column-names "$MYSQL_DATABASE" -e "SHOW TABLES LIKE '$table'") || exit 1
  if [ -n "$exists" ]; then
    mariadb --user=root "$MYSQL_DATABASE" -e "DELETE FROM $table" || exit 1
  fi
done"""
        subprocess.run(compose + ['exec', '-T', 'mariadb', 'sh', '-c', revoke], cwd=ROOT, check=True)
        install = '''from pathlib import Path
import shutil
uploads = Path('/restore-uploads')
for child in uploads.iterdir():
    if child.is_dir() and not child.is_symlink(): shutil.rmtree(child)
    else: child.unlink()
source = Path('/restore-source/files/uploads')
if source.exists(): shutil.copytree(source, uploads, dirs_exist_ok=True)
ntfy = Path('/var/lib/ntfy')
for name in ('auth.db','cache.db'):
    for suffix in ('','-wal','-shm'):
        (ntfy / (name + suffix)).unlink(missing_ok=True)
    shutil.copyfile(Path('/restore-source/ntfy') / name, ntfy / name)
'''
        subprocess.run(compose + ['run', '--rm', '--no-deps', '-T',
            '--volume', f'{temp}:/restore-source:ro', '--volume', f'{ROOT / "uploads"}:/restore-uploads',
            '--entrypoint', 'python', 'vp', '-c', install], cwd=ROOT, check=True)
        print('Daten wiederhergestellt. start-all startet und synchronisiert die Dienste anschließend neu.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    if not args.archive.is_file():
        raise SystemExit('Backupdatei nicht gefunden.')
    restore(args.archive)
