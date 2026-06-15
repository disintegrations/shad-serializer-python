"""Synchronous HTTP client for Shad Messenger."""

from __future__ import annotations

import base64
import json
import math
import os
import secrets
from pathlib import Path
from typing import Any, Mapping

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding
from cryptography.hazmat.primitives.asymmetric import rsa

from .protocol import decrypt_data, encrypt_data, transform_v6


DEFAULT_API_URL = "https://shadmessenger2.iranlms.ir"
GET_DCS_URL = "https://shgetdcmess.iranlms.ir"
BARCODE_URL = "https://shbarcode.iranlms.ir/"
FILE_CHUNK_SIZE = 128 * 1024


class ShadError(RuntimeError):
    pass


class ShadClient:
    """Synchronous client for encrypted Shad HTTP APIs."""

    def __init__(
        self,
        *,
        auth: str | None = None,
        private_key_pem: str | None = None,
        api_url: str = DEFAULT_API_URL,
        api_version: str = "6",
        app_version: str = "4.4.26",
        language: str = "fa",
        timeout: float = 20,
        session: requests.Session | None = None,
    ) -> None:
        self.auth = auth
        self.private_key_pem = private_key_pem
        self.api_url = api_url
        self.api_version = api_version
        self.app_version = app_version
        self.language = language
        self.timeout = timeout
        self.tmp_session = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(32))
        self.session = session or requests.Session()
        self.dcs: dict[str, Any] = {}

    def __enter__(self) -> ShadClient:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()

    @property
    def client_info(self) -> dict[str, str]:
        return {
            "app_name": "Main",
            "app_version": self.app_version,
            "platform": "Web",
            "package": "web.shad.ir",
            "lang_code": self.language,
        }

    def call(
        self,
        method: str,
        input_data: Mapping[str, Any] | None = None,
        *,
        not_authorized: bool = False,
        api_version: str | None = None,
    ) -> dict[str, Any]:
        version = api_version or self.api_version
        secret = self.tmp_session if not_authorized else self.auth
        if not secret:
            raise ShadError("This method needs auth. Call sign_in() or load_state() first.")

        inner = {
            "method": method,
            "input": dict(input_data or {}),
            "client": self.client_info,
        }
        outer: dict[str, Any] = {
            "api_version": version,
            "data_enc": encrypt_data(inner, secret),
        }

        if not_authorized:
            outer["tmp_session"] = self.tmp_session
        elif version == "6":
            if not self.private_key_pem:
                raise ShadError("API v6 authorized calls require the private key created during sign-in")
            outer["auth"] = transform_v6(self.auth or "")
            outer["sign"] = self._sign(outer["data_enc"])
        else:
            outer["auth"] = self.auth

        response = self.session.post(
            self.api_url,
            data=json.dumps(outer, separators=(",", ":")),
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "text/plain",
                "Origin": "https://web.shad.ir",
                "Referer": "https://web.shad.ir/",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("data_enc"):
            return decrypt_data(result["data_enc"], secret)
        return result

    def call_data(
        self,
        method: str,
        input_data: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call an API method and return its unwrapped `data` object."""
        result = self.call(method, input_data, **kwargs)
        if result.get("status") != "OK":
            detail = result.get("status_det") or result.get("status") or "UNKNOWN_ERROR"
            raise ShadError(f"{method} failed: {detail}")
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    def call_plain(
        self,
        url: str,
        method: str,
        input_data: Mapping[str, Any] | None = None,
        *,
        api_version: str = "0",
        authorized: bool = True,
    ) -> dict[str, Any]:
        """Call one of Shad's unencrypted JSON service endpoints."""
        payload: dict[str, Any] = {
            "api_version": api_version,
            "method": method,
            "data": dict(input_data or {}),
            "client": self.client_info,
        }
        if authorized:
            if not self.auth:
                raise ShadError("This service method requires auth")
            payload["auth"] = self.auth
        response = self.session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        if result.get("status") != "OK":
            raise ShadError(f"{method} failed: {result.get('status_det', result.get('status'))}")
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    def send_code(self, phone_number: str, send_type: str = "SMS") -> dict[str, Any]:
        return self.call_data(
            "sendCode",
            {"phone_number": phone_number, "send_type": send_type},
            not_authorized=True,
            api_version="6",
        )

    def sign_in(self, phone_number: str, phone_code_hash: str, phone_code: str) -> dict[str, Any]:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        public_key = transform_v6(base64.b64encode(public_pem.encode("ascii")).decode("ascii"))

        result = self.call_data(
            "signIn",
            {
                "phone_number": phone_number,
                "phone_code_hash": phone_code_hash,
                "phone_code": phone_code,
                "public_key": public_key,
            },
            not_authorized=True,
            api_version="6",
        )
        encrypted_auth = base64.b64decode(result["auth"])
        auth = private_key.decrypt(
            encrypted_auth,
            asymmetric_padding.OAEP(
                mgf=asymmetric_padding.MGF1(algorithm=hashes.SHA1()),
                algorithm=hashes.SHA1(),
                label=None,
            ),
        ).decode("utf-8")
        self.auth = auth
        self.private_key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii")
        result["auth"] = auth
        return result

    def register_device(self, device_hash: str = "python-shad-client") -> dict[str, Any]:
        return self.call_data(
            "registerDevice",
            {
                "token_type": "Web",
                "token": "",
                "app_version": f"WB_{self.app_version}",
                "lang_code": self.language,
                "system_version": "Python",
                "device_model": "Python requests",
                "device_hash": device_hash,
            },
        )

    def logout(self) -> dict[str, Any]:
        """Revoke the current Shad session."""
        return self.call_data("logout", {})

    def get_chats(self, start_id: str | None = None) -> dict[str, Any]:
        return self.call_data("getChats", {"start_id": start_id} if start_id is not None else {})

    def get_messages(
        self,
        object_guid: str,
        *,
        max_id: str | None = None,
        sort: str = "FromMax",
    ) -> dict[str, Any]:
        input_data: dict[str, Any] = {
            "object_guid": object_guid,
            "sort": sort,
        }
        if max_id is not None:
            input_data["max_id"] = max_id
        return self.call_data(
            "getMessages",
            input_data,
        )

    def send_message(self, object_guid: str, text: str) -> dict[str, Any]:
        return self.call_data(
            "sendMessage",
            {"object_guid": object_guid, "text": text, "rnd": str(secrets.randbelow(1_000_000) + 1)},
        )

    def send_file(
        self,
        object_guid: str,
        path: str | Path,
        *,
        file_type: str = "File",
        caption: str | None = None,
    ) -> dict[str, Any]:
        file_inline = self.upload_file(path, file_type=file_type)
        input_data: dict[str, Any] = {
            "object_guid": object_guid,
            "rnd": str(secrets.randbelow(1_000_000) + 1),
            "file_inline": file_inline,
        }
        if caption:
            input_data["text"] = caption
        return self.call_data("sendMessage", input_data)

    def upload_file(self, path: str | Path, *, file_type: str = "File") -> dict[str, Any]:
        """Upload a file and return a `file_inline` object suitable for sendMessage."""
        if not self.auth:
            raise ShadError("File upload requires auth")
        file_path = Path(path)
        size = file_path.stat().st_size
        mime = file_path.suffix.lstrip(".").lower() or "file"
        request = self.call_data(
            "requestSendFile",
            {"file_name": file_path.name, "size": size, "mime": mime},
        )
        total_parts = max(1, math.ceil(size / FILE_CHUNK_SIZE))
        access_hash_rec = ""

        with file_path.open("rb") as source:
            for part_number in range(1, total_parts + 1):
                chunk = source.read(FILE_CHUNK_SIZE)
                response = self.session.post(
                    request["upload_url"],
                    data=chunk,
                    headers={
                        "access-hash-send": request["access_hash_send"],
                        "auth": self.auth,
                        "file-id": str(request["id"]),
                        "part-number": str(part_number),
                        "total-part": str(total_parts),
                        "chunk-size": str(len(chunk)),
                        "Origin": "https://web.shad.ir",
                        "Referer": "https://web.shad.ir/",
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()
                if result.get("status_det") != "OK":
                    raise ShadError(f"File upload failed: {result.get('status_det', 'UNKNOWN_ERROR')}")
                access_hash_rec = (result.get("data") or {}).get("access_hash_rec", access_hash_rec)

        if not access_hash_rec:
            raise ShadError("File upload completed without an access_hash_rec")
        return {
            "dc_id": str(request["dc_id"]),
            "file_id": str(request["id"]),
            "type": file_type,
            "file_name": file_path.name,
            "size": size,
            "mime": mime,
            "access_hash_rec": access_hash_rec,
        }

    def download_file(
        self,
        file_inline: Mapping[str, Any],
        destination: str | Path,
        *,
        storage_url: str | None = None,
    ) -> Path:
        """Download a `file_inline` object to disk using Shad's ranged file API."""
        if not self.auth:
            raise ShadError("File download requires auth")
        url = storage_url or self.get_storage_url(str(file_inline["dc_id"]))
        size = int(file_inline["size"])
        destination_path = Path(destination)
        with destination_path.open("wb") as output:
            for start in range(0, size, FILE_CHUNK_SIZE + 1):
                last = min(start + FILE_CHUNK_SIZE, size - 1)
                response = self.session.post(
                    url if url.endswith("/GetFile.ashx") else f"{url.rstrip('/')}/GetFile.ashx",
                    headers={
                        "access-hash-rec": str(file_inline["access_hash_rec"]),
                        "auth": self.auth,
                        "file-id": str(file_inline["file_id"]),
                        "start-index": str(start),
                        "last-index": str(last),
                        "Content-Type": "text/plain",
                        "Origin": "https://web.shad.ir",
                        "Referer": "https://web.shad.ir/",
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                output.write(response.content)
        return destination_path

    def discover_dcs(self) -> dict[str, Any]:
        payload = {
            "api_version": "4",
            "method": "getDCs",
            "client": self.client_info,
        }
        response = self.session.post(GET_DCS_URL, json=payload, timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        if result.get("status") != "OK":
            raise ShadError(f"getDCs failed: {result.get('status_det', result.get('status'))}")
        self.dcs = result.get("data") or {}
        if self.dcs.get("default_api_urls"):
            self.api_url = self.dcs["default_api_urls"][0]
        return self.dcs

    def get_storage_url(self, dc_id: str) -> str:
        if not self.dcs:
            self.discover_dcs()
        try:
            return self.dcs["storages"][str(dc_id)]
        except KeyError as error:
            raise ShadError(f"Storage DC {dc_id!r} was not returned by getDCs") from error

    def get_messages_interval(self, object_guid: str, middle_message_id: str | int) -> dict[str, Any]:
        return self.call_data(
            "getMessagesInterval",
            {"object_guid": object_guid, "middle_message_id": middle_message_id},
        )

    def get_messages_by_id(self, object_guid: str, message_ids: list[str]) -> dict[str, Any]:
        return self.call_data("getMessagesByID", {"object_guid": object_guid, "message_ids": message_ids})

    def get_messages_updates(self, object_guid: str, state: str | int) -> dict[str, Any]:
        return self.call_data("getMessagesUpdates", {"object_guid": object_guid, "state": state})

    def get_chats_updates(self, state: int) -> dict[str, Any]:
        return self.call_data("getChatsUpdates", {"state": state})

    def get_chat_ads(self) -> dict[str, Any]:
        return self.call_data("getChatAds", {})

    def set_chat_use_time(self, object_guid: str, time: int) -> dict[str, Any]:
        return self.call_data("setChatUseTime", {"object_guid": object_guid, "time": time})

    def seen_chats(self, seen_list: Mapping[str, str]) -> dict[str, Any]:
        return self.call_data("seenChats", {"seen_list": dict(seen_list)})

    def send_chat_activity(self, object_guid: str, activity: str = "Typing") -> dict[str, Any]:
        return self.call_data("sendChatActivity", {"object_guid": object_guid, "activity": activity})

    def get_user_info(self, user_guid: str) -> dict[str, Any]:
        return self.call_data("getUserInfo", {"user_guid": user_guid})

    def get_service_info(self, service_guid: str) -> dict[str, Any]:
        return self.call_data("getServiceInfo", {"service_guid": service_guid})

    def get_object_by_username(self, username: str) -> dict[str, Any]:
        return self.call_data("getObjectByUsername", {"username": username})

    def get_channel_info(self, channel_guid: str) -> dict[str, Any]:
        return self.call_data("getChannelInfo", {"channel_guid": channel_guid})

    def join_channel(self, channel_guid: str) -> dict[str, Any]:
        return self.call_data("joinChannelAction", {"channel_guid": channel_guid, "action": "Join"})

    def leave_channel(self, channel_guid: str) -> dict[str, Any]:
        return self.call_data("joinChannelAction", {"channel_guid": channel_guid, "action": "Leave"})

    def get_related_objects(self, object_guid: str) -> dict[str, Any]:
        return self.call_data("getRelatedObjects", {"object_guid": object_guid})

    def get_contacts(self) -> dict[str, Any]:
        return self.call_data("getContacts", {})

    def get_contacts_updates(self, state: int) -> dict[str, Any]:
        return self.call_data("getContactsUpdates", {"state": state})

    def add_address_book(self, phone: str, first_name: str, last_name: str = "") -> dict[str, Any]:
        return self.call_data(
            "addAddressBook",
            {"phone": phone, "first_name": first_name, "last_name": last_name},
        )

    def get_contacts_last_online(self, user_guids: list[str]) -> dict[str, Any]:
        return self.call_data("getContactsLastOnline", {"user_guids": user_guids})

    def get_folders(self) -> dict[str, Any]:
        return self.call_data("getFolders", {})

    def get_suggested_folders(self) -> dict[str, Any]:
        return self.call_data("getSuggestedFolders", {})

    def get_user_setting(self) -> dict[str, Any]:
        return self.call_data("getUserSetting", {})

    def get_unconfirmed_sessions(self) -> dict[str, Any]:
        return self.call_data("getUnconfirmedSessions", {})

    def get_my_sticker_sets(self) -> dict[str, Any]:
        return self.call_data("getMyStickerSets", {})

    def get_barcode_action(self, barcode: str, action_type: str = "settings") -> dict[str, Any]:
        return self.call_plain(
            BARCODE_URL,
            "getBarcodeAction",
            {"type": action_type, "barcode": barcode},
        )

    def save_state(self, path: str | Path) -> None:
        if not self.auth or not self.private_key_pem:
            raise ShadError("There is no complete signed-in state to save")
        state_path = Path(path)
        state_path.write_text(
            json.dumps(
                {
                    "auth": self.auth,
                    "private_key_pem": self.private_key_pem,
                    "api_url": self.api_url,
                    "api_version": self.api_version,
                    "app_version": self.app_version,
                    "language": self.language,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(state_path, 0o600)

    @classmethod
    def load_state(cls, path: str | Path, **kwargs: Any) -> "ShadClient":
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        state.update(kwargs)
        return cls(**state)

    def _sign(self, data_enc: str) -> str:
        private_key = serialization.load_pem_private_key(
            (self.private_key_pem or "").encode("ascii"),
            password=None,
        )
        signature = private_key.sign(
            data_enc.encode("utf-8"),
            asymmetric_padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")
