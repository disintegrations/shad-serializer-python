# Contributing

Contributions are welcome, especially protocol tests, documented method
wrappers, and fixes for upstream changes.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

## Expectations

- Keep changes focused and preserve the existing public API unless a breaking
  change is justified.
- Add tests for protocol changes and new behavior.
- Use synthetic values in tests and documentation.
- Never commit auth tokens, private keys, phone numbers, message content, HAR
  files, captured requests, or downloaded web assets.
- Document newly supported methods in `docs/feature-support.md` and
  `docs/api.md`.

## Reverse-engineering material

Captured traffic may be used locally to understand protocol behavior, but must
be sanitized before sharing. Prefer documenting field names and data shapes
instead of publishing real request or response bodies.

