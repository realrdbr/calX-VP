"""SSH-independent lifecycle for start-all's Docker mode (Linux, stdlib only)."""
import argparse
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.local-state'
SOCKET = STATE / 'start-all.sock'


def launch(args):
    read_fd, write_fd = os.pipe()
    # fd 9 holds the shell's flock; inheriting it prevents overlapping starts.
    command = [sys.executable, __file__, '--serve', '--mode', args.mode,
               '--ready-fd', str(write_fd)]
    if args.backups:
        command.append('--backups')
    log_fd = os.open(STATE / 'start-all.log', os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    os.fchmod(log_fd, 0o600)
    try:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                   stdout=log_fd, stderr=subprocess.STDOUT,
                                   start_new_session=True, pass_fds=(9, write_fd))
    finally:
        os.close(write_fd)
        os.close(log_fd)
    try:
        ready = select.select([read_fd], [], [], 15)[0]
        if not ready or os.read(read_fd, 1) != b'1':
            process.terminate()
            process.wait()
            raise RuntimeError('Hintergrundstart fehlgeschlagen; siehe .local-state/start-all.log')
    finally:
        os.close(read_fd)


def stop():
    with socket.socket(socket.AF_UNIX) as client:
        try:
            client.connect(str(SOCKET))
        except (FileNotFoundError, ConnectionRefusedError):
            print('Kein mit -d gestarteter Hintergrundbetrieb erreichbar.', file=sys.stderr)
            return 1
        print('Beende Hintergrundbetrieb; ein Abschlussbackup kann einige Zeit dauern.', flush=True)
        client.sendall(b'stop\n')
        result = client.recv(16)
    if result != b'0\n':
        print('Beenden fehlgeschlagen; siehe .local-state/start-all.log', file=sys.stderr)
        return 1
    print('Alle Dienste wurden beendet.')
    return 0


def serve(args):
    stopping = False

    def request_stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    backup = None
    requester = None
    status = 0
    compose = ['docker', 'compose'] + (['--profile', 'proxy'] if args.mode == 'docker-proxy' else [])
    with socket.socket(socket.AF_UNIX) as server:
        # The inherited exclusive lock proves that any previous socket is stale.
        SOCKET.unlink(missing_ok=True)
        server.bind(str(SOCKET))
        os.chmod(SOCKET, 0o600)
        server.listen(1)
        server.settimeout(1)
        try:
            if args.backups:
                backup = subprocess.Popen([sys.executable, str(ROOT / 'ops/backup.py'), '--loop'],
                                          cwd=ROOT, start_new_session=True)
            os.write(args.ready_fd, b'1')
            os.close(args.ready_fd)
            print('Hintergrundbetrieb aktiv.', flush=True)
            while not stopping:
                if backup is not None and backup.poll() is not None:
                    print('WARNUNG: Backup-Worker unerwartet beendet. Bitte Hintergrundbetrieb neu starten.', flush=True)
                    backup = None
                try:
                    client, _ = server.accept()
                except socket.timeout:
                    continue
                client.settimeout(2)
                try:
                    if client.recv(16) == b'stop\n':
                        requester = client
                        stopping = True
                    else:
                        client.close()
                except OSError:
                    client.close()
        finally:
            if backup is not None:
                try:
                    os.killpg(backup.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                backup.wait()
            if args.backups:
                print('Erstelle Abschlussbackup...', flush=True)
                if subprocess.run([sys.executable, str(ROOT / 'ops/backup.py')], cwd=ROOT).returncode:
                    print('WARNUNG: Abschlussbackup fehlgeschlagen.', flush=True)
                    status = 1
            if subprocess.run(compose + ['down'], cwd=ROOT).returncode:
                status = 1
            SOCKET.unlink(missing_ok=True)
            # Release before replying so an immediate restart can acquire the lock.
            os.close(9)
            if requester is not None:
                try:
                    requester.sendall(f'{status}\n'.encode())
                except OSError:
                    pass
                requester.close()
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--launch', action='store_true')
    action.add_argument('--serve', action='store_true')
    action.add_argument('--stop', action='store_true')
    parser.add_argument('--mode', choices=['docker', 'docker-proxy'], default='docker')
    parser.add_argument('--backups', action='store_true')
    parser.add_argument('--ready-fd', type=int)
    args = parser.parse_args()
    try:
        sys.exit(stop() if args.stop else serve(args) if args.serve else launch(args))
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
