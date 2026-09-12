# Keys-Shop Content Desk

This branch is the isolated Keys-Shop Content Desk workspace.

Use it from its own local folder, for example:

```text
E:\Claude work\keys-shop-content-desk
```

Do not run this branch from the Dolla Content Desk folder.

## Start

On Windows, use only:

```text
START_KEYS_CONTENT_DESK.bat
```

It starts the Keys-Shop desk on `http://127.0.0.1:5002/batch`.

Utility BAT files for connection testing, draft testing, and staff-package building live under `tools/` so the project root has one obvious launcher.

## WordPress setup

See `KEYS_SHOP_SETUP.md` for the Application Password, Yoast bridge, and publishing-safety setup.

## Architecture

- Shared Content OS generation/review concepts are reused from the Dolla proof of concept.
- Keys-Shop has its own WordPress adapter, ecommerce/product accuracy rules, internal-link logic, and publishing flow.
- Dolla and Keys-Shop should remain in separate local working folders so branch switching in one cannot affect the other.
