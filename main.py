"""Application entry point for WS Downloader.

This module intentionally stays minimal: it exposes a single executable
entry point that starts the Tkinter GUI from :mod:`ws_downloader.ui`.
"""

from ws_downloader.ui import run_app


def main() -> None:
    """Start the desktop application."""
    run_app()


if __name__ == "__main__":
    main()
