"""CLI entry point: python -m hud <command>"""
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m hud <watch|install>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "watch":
        from hud.app import HudApp
        base_dir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/claude-hud"
        app = HudApp(base_dir=base_dir)
        app.run()

    elif command == "install":
        from hud.install import install_hooks
        install_hooks()

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
