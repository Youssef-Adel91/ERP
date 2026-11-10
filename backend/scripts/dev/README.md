# Developer / maintenance scripts

One-off diagnostics, repair and verification scripts used during development.
**Not part of the product. Several of them modify or delete data (users, tenants,
schemas) — never run them against a production database.**

Run from the `backend/` directory so `app` is importable:

    PYTHONPATH=. python scripts/dev/<script>.py
