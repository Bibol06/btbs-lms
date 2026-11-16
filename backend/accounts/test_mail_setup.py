from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
import smtplib

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings
from dotenv import dotenv_values


class GmailSetupTests(SimpleTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)/'backend'; self.base.mkdir()
        self.env = self.base/'.env'
        self.env.write_text('DJANGO_SECRET_KEY=unchanged\nMEDIA_S3_SECRET_KEY=preserve-this\n', encoding='utf-8')
        self.settings_context = override_settings(BASE_DIR=self.base)
        self.settings_context.enable(); self.addCleanup(self.settings_context.disable)

    def test_success_tests_own_mailbox_and_preserves_existing_secrets(self):
        output = StringIO()
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty', return_value=True), \
                patch('accounts.management.commands.configure_gmail_mail.getpass.getpass', return_value='abcd efgh ijkl mnop'), \
                patch('accounts.management.commands.configure_gmail_mail.EmailBackend') as connection, \
                patch('accounts.management.commands.configure_gmail_mail.EmailMessage') as message:
            message.return_value.send.return_value = 1
            call_command('configure_gmail_mail', sender='sender@gmail.com', stdout=output)
            self.assertEqual(message.call_args.args[3], ['sender@gmail.com'])
            self.assertEqual(connection.call_args.kwargs['password'], 'abcdefghijklmnop')
        values = dotenv_values(self.env)
        self.assertEqual(values['EMAIL_HOST_PASSWORD'], 'abcdefghijklmnop')
        self.assertEqual(values['EMAIL_HOST'], 'smtp.gmail.com')
        self.assertEqual(values['MEDIA_S3_SECRET_KEY'], 'preserve-this')
        self.assertNotIn('abcdefghijklmnop', output.getvalue())
        self.assertTrue((self.base.parent/'.local/mail-configured.json').is_file())

    def test_rejected_authentication_does_not_enable_broken_smtp(self):
        before = self.env.read_bytes()
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty', return_value=True), \
                patch('accounts.management.commands.configure_gmail_mail.getpass.getpass', return_value='invalidsecret123'), \
                patch('accounts.management.commands.configure_gmail_mail.EmailBackend', side_effect=smtplib.SMTPAuthenticationError(535,b'rejected')):
            with self.assertRaises(CommandError): call_command('configure_gmail_mail', sender='sender@gmail.com', stdout=StringIO())
        self.assertEqual(self.env.read_bytes(), before)
        self.assertFalse((self.base.parent/'.local/mail-configured.json').exists())

    def test_quit_error_after_acceptance_does_not_report_delivery_as_failed(self):
        output = StringIO()
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty', return_value=True), \
                patch('accounts.management.commands.configure_gmail_mail.getpass.getpass', return_value='abcdefghijklmnop'), \
                patch('accounts.management.commands.configure_gmail_mail.EmailBackend') as connection, \
                patch('accounts.management.commands.configure_gmail_mail.EmailMessage') as message:
            message.return_value.send.return_value = 1
            connection.return_value.close.side_effect = TimeoutError('private-server-text')
            call_command('configure_gmail_mail', sender='sender@gmail.com', stdout=output)
        self.assertEqual(dotenv_values(self.env)['EMAIL_BACKEND'], 'django.core.mail.backends.smtp.EmailBackend')
        self.assertTrue((self.base.parent/'.local/mail-configured.json').is_file())
        self.assertNotIn('private-server-text', output.getvalue())

    def test_transport_failure_falls_back_to_other_encrypted_port(self):
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty', return_value=True), \
                patch('accounts.management.commands.configure_gmail_mail.getpass.getpass', return_value='abcdefghijklmnop'), \
                patch('accounts.management.commands.configure_gmail_mail.EmailBackend', side_effect=[TimeoutError('private-text'), MagicMock()]) as connection, \
                patch('accounts.management.commands.configure_gmail_mail.EmailMessage') as message:
            message.return_value.send.return_value = 1
            call_command('configure_gmail_mail', sender='sender@gmail.com', stdout=StringIO())
        self.assertEqual([call.kwargs['port'] for call in connection.call_args_list], [465, 587])
        values = dotenv_values(self.env)
        self.assertEqual((values['EMAIL_PORT'], values['EMAIL_USE_TLS'], values['EMAIL_USE_SSL']), ('587','True','False'))

    def test_authentication_diagnostic_contains_only_safe_codes_and_does_not_retry(self):
        output = StringIO(); before = self.env.read_bytes()
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty', return_value=True), \
                patch('accounts.management.commands.configure_gmail_mail.getpass.getpass', return_value='abcdefghijklmnop'), \
                patch('accounts.management.commands.configure_gmail_mail.EmailBackend', side_effect=smtplib.SMTPAuthenticationError(535,b'5.7.8 private-auth-data')) as connection:
            with self.assertRaises(CommandError) as result:
                call_command('configure_gmail_mail', sender='sender@gmail.com', stdout=output)
        self.assertEqual(connection.call_count, 1)
        self.assertIn('535', str(result.exception)); self.assertIn('5.7.8', str(result.exception))
        diagnostic = (self.base.parent/'.local/mail-setup-diagnostic.json').read_text(encoding='utf-8')
        for secret in ['private-auth-data','abcdefghijklmnop','sender@gmail.com']:
            self.assertNotIn(secret, diagnostic + str(result.exception))
        self.assertEqual(self.env.read_bytes(), before)

    def test_refusal_during_send_does_not_retry_and_preserves_settings(self):
        before = self.env.read_bytes()
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty', return_value=True), \
                patch('accounts.management.commands.configure_gmail_mail.getpass.getpass', return_value='abcdefghijklmnop'), \
                patch('accounts.management.commands.configure_gmail_mail.EmailBackend') as connection, \
                patch('accounts.management.commands.configure_gmail_mail.EmailMessage') as message:
            message.return_value.send.side_effect = smtplib.SMTPDataError(550,b'5.7.1 private-message')
            with self.assertRaises(CommandError) as result:
                call_command('configure_gmail_mail', sender='sender@gmail.com', stdout=StringIO())
        self.assertEqual(connection.call_count, 1)
        self.assertIn('550', str(result.exception)); self.assertNotIn('private-message', str(result.exception))
        self.assertEqual(self.env.read_bytes(), before)

    def test_timeout_during_send_does_not_automatically_duplicate_the_message(self):
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty', return_value=True), \
                patch('accounts.management.commands.configure_gmail_mail.getpass.getpass', return_value='abcdefghijklmnop'), \
                patch('accounts.management.commands.configure_gmail_mail.EmailBackend') as connection, \
                patch('accounts.management.commands.configure_gmail_mail.EmailMessage') as message:
            message.return_value.send.side_effect = TimeoutError('private-data')
            with self.assertRaises(CommandError):
                call_command('configure_gmail_mail', sender='sender@gmail.com', stdout=StringIO())
        self.assertEqual(connection.call_count,1)
        self.assertFalse((self.base.parent/'.local/mail-configured.json').exists())

    def test_noninteractive_execution_cannot_collect_a_password(self):
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty', return_value=False):
            with self.assertRaises(CommandError): call_command('configure_gmail_mail', sender='sender@gmail.com', stdout=StringIO())

    def test_masked_window_pipe_passes_code_without_using_console_or_printing_it(self):
        output=StringIO()
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty', return_value=False), \
                patch('accounts.management.commands.configure_gmail_mail.sys.stdin.readline', return_value='abcd\u200eefgh ijkl mnop\n'), \
                patch('accounts.management.commands.configure_gmail_mail.getpass.getpass') as console, \
                patch('accounts.management.commands.configure_gmail_mail.EmailBackend') as connection, \
                patch('accounts.management.commands.configure_gmail_mail.EmailMessage') as message:
            message.return_value.send.return_value=1
            call_command('configure_gmail_mail',sender='sender@gmail.com',password_stdin=True,stdout=output)
            console.assert_not_called()
            self.assertEqual(connection.call_args.kwargs['password'],'abcdefghijklmnop')
        self.assertNotIn('abcdefghijklmnop',output.getvalue())

    def test_redirected_input_cannot_be_used_as_a_visible_terminal_password_prompt(self):
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty', return_value=True):
            with self.assertRaises(CommandError):
                call_command('configure_gmail_mail',sender='sender@gmail.com',password_stdin=True,stdout=StringIO())

    def test_short_pasted_code_reports_only_its_length_and_never_connects(self):
        with patch('accounts.management.commands.configure_gmail_mail.sys.stdin.isatty',return_value=False), \
                patch('accounts.management.commands.configure_gmail_mail.sys.stdin.readline',return_value='123456\n'), \
                patch('accounts.management.commands.configure_gmail_mail.EmailBackend') as connection:
            with self.assertRaises(CommandError) as error:
                call_command('configure_gmail_mail',sender='sender@gmail.com',password_stdin=True,stdout=StringIO())
        connection.assert_not_called()
        self.assertIn('6',str(error.exception)); self.assertNotIn('123456',str(error.exception))

    def test_recovery_send_keeps_success_when_disconnect_fails(self):
        from accounts.mail_setup import send_recovery_mail
        with patch('accounts.mail_setup.get_connection') as get_connection, patch('accounts.mail_setup.EmailMessage') as message:
            message.return_value.send.return_value = 1
            get_connection.return_value.close.side_effect = TimeoutError('private-data')
            self.assertEqual(send_recovery_mail('Subject','Body','from@example.test',['to@example.test']),1)

    def test_recovery_send_keeps_original_auth_failure_when_disconnect_also_fails(self):
        from accounts.mail_setup import send_recovery_mail
        with patch('accounts.mail_setup.get_connection') as get_connection:
            get_connection.return_value.open.side_effect = smtplib.SMTPAuthenticationError(535,b'rejected')
            get_connection.return_value.close.side_effect = TimeoutError('private-data')
            with self.assertRaises(smtplib.SMTPAuthenticationError):
                send_recovery_mail('Subject','Body','from@example.test',['to@example.test'])
