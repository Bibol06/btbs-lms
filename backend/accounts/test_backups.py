from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .backups import (BackupError, BackupBusy, create_backup, backup_status, decrypt, encrypt, key_bytes,
                      safe_media_name, restore_backup, write_json, backup_due)


class BackupCryptoTests(SimpleTestCase):
    def test_scheduled_backup_does_not_fail_when_another_copy_is_running(self):
        from django.core.management import call_command
        with patch('accounts.management.commands.backup_lms.create_backup', side_effect=BackupBusy('busy')):
            call_command('backup_lms', if_due=True)

    def test_manual_backup_reports_an_existing_copy_instead_of_starting_another(self):
        from django.core.management import call_command, CommandError
        with patch('accounts.management.commands.backup_lms.create_backup', side_effect=BackupBusy('busy')):
            with self.assertRaises(CommandError): call_command('backup_lms')

    def test_streaming_roundtrip_wrong_key_and_tampered_archive(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original, sealed = root/'original', root/'sealed'
            original.write_bytes(b'private backup\n'*100000)
            encrypt(original, sealed, b'a'*32)
            decrypt(sealed, root/'restored', b'a'*32)
            self.assertEqual(original.read_bytes(), (root/'restored').read_bytes())
            with self.assertRaises(BackupError):
                decrypt(sealed, root/'bad-key', b'b'*32)
            changed = bytearray(sealed.read_bytes()); changed[40] ^= 1; sealed.write_bytes(changed)
            with self.assertRaises(BackupError):
                decrypt(sealed, root/'tampered', b'a'*32)
            self.assertFalse((root/'tampered').exists())

    def test_paths_cannot_escape_restore_directory(self):
        for path in ['../secrets', '/absolute', 'folder/../../secret', 'C:/outside', 'folder\\outside', './file']:
            with self.assertRaises(BackupError): safe_media_name(path)

    def test_missing_key_does_not_replace_key_of_existing_archives(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'previous.lmsbak').write_bytes(b'previous')
            with override_settings(LMS_BACKUP_DIR=root, LMS_BACKUP_KEY_FILE=root/'missing-key'):
                with self.assertRaises(BackupError): key_bytes(create=True)
                self.assertFalse((root/'missing-key').exists())

    def test_restore_never_overwrites_live_or_existing_media(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(BackupError): restore_backup('unused', 'live_database', Path(directory)/'new')
            with self.assertRaises(BackupError): restore_backup('unused', 'lms_restore_safe', directory)

    def test_failed_attempt_has_retry_delay_and_keeps_last_good_copy(self):
        with TemporaryDirectory() as directory, override_settings(LMS_BACKUP_DIR=Path(directory)):
            good = Path(directory)/'btbs-good.lmsbak'; good.write_bytes(b'last good')
            write_json(Path(directory)/'status.json', {'last_success': '2026-01-01T00:00:00+00:00', 'last_attempt': timezone.now().isoformat(), 'error': 'failed'})
            self.assertFalse(backup_due())
            self.assertEqual(backup_status()['archives'][0]['name'], good.name)


@override_settings(MEDIA_STORAGE_MODE='local')
class BackupSnapshotTests(TransactionTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.settings_context = override_settings(LMS_BACKUP_DIR=self.root/'archives', LMS_BACKUP_KEY_FILE=self.root/'key',
                                                  MEDIA_ROOT=self.root/'media', LMS_BACKUP_KEEP=2)
        self.settings_context.enable(); self.addCleanup(self.settings_context.disable)
        User = get_user_model()
        self.owner = User.objects.create_user(username='backup_owner', role='admin')
        self.learning = User.objects.create_user(username='backup_learning', role='admin', admin_scope='learning')
        from courses.models import Course
        from learning.models import Lesson, LessonMaterial
        course = Course.objects.create(title='Snapshot test', teacher=self.owner)
        lesson = Lesson.objects.create(course=course, title='Lesson')
        self.material = LessonMaterial(lesson=lesson, title='Private file')
        self.material.file.save('backup.txt', ContentFile(b'file included in snapshot'))

    def test_real_postgres_dump_encrypted_media_and_manifest_are_consistent(self):
        archive = create_backup()
        unpacked = self.root/'unpacked.zip'
        decrypt(archive, unpacked, key_bytes())
        with zipfile.ZipFile(unpacked) as contents:
            manifest = json.loads(contents.read('manifest.json'))
            self.assertEqual(manifest['counts']['accounts_user'], 2)
            self.assertEqual(contents.read('media/'+self.material.file.name), b'file included in snapshot')
            self.assertTrue(contents.read('database.dump').startswith(b'PGDMP'))
            self.assertFalse(any('.env' in n or 'key' in n for n in contents.namelist()))
        self.assertEqual(backup_status()['media_files'], 1)
        self.assertIsNone(create_backup(if_due=True))

    def test_failed_media_read_preserves_existing_success_and_does_not_prune(self):
        first = create_backup()
        previous_success = backup_status()['last_success']
        with patch('accounts.backups.media_sources', return_value={'missing.bin': self.material.file.storage}):
            with self.assertRaises(BackupError): create_backup()
        self.assertTrue(first.exists())
        self.assertEqual(backup_status()['last_success'], previous_success)
        self.assertFalse(list((self.root/'archives').glob('*.part')))

    def test_backup_creation_api_is_only_for_system_and_full_admins_and_returns_no_archive(self):
        self.client.force_login(self.learning)
        self.assertEqual(self.client.post('/api/auth/system/backups/', '{}', content_type='application/json').status_code, 403)
        self.client.force_login(self.owner)
        response = self.client.post('/api/auth/system/backups/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 202)
        self.assertTrue(backup_status()['queued'])
        self.assertNotIn('key', response.json())

    def test_retention_removes_only_old_managed_archives_after_success(self):
        other = self.root/'archives'/'manual-file.txt'
        other.parent.mkdir(parents=True); other.write_text('keep')
        copies = [create_backup() for _ in range(3)]
        self.assertEqual(len(list(other.parent.glob('btbs-*.lmsbak'))), 2)
        self.assertFalse(copies[0].exists())
        self.assertTrue(copies[-1].exists())
        self.assertTrue(other.exists())
