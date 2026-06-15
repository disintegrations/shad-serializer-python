from shad_client import ShadClient


with ShadClient.load_state("shad-state.json") as shad:
    chats = shad.get_chats()
    for chat in chats.get("chats", []):
        print(chat["object_guid"], chat["abs_object"])

    # shad.send_message("u0...", "Hello from Python")
    # shad.send_file("u0...", "document.pdf")

