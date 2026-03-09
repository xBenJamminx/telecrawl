"""
Two-step non-interactive authentication for Telethon.
Designed for headless servers where interactive input isn't available.

Usage:
    Step 1: Request code
        python -m telecrawl.auth request +1234567890

    Step 2: Verify code (sent via Telegram)
        python -m telecrawl.auth verify 12345
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError


DEFAULT_SESSION_DIR = Path.home() / '.telecrawl'
AUTH_STATE_FILE = DEFAULT_SESSION_DIR / '.auth_state.json'


def get_config():
    """Load API credentials from environment."""
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')

    if not api_id or not api_hash:
        print("Error: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set")
        print("Get these from https://my.telegram.org/apps")
        sys.exit(1)

    return int(api_id), api_hash


async def request_code(phone: str):
    """Step 1: Send verification code to the phone number."""
    api_id, api_hash = get_config()
    session_path = str(DEFAULT_SESSION_DIR / 'telecrawl')

    DEFAULT_SESSION_DIR.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()

    result = await client.send_code_request(phone)

    # Save state for step 2
    state = {
        'phone': phone,
        'phone_code_hash': result.phone_code_hash,
    }
    AUTH_STATE_FILE.write_text(json.dumps(state))

    print(f"Code sent to {phone}")
    print(f"Run: python -m telecrawl.auth verify <code>")

    await client.disconnect()


async def verify_code(code: str):
    """Step 2: Complete sign-in with the verification code."""
    api_id, api_hash = get_config()
    session_path = str(DEFAULT_SESSION_DIR / 'telecrawl')

    if not AUTH_STATE_FILE.exists():
        print("Error: No pending auth request. Run 'request' first.")
        sys.exit(1)

    state = json.loads(AUTH_STATE_FILE.read_text())

    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()

    try:
        await client.sign_in(
            phone=state['phone'],
            code=code,
            phone_code_hash=state['phone_code_hash']
        )
        me = await client.get_me()
        print(f"Authenticated as {me.first_name} (@{me.username})")
        print(f"Session saved to {session_path}.session")
    except SessionPasswordNeededError:
        print("Error: 2FA is enabled. Enter your password:")
        # For headless, you'd need to extend this
        print("2FA support not yet implemented for headless auth.")
        sys.exit(1)
    finally:
        AUTH_STATE_FILE.unlink(missing_ok=True)
        await client.disconnect()


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python -m telecrawl.auth request <phone_number>")
        print("  python -m telecrawl.auth verify <code>")
        sys.exit(1)

    command = sys.argv[1]
    arg = sys.argv[2]

    if command == 'request':
        asyncio.run(request_code(arg))
    elif command == 'verify':
        asyncio.run(verify_code(arg))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
