import builtins
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import os
if os.environ.get('CAL11_BACKUP_E2E') != '1':
    raise SystemExit('Isolierten Test ausdrücklich mit CAL11_BACKUP_E2E=1 aktivieren.')
repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / 'ops'))
import backup
import restore

with tempfile.TemporaryDirectory(prefix='cal11-backup-check-') as folder:
    root = Path(folder)
    (root / 'ops').mkdir()
    for name in ('backup_crypto.py', 'backup_archive.py'):
        shutil.copyfile(repo / 'ops' / name, root / 'ops' / name)
    (root / 'uploads').mkdir()
    (root / 'uploads' / 'example.txt').write_text('original attachment')
    (root / 'data' / 'ntfy').mkdir(parents=True)
    (root / '.env').write_text('DB_NAME=regression\nDB_ROOT_PASSWORD=isolated-test-password\nAPP_ENCRYPTION_KEY=test-only\n')
    (root / 'docker-compose.yml').write_text('''name: cal11-backup-check
services:
  mariadb:
    image: mariadb:11.4
    environment:
      MYSQL_ROOT_PASSWORD: isolated-test-password
      MYSQL_DATABASE: regression
    healthcheck:
      test: [CMD, healthcheck.sh, --connect, --innodb_initialized]
      interval: 1s
      timeout: 3s
      retries: 60
    volumes:
      - db:/var/lib/mysql
  vp:
    image: jahrgangskalender-vp
    entrypoint: [sleep, infinity]
    volumes:
      - ./data/ntfy:/var/lib/ntfy
  app:
    image: jahrgangskalender-vp
    entrypoint: [sleep, infinity]
  ntfy:
    image: jahrgangskalender-vp
    entrypoint: [sleep, infinity]
  ntfy-provisioner:
    image: jahrgangskalender-vp
    entrypoint: [sleep, infinity]
volumes:
  db:
''')
    # exec uses the running container's python, while restore overrides entrypoint.
    def compose(*args, **kw):
        return subprocess.run(['docker', 'compose', *args], cwd=root, check=True, **kw)
    try:
        compose('up', '-d', '--wait')
        compose('exec', '-T', 'vp', 'python', '-c', "import sqlite3; from pathlib import Path; [(lambda db: (db.execute('create table sample(value text)'), db.execute(\"insert into sample values ('original')\"), db.commit(), db.close()))(sqlite3.connect('/var/lib/ntfy/'+name)) for name in ('auth.db','cache.db')]")
        shell = 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mariadb --user=root "$MYSQL_DATABASE"'
        compose('exec', '-T', 'mariadb', 'sh', '-c', shell, input=b'CREATE TABLE example(value TEXT); INSERT INTO example VALUES ("original"); CREATE TABLE app_sessions(token TEXT); INSERT INTO app_sessions VALUES ("old-token");')
        backup.backup(root)
        archive = next((root / 'backups').rglob('*.enc'))
        compose('exec', '-T', 'mariadb', 'sh', '-c', shell, input=b'UPDATE example SET value="changed";')
        (root / 'uploads' / 'example.txt').write_text('changed attachment')
        compose('stop', '--timeout', '1')
        restore.ROOT = root
        builtins.input = lambda prompt: 'WIEDERHERSTELLEN'
        restore.restore(archive)
        result = compose('exec', '-T', 'mariadb', 'sh', '-c', shell + ' --batch --skip-column-names', input=b'SELECT value FROM example; SELECT COUNT(*) FROM app_sessions;', stdout=subprocess.PIPE)
        assert result.stdout.strip() == b'original\n0', result.stdout
        assert (root / 'uploads' / 'example.txt').read_text() == 'original attachment'
        assert len(list((root / 'backups').rglob('*.enc'))) == 2
        print('PASS: encrypted backup and confirmed restore, original MariaDB data and upload restored, sessions revoked, safety backup retained.')
    finally:
        compose('down', '-v', '--timeout', '1')
        # Restore container writes owned files; remove fixture files through its UID.
        subprocess.run(['docker','run','--rm','-v',str(root)+':/fixture','--entrypoint','python','jahrgangskalender-vp','-c','import os; from pathlib import Path; import shutil; [shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink() for p in Path("/fixture").iterdir()]'], check=True)
