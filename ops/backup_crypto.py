"""Authenticated streaming backup encryption; requires cryptography (VP image)."""
import os
import sys
import tempfile
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b'CAL11-BACKUP-1\n'


def encrypt(source, target, key):
    nonce = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    cipher.authenticate_additional_data(MAGIC)
    target.write(MAGIC + nonce)
    while chunk := source.read(1024 * 1024):
        target.write(cipher.update(chunk))
    target.write(cipher.finalize())
    target.write(cipher.tag)


def decrypt(source, target, key):
    if source.read(len(MAGIC)) != MAGIC:
        raise ValueError('Unbekanntes Backupformat')
    nonce = source.read(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).decryptor()
    cipher.authenticate_additional_data(MAGIC)
    # Never release plaintext before the complete authentication tag is checked.
    with tempfile.TemporaryFile() as plain:
        tail = b''
        while chunk := source.read(1024 * 1024):
            data = tail + chunk
            tail = data[-16:]
            plain.write(cipher.update(data[:-16]))
        plain.write(cipher.finalize_with_tag(tail))
        plain.seek(0)
        while chunk := plain.read(1024 * 1024):
            target.write(chunk)


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'stream-encrypt':
        encrypt(sys.stdin.buffer, sys.stdout.buffer, sys.stdin.buffer.read(32))
    elif len(sys.argv) == 5 and sys.argv[1] == 'decrypt':
        # Usage: python backup_crypto.py decrypt KEY ARCHIVE OUTPUT.tar.gz
        key = open(sys.argv[2], 'rb').read()
        with open(sys.argv[3], 'rb') as source:
            # Use exclusive creation and private permissions; never overwrite.
            fd = os.open(sys.argv[4], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, 'wb') as target:
                    decrypt(source, target, key)
            except BaseException:
                os.unlink(sys.argv[4])
                raise
    else:
        raise SystemExit('Usage: backup_crypto.py decrypt KEY ARCHIVE OUTPUT.tar.gz')
