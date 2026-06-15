# API Reference

The client is synchronous and returns decoded Python dictionaries.

## Client lifecycle

```python
from shad_client import ShadClient

with ShadClient.load_state("shad-state.json") as client:
    chats = client.get_chats()
```

`close()` closes the underlying `requests.Session`.

## Authentication

- `send_code(phone_number, send_type="SMS")`
- `sign_in(phone_number, phone_code_hash, phone_code)`
- `register_device(device_hash="python-shad-client")`
- `logout()`
- `save_state(path)`
- `ShadClient.load_state(path)`
- `get_unconfirmed_sessions()`

## Generic calls

### `call(method, input_data=None, **options)`

Builds, encrypts, signs, and sends a messenger API request. Returns the complete
response envelope.

### `call_data(method, input_data=None, **options)`

Calls `call()`, checks that the response status is `OK`, and returns the
response's `data` dictionary.

### `call_plain(url, method, input_data=None, ...)`

Calls an unencrypted JSON service endpoint.

## Chats and messages

- `get_chats(start_id=None)`
- `get_chats_updates(state)`
- `get_chat_ads()`
- `set_chat_use_time(object_guid, time)`
- `get_messages(object_guid, max_id=None, sort="FromMax")`
- `get_messages_interval(object_guid, middle_message_id)`
- `get_messages_by_id(object_guid, message_ids)`
- `get_messages_updates(object_guid, state)`
- `send_message(object_guid, text)`
- `seen_chats(seen_list)`
- `send_chat_activity(object_guid, activity="Typing")`

## Files

- `upload_file(path, file_type="File")`
- `send_file(object_guid, path, file_type="File", caption=None)`
- `download_file(file_inline, destination, storage_url=None)`
- `discover_dcs()`
- `get_storage_url(dc_id)`

`file_inline` is the dictionary returned by `upload_file()` or included in a
file message.

## Users, contacts, and channels

- `get_user_info(user_guid)`
- `get_service_info(service_guid)`
- `get_object_by_username(username)`
- `get_related_objects(object_guid)`
- `get_contacts()`
- `get_contacts_updates(state)`
- `add_address_book(phone, first_name, last_name="")`
- `get_contacts_last_online(user_guids)`
- `get_channel_info(channel_guid)`
- `join_channel(channel_guid)`
- `leave_channel(channel_guid)`

## Other helpers

- `get_folders()`
- `get_suggested_folders()`
- `get_user_setting()`
- `get_my_sticker_sets()`
- `get_barcode_action(barcode, action_type="settings")`

## Errors

Methods raise:

- `ShadError` for protocol or Shad API failures.
- `requests` exceptions for HTTP and network failures.
- Standard filesystem exceptions for state and file operations.

## Interactive Example

`examples/account_chat.py` demonstrates a complete terminal workflow around
the public API:

- Load an existing state file or perform SMS login and device registration.
- List and select contacts.
- Add contacts with `add_address_book()`.
- Display recent messages and manually refresh them.
- Send text and files.
- Revoke the remote session with `logout()` and remove local state.
