"""Quiet Messenger Desktop — application entry point.

This is the top-level entry point for PyInstaller packaging and direct
invocation. It imports the `app.main` module (which uses relative imports
internally) and calls its `main()` function.

Why this file exists:
    `app/main.py` uses relative imports (`from .router.router import Router`),
    which require it to be run as part of the `app` package
    (`python -m app.main`). Running it directly (`python app/main.py`) or
    feeding it directly to PyInstaller causes:
        ImportError: attempted relative import with no known parent package

    This wrapper script has no relative imports, so it can be used as the
    PyInstaller entry point. PyInstaller adds the script's directory to
    sys.path, making the `app` package importable.

Usage:
    python run.py
    pyinstaller --onefile --windowed run.py
"""

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
