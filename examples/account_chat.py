"""Interactive terminal account manager and contact chat example."""

from __future__ import annotations

import argparse
from datetime import datetime
from getpass import getpass
from pathlib import Path
from typing import Any, Callable, Mapping

from shad_client import ShadClient

Input = Callable[[str], str]
Output = Callable[[str], None]

CHAT_HELP = """Chat commands:
  /refresh     load recent messages
  /file PATH   upload and send a file
  /help        show this help
  /back        return to the main menu
Any other non-empty input is sent as a text message."""


def contact_name(contact: Mapping[str, Any]) -> str:
    """Return a useful display name for a contact."""
    name_parts = (contact.get("first_name"), contact.get("last_name"))
    full_name = " ".join(str(part).strip() for part in name_parts if part and str(part).strip())
    if full_name:
        return full_name
    if contact.get("username"):
        return f"@{contact['username']}"
    return str(contact.get("phone") or contact.get("user_guid") or "Unknown contact")


def format_message(message: Mapping[str, Any], contact: Mapping[str, Any]) -> str:
    """Format one message for terminal output."""
    author_guid = message.get("author_object_guid")
    sender = contact_name(contact) if author_guid == contact.get("user_guid") else "You"
    content = str(message.get("text") or "")
    file_inline = message.get("file_inline")
    if isinstance(file_inline, Mapping):
        file_name = file_inline.get("file_name") or file_inline.get("type") or "file"
        content = f"[file: {file_name}]" + (f" {content}" if content else "")
    if not content:
        content = f"[{message.get('type', 'message')}]"

    timestamp = str(message.get("time") or "")
    if timestamp.isdigit():
        timestamp = datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
    return f"[{timestamp or 'unknown time'}] {sender}: {content}"


def message_sort_key(message: Mapping[str, Any]) -> tuple[int, int | str]:
    """Sort numeric Shad IDs chronologically and tolerate unexpected IDs."""
    message_id = str(message.get("message_id") or "")
    return (0, int(message_id)) if message_id.isdigit() else (1, message_id)


def show_messages(
    client: ShadClient,
    contact: Mapping[str, Any],
    shown_ids: set[str],
    output: Output = print,
) -> None:
    """Load recent messages and print messages not already displayed."""
    result = client.get_messages(str(contact["user_guid"]))
    messages = result.get("messages", [])
    fresh = [message for message in messages if str(message.get("message_id")) not in shown_ids]
    fresh.sort(key=message_sort_key)
    if not fresh:
        output("No new messages.")
        return
    for message in fresh:
        output(format_message(message, contact))
        shown_ids.add(str(message.get("message_id")))


def chat_loop(
    client: ShadClient,
    contact: Mapping[str, Any],
    input_fn: Input = input,
    output: Output = print,
) -> None:
    """Open an interactive text/file chat with one contact."""
    output(f"\nChat with {contact_name(contact)}")
    output(CHAT_HELP)
    shown_ids: set[str] = set()
    show_messages(client, contact, shown_ids, output)

    while True:
        command = input_fn("> ").strip()
        if not command:
            continue
        if command == "/back":
            return
        if command == "/help":
            output(CHAT_HELP)
            continue
        if command == "/refresh":
            show_messages(client, contact, shown_ids, output)
            continue
        if command.startswith("/file "):
            path = Path(command[6:].strip()).expanduser()
            if not path.is_file():
                output(f"File not found: {path}")
                continue
            client.send_file(str(contact["user_guid"]), path)
            output(f"Sent file: {path.name}")
            continue
        if command.startswith("/"):
            output("Unknown command. Enter /help for available commands.")
            continue
        client.send_message(str(contact["user_guid"]), command)
        output("Sent.")


