"""Entry point: GUI by default; ``--self-test`` / CLI sub-commands run without Qt."""
import multiprocessing
import sys


def main() -> int:
    multiprocessing.freeze_support()   # required for spawned workers in frozen (PyInstaller) builds
    args = sys.argv[1:]
    if args and (args[0] in ("convert", "routes", "selftest", "--version") or args[0] == "--self-test"):
        if args[0] == "--self-test":
            args[0] = "selftest"
        from .cli import main as cli_main
        return cli_main(args)
    from .ui.app import run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
