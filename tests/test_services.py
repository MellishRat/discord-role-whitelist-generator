import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from csv_loader import load_members_csv
from profile_manager import Profile, SftpSettings, load_profile, save_profile
from whitelist_rules import OutputRule
from sftp_uploader import upload_lists
import paramiko


class CsvTests(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "members.csv"
            path.write_text(text, encoding="utf-8")
            return load_members_csv(path)

    def test_bom_commas_unicode_and_literal_na(self):
        df = self.read('\ufeffNickname,Role\n"Zoë, Jr",NA\n')
        self.assertEqual(df.iloc[0].tolist(), ["Zoë, Jr", "NA"])

    def test_bad_exports_explain_problem(self):
        cases = [("", "empty"), ("Name,Name\na,b\n", "Duplicate"),
                 ("Name,\na,b\n", "blank"), ("Name,Role\na\n", "line 2"),
                 ("Name,Role\na,b,c\n", "line 2"), ("Name,Role\n", "no members"),
                 ('Name,Role\n"unclosed,b', "Malformed"),
                 ('Name,Role\n"two\nlines",x\n', "multiline")]
        for text, message in cases:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                self.read(text)

    def test_invalid_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            path.write_bytes(b"Name,Role\n\xff,x")
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                load_members_csv(path)


class ProfileTests(unittest.TestCase):
    def test_roundtrip_and_no_password(self):
        profile = Profile(outputs=[OutputRule("out", ["Verified"])], sftp=SftpSettings(host="example.test"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            save_profile(path, profile)
            self.assertEqual(load_profile(path), profile)
            self.assertNotIn("password", path.read_text())

    def test_bundled_profiles(self):
        for path in (Path(__file__).resolve().parents[1] / "examples").glob("*.json"):
            with self.subTest(path=path):
                self.assertTrue(load_profile(path).outputs)


class SftpTests(unittest.TestCase):
    def setUp(self):
        self.settings = SftpSettings(True, "example.test", 22, "user", "/")
        self.connection = Mock()
        self.transport = Mock()
        self.sftp = Mock()
        self.stack = __import__("contextlib").ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("sftp_uploader.socket.create_connection", return_value=self.connection))
        self.stack.enter_context(patch("sftp_uploader.paramiko.Transport", return_value=self.transport))
        self.stack.enter_context(patch("sftp_uploader.paramiko.SFTPClient.from_transport", return_value=self.sftp))

    def test_upload_rewrites_local_file_and_uses_snapshot(self):
        progress = Mock()
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder) / "list.txt"
            local.write_text("old")
            upload_lists(self.settings, "secret", {"list.txt": ["new", "Zoë"]}, folder, progress)
            self.assertEqual(local.read_text(encoding="utf-8"), "new\nZoë")
            self.sftp.put.assert_called_once_with(str(local), "/list.txt")
        progress.assert_called_once_with("Uploaded list.txt")
        self.sftp.close.assert_called_once()
        self.transport.close.assert_called_once()

    def test_auth_failure_closes_transport_and_hides_password(self):
        self.transport.connect.side_effect = paramiko.AuthenticationException("secret")
        with self.assertRaisesRegex(RuntimeError, "Authentication failed") as error:
            upload_lists(self.settings, "secret", {}, ".")
        self.assertNotIn("secret", str(error.exception))
        self.transport.close.assert_called_once()

    def test_transfer_failure_has_path_and_closes_resources(self):
        self.sftp.put.side_effect = PermissionError()
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(RuntimeError, "uploading /list.txt"):
            upload_lists(self.settings, "secret", {"list.txt": []}, folder)
        self.sftp.close.assert_called_once()
        self.transport.close.assert_called_once()

    def test_invalid_port(self):
        self.settings.port = 0
        with self.assertRaisesRegex(ValueError, "port"):
            upload_lists(self.settings, "secret", {}, ".")
