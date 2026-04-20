from __future__ import annotations

from config_loader import load_config
from gui import AutomationApp


def main() -> None:
    config = load_config()
    app = AutomationApp(config)
    app.run()


if __name__ == "__main__":
    main()
