"""Expected to run inside no_external_network.sb; makes no packet when blocked."""
import errno
import socket

try:
    socket.create_connection(("203.0.113.1", 9), timeout=0.5)
except OSError as exc:
    if exc.errno in (errno.EPERM, errno.EACCES):
        print(f"NETWORK_BLOCK_ACTIVE: outbound socket denied by policy (errno={exc.errno}).")
    else:
        raise SystemExit(f"No proof of sandbox egress denial: socket failed with {exc!r}.")
else:
    raise SystemExit("FAIL: sandbox allowed an outbound socket.")
