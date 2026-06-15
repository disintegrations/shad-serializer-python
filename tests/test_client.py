import base64
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding
from cryptography.hazmat.primitives.asymmetric import rsa

from shad_client import (
    ShadClient,
    decrypt_data,
    derive_aes_key,
    encrypt_data,
    transform_v6,
)
from shad_client.client import FILE_CHUNK_SIZE


class FakeResponse:
    def __init__(self, value=None, content=b""):
        self.value = value
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self.value


class FakeShadServer:
    auth = "abcdefghijklmnopqrstuvwxyzabcdef"

    def __init__(self):
        self.uploaded_parts = []
        self.download_bytes = b""

    def close(self):
        pass

    def post(self, url, data=None, headers=None, **_kwargs):
        if _kwargs.get("json"):
            payload = _kwargs["json"]
            if payload["method"] == "getDCs":
                value = {
                    "storages": {"522": "https://storage.test/GetFile.ashx"},
                    "default_api_urls": ["https://api.test"],
                }
            else:
                value = {"method": payload["method"], "input": payload["data"]}
            return FakeResponse({"status": "OK", "status_det": "OK", "data": value})
        if url.endswith("/UploadFile.ashx"):
            self.uploaded_parts.append(data)
            result = {"status": "OK", "status_det": "OK", "data": {}}
            if headers["part-number"] == headers["total-part"]:
                result["data"]["access_hash_rec"] = "access-rec"
            return FakeResponse(result)
        if url.endswith("/GetFile.ashx"):
            start = int(headers["start-index"])
            last = int(headers["last-index"])
            return FakeResponse(content=self.download_bytes[start : last + 1])

        outer = json.loads(data)
        secret = outer.get("tmp_session") or self.auth
        inner = decrypt_data(outer["data_enc"], secret)

        if inner["method"] == "sendCode":
            data = {"phone_code_hash": "hash", "code_digits_count": 6}
        elif inner["method"] == "signIn":
            public_pem = base64.b64decode(transform_v6(inner["input"]["public_key"]))
            public_key = serialization.load_pem_public_key(public_pem)
            encrypted_auth = public_key.encrypt(
                self.auth.encode(),
                asymmetric_padding.OAEP(
                    mgf=asymmetric_padding.MGF1(hashes.SHA1()),
                    algorithm=hashes.SHA1(),
                    label=None,
                ),
            )
            data = {"status": "OK", "auth": base64.b64encode(encrypted_auth).decode()}
        else:
            self._verify_authorized_request(outer)
            if inner["method"] == "requestSendFile":
                data = {
                    "id": "file-id",
                    "dc_id": "522",
                    "access_hash_send": "access-send",
                    "upload_url": "https://upload.test/UploadFile.ashx",
                }
            else:
                data = {"method": inner["method"], "input": inner["input"]}

        result = {"status": "OK", "status_det": "OK", "data": data}
        return FakeResponse({"data_enc": encrypt_data(result, secret)})

    def _verify_authorized_request(self, outer):
        self.assert_equal(outer["auth"], transform_v6(self.auth))
        public_key = self.client_private_key.public_key()
        public_key.verify(
            base64.b64decode(outer["sign"]),
            outer["data_enc"].encode(),
            asymmetric_padding.PKCS1v15(),
            hashes.SHA256(),
        )

    @staticmethod
    def assert_equal(left, right):
        if left != right:
            raise AssertionError(f"{left!r} != {right!r}")


class ProtocolTests(unittest.TestCase):
    def test_v6_transform_is_reversible(self):
        value = "abcdefghijklmnopqrstuvwxyz012345"
        self.assertEqual(transform_v6(transform_v6(value)), value)

    def test_v6_transform_handles_base64_characters(self):
        value = "Az09+/="
        self.assertEqual(transform_v6(transform_v6(value)), value)

    def test_protocol_round_trip(self):
        secret = "abcdefghijklmnopqrstuvwxyzabcdef"
        value = {"method": "example", "input": {"text": "hello"}}
        self.assertEqual(len(derive_aes_key(secret)), 32)
        self.assertEqual(decrypt_data(encrypt_data(value, secret), secret), value)

    def test_complete_v6_login_and_authorized_call(self):
        server = FakeShadServer()
        client = ShadClient(session=server)
        sent = client.send_code("10000000000")
        self.assertEqual(sent["phone_code_hash"], "hash")

        result = client.sign_in("10000000000", sent["phone_code_hash"], "123456")
        self.assertEqual(result["auth"], server.auth)
        server.client_private_key = serialization.load_pem_private_key(
            client.private_key_pem.encode(), password=None
        )

        result = client.call_data("getChats", {})
        self.assertEqual(result, {"method": "getChats", "input": {}})
        result = client.logout()
        self.assertEqual(result, {"method": "logout", "input": {}})

    def test_multipart_upload_and_download(self):
        server = FakeShadServer()
        client = ShadClient(auth=server.auth, private_key_pem=self._private_key_pem(), session=server)
        server.client_private_key = serialization.load_pem_private_key(
            client.private_key_pem.encode(), password=None
        )
        content = b"x" * (FILE_CHUNK_SIZE + 7)
        server.download_bytes = content

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.bin"
            destination = Path(directory) / "downloaded.bin"
            source.write_bytes(content)

            file_inline = client.upload_file(source)
            self.assertEqual([len(part) for part in server.uploaded_parts], [FILE_CHUNK_SIZE, 7])
            self.assertEqual(file_inline["access_hash_rec"], "access-rec")

            client.download_file(
                {**file_inline, "size": len(content)},
                destination,
                storage_url="https://storage.test/GetFile.ashx",
            )
            self.assertEqual(destination.read_bytes(), content)

    def test_plain_service_and_dc_discovery(self):
        server = FakeShadServer()
        client = ShadClient(auth=server.auth, session=server)

        result = client.get_barcode_action("access")
        self.assertEqual(result["method"], "getBarcodeAction")
        self.assertEqual(client.get_storage_url("522"), "https://storage.test/GetFile.ashx")
        self.assertEqual(client.api_url, "https://api.test")

    @staticmethod
    def _private_key_pem():
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        return private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()


if __name__ == "__main__":
    unittest.main()
