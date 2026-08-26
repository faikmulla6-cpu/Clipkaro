from __future__ import annotations

import secrets


def main() -> None:
    token = secrets.token_urlsafe(64)
    print("ClipKaro Founder Admin service token (generated locally; shown once):")
    print(token)
    print("\nInstall the SAME value only in the ClipKaro server secret store and the Founder Console server secret store.")
    print("Do not commit it, paste it into browser code, screenshots, chat, logs, or example env files.")


if __name__ == "__main__":
    main()
