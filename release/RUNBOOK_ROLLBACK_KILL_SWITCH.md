# Local candidate install, stop, and rollback runbook

This P2 candidate accepts a local JSON snapshot only. It does not start background workers, connect to MCP, issue database queries, or write to manufacturing systems.

## Start and stop the local UI

From the extracted bundle folder, run:

```sh
python -m fabintel serve --host 127.0.0.1 --port 8765
```

The server runs in the foreground and binds only to loopback. Press **Ctrl-C in that terminal** to stop it. `KeyboardInterrupt` exits `serve_forever()`, signals cancellation to active analyses, closes the listener, and waits for request threads to finish. This shutdown was observed on the current macOS host; see `qualification/evidence/server-stop-smoke.json`.

Each HTTP request runs on a server-owned thread so the loopback UI can cancel an active analysis. Analysis stays within its request and checks a per-request cancellation signal while processing bounded rows. Only one analysis runs at a time, at most two non-cancellation API submissions are admitted concurrently, and cancel requests remain serviceable while those slots are occupied. The API accepts the same session token for `/api/cancel`; UUID state is bounded, pending cancellation IDs expire, and a stopped request returns no partial evidence. Ctrl-C signals active work and server shutdown waits for those request threads. No persistent request/audit log exists in this local-only candidate. Save exported evidence JSON before stopping if the result needs to be retained.

If the original terminal is unavailable on macOS/Linux, inspect candidate processes first:

```sh
ps -axo pid=,command= | rg 'python -m fabintel serve'
```

Send `kill -INT <exact-pid>` only to the confirmed server process, then verify it exited. If it does not exit, `kill -TERM <exact-pid>` is the bounded last-resort process stop; there are no child workers or persistent writes to preserve. Do not use a broad `pkill` pattern. Windows console shutdown and force-stop behavior are not qualified in this package.

## Offline installation

The optional installer requires Python 3.10 or newer and creates `.venv` with `with_pip=False`; it performs no package installation or download:

```sh
python release/install_offline.py
```

The installer refuses an existing unmanaged or symlinked `.venv`. For rollback, run:

```sh
python release/uninstall_offline.py
```

Rollback removes only a `.venv` containing this bundle's `.fabintel-p2-managed` marker and verifies that the resolved path is the bundle-local `.venv`. It leaves source files and user data untouched. Fresh extraction, install, and rollback are exercised in `qualification/evidence/bundle-verification.log`.

## Operational limits

The API enforces a 25 MiB body limit and a 100,000 event-row limit. These bounds are not a company-approved query budget. The runbook is not a production deployment procedure; a target OS, authentication model, site firewall, source permissions, and audit-retention policy remain unqualified. Do not put company data in the synthetic fixtures or transfer artifacts.
