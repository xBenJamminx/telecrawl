"""
Configuration management for telecrawl.
Loads/saves TOML config from ~/.telecrawl/config.toml.
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional, Any

# Use tomllib (3.11+) or tomli as fallback for reading
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

try:
    import tomli_w
except ImportError:
    tomli_w = None


CONFIG_DIR = Path.home() / '.telecrawl'
CONFIG_PATH = CONFIG_DIR / 'config.toml'

DEFAULT_DB = str(CONFIG_DIR / 'telecrawl.db')
DEFAULT_SESSION = str(CONFIG_DIR / 'telecrawl')


def load_config() -> Optional[Dict[str, Any]]:
    """
    Load config from ~/.telecrawl/config.toml.
    Returns None if config file doesn't exist.
    """
    if not CONFIG_PATH.exists():
        return None

    if tomllib is None:
        print("Error: tomli package required for Python <3.11")
        print("Install it: pip install tomli")
        sys.exit(1)

    with open(CONFIG_PATH, 'rb') as f:
        return tomllib.load(f)


def save_config(config: Dict[str, Any]) -> Path:
    """
    Save config to ~/.telecrawl/config.toml.
    Creates the directory if it doesn't exist.
    Returns the path to the saved config file.
    """
    if tomli_w is None:
        print("Error: tomli-w package required for writing config")
        print("Install it: pip install tomli-w")
        sys.exit(1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_PATH, 'wb') as f:
        tomli_w.dump(config, f)

    return CONFIG_PATH


def get_configured_chats() -> List[Dict[str, Any]]:
    """
    Get the list of tracked chats from config.
    Returns empty list if no config or no chats configured.
    """
    config = load_config()
    if config is None:
        return []
    return config.get('chats', [])


def get_configured_chat_ids() -> List[int]:
    """
    Get just the chat IDs from config.
    Returns empty list if no config or no chats configured.
    """
    return [chat['id'] for chat in get_configured_chats()]


def get_db_path(cli_override: Optional[str] = None) -> str:
    """
    Get database path. Priority: CLI flag > config > default.
    """
    if cli_override and cli_override != DEFAULT_DB:
        return cli_override

    config = load_config()
    if config and 'telecrawl' in config:
        db_path = config['telecrawl'].get('db_path')
        if db_path:
            return str(Path(db_path).expanduser())

    return DEFAULT_DB


def get_session_path(cli_override: Optional[str] = None) -> str:
    """
    Get Telethon session path. Priority: CLI flag > config > default.
    """
    if cli_override and cli_override != DEFAULT_SESSION:
        return cli_override

    config = load_config()
    if config and 'telecrawl' in config:
        session_path = config['telecrawl'].get('session_path')
        if session_path:
            return str(Path(session_path).expanduser())

    return DEFAULT_SESSION


def config_exists() -> bool:
    """Check if a config file already exists."""
    return CONFIG_PATH.exists()


def format_chat_type(entity) -> str:
    """Determine chat type string from a Telethon entity."""
    from telethon.tl.types import Channel, Chat, User

    if isinstance(entity, Channel):
        if entity.megagroup:
            return "supergroup"
        elif entity.broadcast:
            return "channel"
        else:
            return "group"
    elif isinstance(entity, Chat):
        return "group"
    elif isinstance(entity, User):
        return "user"
    return "unknown"
