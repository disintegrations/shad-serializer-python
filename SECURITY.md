# Security Policy

## Reporting vulnerabilities

Do not open a public issue containing credentials, account data, private keys,
captured requests, or exploitable vulnerability details.

Report vulnerabilities privately to the repository maintainers through the
hosting platform's private security-reporting feature.

## Credential handling

`ShadClient.save_state()` writes the account auth token and RSA private key to
disk with owner-only permissions where supported. Treat that file as a
password:

- Do not commit or share it.
- Do not include it in bug reports.
- Revoke the corresponding Shad session if it is exposed.
- Use a dedicated test account when investigating protocol behavior.

HAR exports and file-transfer requests may contain raw auth tokens in headers.
Revoke the session after accidental exposure.

