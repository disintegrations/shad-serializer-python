from getpass import getpass

from shad_client import ShadClient


phone = input("Phone number with country code, without + (example 98912...): ").strip()
client = ShadClient()

sent = client.send_code(phone)
print(sent)
code = getpass("Code: ")

signed_in = client.sign_in(phone, sent["phone_code_hash"], code)
print(signed_in["status"])
client.save_state("shad-state.json")

print(client.register_device())
print(client.get_chats())

# Later:
# client = ShadClient.load_state("shad-state.json")
# print(client.send_message("u0...", "Hello from Python"))

