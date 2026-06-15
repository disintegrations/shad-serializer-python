import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from examples import account_chat


class FakeClient:
    def __init__(self):
        self.contacts = [
            {"user_guid": "u2", "first_name": "", "last_name": "", "username": "beta"},
            {"user_guid": "u1", "first_name": "Alice", "last_name": "Example"},
        ]
        self.message_results = [
            {
                "messages": [
                    {"message_id": "2", "author_object_guid": "u1", "time": "2", "text": "second"},
                    {"message_id": "1", "author_object_guid": "me", "time": "1", "text": "first"},
                ]
            },
            {
                "messages": [
                    {"message_id": "3", "author_object_guid": "u1", "time": "3", "text": "new"},
                    {"message_id": "2", "author_object_guid": "u1", "time": "2", "text": "second"},
                ]
            },
        ]
        self.sent_messages = []
        self.sent_files = []
        self.added = []
        self.logged_out = False
        self.saved = None
        self.registered = False
        self.closed = False

    def get_contacts(self):
        return {"users": self.contacts}

    def get_messages(self, _object_guid):
        if len(self.message_results) > 1:
            return self.message_results.pop(0)
        return self.message_results[0]

    def send_message(self, object_guid, text):
        self.sent_messages.append((object_guid, text))

    def send_file(self, object_guid, path):
        self.sent_files.append((object_guid, Path(path)))

    def add_address_book(self, phone, first_name, last_name):
        self.added.append((phone, first_name, last_name))
        return {"user": {"user_guid": "u3", "first_name": first_name, "last_name": last_name}}

    def send_code(self, phone):
        self.phone = phone
        return {"phone_code_hash": "hash"}

    def sign_in(self, phone, phone_code_hash, code):
        self.sign_in_args = (phone, phone_code_hash, code)

    def register_device(self):
        self.registered = True

    def save_state(self, path):
        self.saved = Path(path)
        self.saved.write_text("state", encoding="utf-8")

    def logout(self):
        self.logged_out = True

    def close(self):
        self.closed = True


def scripted_input(values):
    iterator = iter(values)
    return lambda _prompt="": next(iterator)


class AccountChatExampleTests(unittest.TestCase):
    def test_contact_name_and_message_formatting(self):
        contact = {"user_guid": "u1", "first_name": "Alice", "last_name": "Example"}
        self.assertEqual(account_chat.contact_name(contact), "Alice Example")
        self.assertEqual(
            account_chat.contact_name({"user_guid": "u2", "first_name": None, "last_name": None}),
            "u2",
        )
        self.assertIn(
            "Alice Example: hello",
            account_chat.format_message(
                {"author_object_guid": "u1", "text": "hello", "time": "1"},
                contact,
            ),
        )
        self.assertIn(
            "[file: report.pdf]",
            account_chat.format_message(
                {"author_object_guid": "me", "file_inline": {"file_name": "report.pdf"}},
                contact,
            ),
        )

    def test_contact_selection_and_add(self):
        client = FakeClient()
        output = []
        selected = account_chat.choose_contact(client, scripted_input(["1"]), output.append)
        self.assertEqual(selected["user_guid"], "u1")
        self.assertEqual(output[0], "1. Alice Example")

        added = account_chat.add_contact(
            client,
            scripted_input(["10000000000", "New", "Contact"]),
            output.append,
        )
        self.assertEqual(added["user_guid"], "u3")
        self.assertEqual(client.added, [("10000000000", "New", "Contact")])

    def test_chat_text_file_refresh_and_back(self):
        client = FakeClient()
        output = []
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "file.txt"
            file_path.write_text("example", encoding="utf-8")
            account_chat.chat_loop(
                client,
                client.contacts[1],
                scripted_input(["/refresh", "hello", f"/file {file_path}", "/back"]),
                output.append,
            )

        self.assertEqual(client.sent_messages, [("u1", "hello")])
        self.assertEqual(client.sent_files[0][0], "u1")
        self.assertEqual(sum("second" in line for line in output), 1)
        self.assertEqual(sum("new" in line for line in output), 1)

    def test_login_creates_state_and_reuses_existing_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            fresh = FakeClient()
            with patch.object(account_chat, "ShadClient", return_value=fresh):
                result = account_chat.login(
                    state_path,
                    scripted_input(["10000000000"]),
                    scripted_input(["123456"]),
                    lambda _line: None,
                )
            self.assertIs(result, fresh)
            self.assertTrue(fresh.registered)
            self.assertEqual(fresh.sign_in_args, ("10000000000", "hash", "123456"))
            self.assertTrue(state_path.exists())

            loaded = FakeClient()
            with patch.object(account_chat.ShadClient, "load_state", return_value=loaded) as load_state:
                result = account_chat.login(state_path, output=lambda _line: None)
            self.assertIs(result, loaded)
            load_state.assert_called_once_with(state_path)

    def test_failed_login_closes_new_client(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(account_chat, "ShadClient", return_value=client):
                with self.assertRaises(RuntimeError):
                    account_chat.login(
                        Path(directory) / "nested" / "state.json",
                        lambda _prompt: (_ for _ in ()).throw(RuntimeError("failed")),
                        output=lambda _line: None,
                    )
        self.assertTrue(client.closed)

    def test_logout_removes_state_after_confirmation(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text("state", encoding="utf-8")
            result = account_chat.logout(client, state_path, scripted_input(["yes"]), lambda _line: None)
        self.assertTrue(result)
        self.assertTrue(client.logged_out)
        self.assertFalse(state_path.exists())


if __name__ == "__main__":
    unittest.main()
