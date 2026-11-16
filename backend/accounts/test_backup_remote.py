import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, override_settings
from .backup_remote import upload_archive, download_archive, object_key
from .backups import BackupError, MAGIC


@override_settings(LMS_BACKUP_S3_BUCKET='test-private-backups')
class RemoteBackupTests(SimpleTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'btbs-20261113T120000-aabbccdd.lmsbak'
        self.body = MAGIC + b'encrypted-test-payload'
        self.path.write_bytes(self.body)
        self.sha = hashlib.sha256(self.body).hexdigest()

    def fake(self, body=None):
        s3 = Mock()
        s3.head_object.return_value = {'ContentLength': len(self.body), 'Metadata': {'sha256': self.sha}, 'VersionId': 'v1'}
        s3.get_object.return_value = {'Body': io.BytesIO(self.body if body is None else body), 'Metadata': {'sha256': self.sha}}
        return s3

    def test_upload_reads_back_exact_version_and_never_deletes(self):
        s3 = self.fake()
        with patch('accounts.backup_remote.client', return_value=s3):
            result = upload_archive(self.path)
        self.assertEqual(result['sha256'], self.sha)
        self.assertEqual(s3.get_object.call_args.kwargs['VersionId'], 'v1')
        s3.delete_object.assert_not_called()

    def test_checksum_metadata_is_not_enough(self):
        with patch('accounts.backup_remote.client', return_value=self.fake(b'corrupted')):
            with self.assertRaises(BackupError): upload_archive(self.path)
        self.assertTrue(self.path.exists())

    def test_plaintext_and_paths_rejected(self):
        self.path.write_bytes(b'plaintext')
        with self.assertRaises(BackupError): upload_archive(self.path)
        for name in ['../main.key', '.env', 'btbs-invalid.lmsbak']:
            with self.assertRaises(BackupError): object_key(name)

    def test_download_checks_digest_and_preserves_existing_file(self):
        target = Path(self.tmp.name) / 'download.lmsbak'
        with patch('accounts.backup_remote.client', return_value=self.fake()):
            download_archive(self.path.name, target)
        self.assertEqual(target.read_bytes(), self.body)
        with self.assertRaises(BackupError): download_archive(self.path.name, target)
        damaged = Path(self.tmp.name) / 'bad.lmsbak'
        with patch('accounts.backup_remote.client', return_value=self.fake(b'wrong')):
            with self.assertRaises(BackupError): download_archive(self.path.name, damaged)
        self.assertFalse(damaged.exists())
