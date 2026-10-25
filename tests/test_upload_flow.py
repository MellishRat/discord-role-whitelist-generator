"""Exercise the GUI/controller boundary without creating a Tk window."""
import threading
import unittest
from queue import Queue
from unittest.mock import Mock, patch
import pandas as pd
from discord_role_whitelist_generator import WhitelistGeneratorApp
from whitelist_rules import OutputRule
from profile_manager import SftpSettings


class UploadFlowTests(unittest.TestCase):
    def app(self):
        app = WhitelistGeneratorApp.__new__(WhitelistGeneratorApp)
        values = dict(sftp_enabled=True, sftp_host="example.test", sftp_port=22,
                      sftp_username="user", sftp_remote_path="/lists", output_folder="output",
                      name_column="Nickname", dedupe_names=True, sort_names=True)
        for name, value in values.items():
            setattr(app, name, Mock(get=Mock(return_value=value)))
        app._upload_active = False
        app._upload_events = Queue()
        app.status = Mock()
        app.root = Mock()
        app.df = pd.DataFrame({"Nickname": ["current"], "Role": ["yes"]})
        app.output_rules = [OutputRule("out", ["Role"])]
        app.generated_content = {"out.txt": ["stale"]}
        return app

    @patch("discord_role_whitelist_generator.threading.Thread")
    @patch("discord_role_whitelist_generator.simpledialog.askstring", return_value="password")
    def test_upload_regenerates_even_after_preview(self, ask, thread):
        app = self.app()
        app.upload_sftp()
        settings, password, content, folder = thread.call_args.kwargs["args"]
        self.assertEqual(content, {"out.txt": ["current"]})
        app.df.loc[0, "Nickname"] = "edited later"
        app.output_rules.clear()
        self.assertEqual(content, {"out.txt": ["current"]})
        self.assertEqual(settings.host, "example.test")
        thread.return_value.start.assert_called_once()

    @patch("discord_role_whitelist_generator.upload_lists")
    @patch("discord_role_whitelist_generator.messagebox")
    def test_worker_queues_and_main_loop_updates_ui(self, dialogs, upload):
        app = self.app()
        app._upload_active = True
        upload.side_effect = lambda settings, password, content, folder, progress: progress("Uploaded out.txt")
        worker = threading.Thread(target=app._upload_sftp_worker,
                                  args=(SftpSettings(), "password", {"out.txt": []}, "output"))
        worker.start()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        app.status.set.assert_not_called()
        dialogs.showinfo.assert_not_called()
        for field in (app.sftp_host, app.sftp_port, app.output_folder):
            field.get.assert_not_called()
        app._poll_upload_events()
        self.assertFalse(app._upload_active)
        app.status.set.assert_any_call("Uploaded out.txt")
        dialogs.showinfo.assert_called_once()
        app.root.after.assert_called_once()

    @patch("discord_role_whitelist_generator.upload_lists", side_effect=RuntimeError("connection failed"))
    @patch("discord_role_whitelist_generator.messagebox")
    def test_worker_failure_is_delivered_on_event_loop(self, dialogs, upload):
        app = self.app()
        app._upload_sftp_worker(SftpSettings(), "password", {}, "output")
        dialogs.showerror.assert_not_called()
        app._poll_upload_events()
        dialogs.showerror.assert_called_once_with("SFTP Upload Error", "connection failed")
