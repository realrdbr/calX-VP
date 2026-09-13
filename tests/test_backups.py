import io
import os
from pathlib import Path
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest

from cryptography.exceptions import InvalidTag
from ops.backup import prune, next_midnight, month_later, organize
from datetime import datetime
from zoneinfo import ZoneInfo
from ops.backup_crypto import encrypt, decrypt
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ops'))
from ops.restore import extract_regular


class BackupTests(unittest.TestCase):
    def test_encryption_roundtrip_and_tampering_releases_no_plaintext(self):
        key = os.urandom(32)
        plain = b'private backup data' * 100000
        encrypted = io.BytesIO()
        encrypt(io.BytesIO(plain), encrypted, key)
        result = io.BytesIO()
        decrypt(io.BytesIO(encrypted.getvalue()), result, key)
        self.assertEqual(result.getvalue(), plain)
        corrupted = bytearray(encrypted.getvalue())
        corrupted[-20] ^= 1
        result = io.BytesIO()
        with self.assertRaises(InvalidTag):
            decrypt(io.BytesIO(corrupted), result, key)
        self.assertEqual(result.getvalue(), b'')

    def test_midnight_observes_daylight_saving(self):
        zone = ZoneInfo('Europe/Berlin')
        for month, day, hours in ((3, 29, 23), (10, 25, 25)):
            now = datetime(2026, month, day, tzinfo=zone)
            target = next_midnight(now)
            self.assertEqual(target.hour, 0)
            self.assertEqual((target.timestamp() - now.timestamp()) / 3600, hours)

    def test_calendar_month_clamps_month_end(self):
        zone = ZoneInfo('Europe/Berlin')
        self.assertEqual(month_later(datetime(2026, 1, 31, tzinfo=zone)), datetime(2026, 2, 28, tzinfo=zone))
        self.assertEqual(month_later(datetime(2024, 1, 31, tzinfo=zone)), datetime(2024, 2, 29, tzinfo=zone))

    def test_pruning_handles_date_folders_and_legacy_archives(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            dated = root / '2026-01-31'
            dated.mkdir()
            old = dated / 'cal11-20260131T000000Z-01234567.tar.gz.enc'
            legacy = root / 'cal11-20260101T000000Z-01234567.tar.gz.enc'
            other = root / 'important.tar.gz.enc'
            new = root / 'cal11-20260201T000000Z-01234567.tar.gz.enc'
            for path in (old, legacy, other, new): path.write_bytes(b'test')
            prune(root, datetime(2026, 2, 28, 2, tzinfo=ZoneInfo('Europe/Berlin')))
            self.assertFalse(old.exists())
            self.assertFalse(legacy.exists())
            self.assertFalse(dated.exists())
            self.assertTrue(other.exists())
            self.assertTrue(new.exists())

    def test_restore_rejects_path_traversal_and_symlinks(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for name, kind in (('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)):
                with tarfile.open(root / 'test.tar', 'w') as archive:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = '/etc/passwd' if kind == tarfile.SYMTYPE else ''
                    archive.addfile(member)
                with self.assertRaises(ValueError):
                    extract_regular(root / 'test.tar', root / 'output')

    def test_flat_archives_are_grouped_by_local_date_without_overwriting(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / 'cal11-20260913T230000Z-01234567.tar.gz.enc'
            archive.write_bytes(b'original')
            organize(root, ZoneInfo('Europe/Berlin'))
            grouped = root / '2026-09-14' / archive.name
            self.assertEqual(grouped.read_bytes(), b'original')
            self.assertFalse(archive.exists())
            archive.write_bytes(b'conflicting-copy')
            organize(root, ZoneInfo('Europe/Berlin'))
            self.assertEqual(grouped.read_bytes(), b'original')
            self.assertEqual(archive.read_bytes(), b'conflicting-copy')
