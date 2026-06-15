# Protocol Notes

Shad's web client communicates with messenger data centers through JSON HTTP
`POST` requests.

## Encrypted messenger calls

The inner request contains:

```json
{
  "method": "getChats",
  "input": {},
  "client": {
    "app_name": "Main",
    "app_version": "4.4.26",
    "platform": "Web",
    "package": "web.shad.ir",
    "lang_code": "fa"
  }
}
```

The inner request is encrypted with AES-256-CBC and PKCS#7 padding. The key is
derived from either a temporary session value or the account auth token.

Authorized API v6 requests also:

- Apply a reversible substitution to the auth token.
- Sign the encrypted `data_enc` string with the RSA private key created during
  sign-in.

## Login

1. `sendCode` is encrypted using a random temporary session.
2. The client creates an RSA key pair.
3. `signIn` sends the transformed public key.
4. The response returns the auth token encrypted for that RSA key.
5. Future API v6 requests use the auth token and private key.

## Files

Uploads begin with `requestSendFile`, followed by 128 KiB HTTP upload parts.
The resulting `file_inline` dictionary can be sent using `sendMessage`.

Downloads use storage URLs returned by `getDCs` and request byte ranges through
headers.

## Compatibility

This protocol is undocumented and may change. Avoid depending on internal
helpers unless needed for protocol research. New behavior should be covered by
synthetic tests before release.

