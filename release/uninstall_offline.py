"""Remove only the virtual environment created by this bundle installer."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".venv"
MARKER = ENV / ".fabintel-p2-managed"


def main():
    if ENV.is_symlink() or not MARKER.is_file():
        raise SystemExit("No bundle-managed .venv found; nothing was removed.")
    resolved_root = ROOT.resolve()
    resolved_env = ENV.resolve(strict=True)
    if resolved_env.parent != resolved_root or resolved_env.name != ".venv":
        raise SystemExit("Refusing to remove an environment outside this bundle folder.")
    shutil.rmtree(resolved_env)
    print("Removed the bundle-managed local virtual environment. Source files and user data were untouched.")


if __name__ == "__main__":
    main()
