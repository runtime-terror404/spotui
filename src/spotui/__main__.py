"""Allow ``python -m spotui`` to behave like the ``spotui`` command."""

from spotui.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
