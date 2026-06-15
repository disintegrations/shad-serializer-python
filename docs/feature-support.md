# Feature Support

## Implemented

- SMS login and API v6 RSA key exchange
- Authenticated encrypted HTTP calls
- Device registration and local session-state persistence
- Chat listing and chat updates
- Message history, message updates, text sending, seen state, and typing state
- Multipart file upload, file messages, and ranged file download
- User, service, username, contact, and related-object lookups
- Channel lookup, join, and leave
- Folders, settings, stickers, sessions, barcode actions, and data-center
  discovery
- Generic calls for HTTP methods without convenience wrappers
- Interactive account/contact chat example with manual message refresh

## Not implemented

- WebSocket event streaming and automatic update handling
- Async client
- Complete message actions such as edit, delete, forward, reactions, and polls
- Complete group/channel administration
- Image/video/voice preprocessing and thumbnails
- Calls, voice chats, live streams, Rubino, stories, and wallet features

## Stability

The project is alpha software. Method names and payload shapes follow observed
web-client behavior and may stop working after upstream changes.