def list_contacts(client: ShadClient, output: Output = print) -> list[dict[str, Any]]:
    """Load, sort, and display contacts."""
    contacts = list(client.get_contacts().get("users", []))
    contacts.sort(key=lambda contact: contact_name(contact).lstrip("@").casefold())
    if not contacts:
        output("No contacts found.")
        return contacts
    for index, contact in enumerate(contacts, start=1):
        output(f"{index}. {contact_name(contact)}")
    return contacts


def choose_contact(
    client: ShadClient,
    input_fn: Input = input,
    output: Output = print,
) -> dict[str, Any] | None:
    """Prompt the user to select one existing contact."""
    contacts = list_contacts(client, output)
    if not contacts:
        return None
    selected = input_fn("Contact number, or blank to cancel: ").strip()
    if not selected:
        return None
    try:
        return contacts[int(selected) - 1]
    except (ValueError, IndexError):
        output("Invalid contact number.")
        return None


def add_contact(
    client: ShadClient,
    input_fn: Input = input,
    output: Output = print,
) -> dict[str, Any] | None:
    """Prompt for a phone/name and add it to the Shad address book."""
    phone = input_fn("Phone number with country code, without +: ").strip()
    first_name = input_fn("First name: ").strip()
    last_name = input_fn("Last name (optional): ").strip()
    if not phone or not first_name:
        output("Phone number and first name are required.")
        return None
    result = client.add_address_book(phone, first_name, last_name)
    contact = result.get("user")
    if not isinstance(contact, dict):
        output("The contact was not returned by Shad.")
        return None
    output(f"Added contact: {contact_name(contact)}")
    return contact


def login(
    state_path: Path,
    input_fn: Input = input,
    getpass_fn: Input = getpass,
    output: Output = print,
) -> ShadClient:
    """Load an existing state or perform a guided SMS login."""
    if state_path.exists():
        output(f"Loading session from {state_path}")
        return ShadClient.load_state(state_path)

    client = ShadClient()
    try:
        phone = input_fn("Phone number with country code, without +: ").strip()
        sent = client.send_code(phone)
        code = getpass_fn("SMS code: ").strip()
        client.sign_in(phone, str(sent["phone_code_hash"]), code)
        client.register_device()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        client.save_state(state_path)
        output(f"Session saved to {state_path}")
        return client
    except BaseException:
        client.close()
        raise


def logout(
    client: ShadClient,
    state_path: Path,
    input_fn: Input = input,
    output: Output = print,
) -> bool:
    """Confirm logout, revoke the remote session, and remove local state."""
    if input_fn("Logout and delete the saved session? [y/N]: ").strip().lower() not in {"y", "yes"}:
        output("Logout canceled.")
        return False
    client.logout()
    state_path.unlink(missing_ok=True)
    output("Logged out and removed local session state.")
    return True


def main_menu(
    client: ShadClient,
    state_path: Path,
    input_fn: Input = input,
    output: Output = print,
) -> None:
    """Run the account/contact menu until exit or logout."""
    while True:
        output("\n1. List contacts\n2. Chat with contact\n3. Add contact and chat\n4. Logout\n5. Exit")
        choice = input_fn("Choose: ").strip()
        try:
            if choice == "1":
                list_contacts(client, output)
            elif choice == "2":
                contact = choose_contact(client, input_fn, output)
                if contact:
                    chat_loop(client, contact, input_fn, output)
            elif choice == "3":
                contact = add_contact(client, input_fn, output)
                if contact:
                    chat_loop(client, contact, input_fn, output)
            elif choice == "4":
                if logout(client, state_path, input_fn, output):
                    return
            elif choice == "5":
                return
            else:
                output("Invalid choice.")
        except Exception as error:
            output(f"Error: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path("shad-state.json"), help="session state path")
    args = parser.parse_args()

    client: ShadClient | None = None
    try:
        client = login(args.state)
        main_menu(client, args.state)
    except (EOFError, KeyboardInterrupt):
        print("\nExiting. The saved session was preserved.")
    except Exception as error:
        print(f"Error: {error}")
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()
