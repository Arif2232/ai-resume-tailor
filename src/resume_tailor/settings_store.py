"""Store the user's opted-in provider settings in a local file."""

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Literal

from platformdirs import user_config_path
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from resume_tailor import providers

SETTINGS_DIR = Path(os.environ.get('RESUME_TAILOR_CONFIG_DIR') or user_config_path('ai-resume-tailor', appauthor=False))
SETTINGS_PATH = SETTINGS_DIR / 'connection.json'
MAX_SETTINGS_BYTES = 10_000


class SettingsStoreError(ValueError):
    pass


class SavedSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    provider: Literal['openai', 'gemini', 'claude']
    model: str = Field(max_length=128)
    api_key: SecretStr
    workspace_id: str = Field(max_length=128)

    @model_validator(mode='after')
    def validate_settings(self):
        try:
            providers.selected_settings(self.provider, self.api_key.get_secret_value(), self.model, self.workspace_id)
        except providers.ProviderError as exc:
            raise ValueError('Invalid saved settings.') from exc
        return self


def legacy_settings_exist() -> bool:
    return (SETTINGS_PATH.parent / 'settings.json').is_file()


def load_settings() -> SavedSettings | None:
    try:
        if SETTINGS_PATH.is_symlink():
            raise SettingsStoreError('Saved settings cannot be read. Remove them and connect again.')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(SETTINGS_PATH, flags)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SETTINGS_BYTES:
                raise SettingsStoreError('Saved settings cannot be read. Remove them and connect again.')
            raw = handle.read(MAX_SETTINGS_BYTES + 1)
            if len(raw) > MAX_SETTINGS_BYTES:
                raise SettingsStoreError('Saved settings cannot be read. Remove them and connect again.')
        return SavedSettings.model_validate_json(raw)
    except FileNotFoundError:
        return None
    except SettingsStoreError:
        raise
    except (OSError, ValueError) as exc:
        raise SettingsStoreError('Saved settings cannot be read. Remove them and connect again.') from exc


def save_settings(settings: SavedSettings):
    temporary = None
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix='.settings-', dir=SETTINGS_PATH.parent)
        temporary = Path(name)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            if os.name != 'nt':
                os.fchmod(handle.fileno(), 0o600)
            data = settings.model_dump(exclude={'api_key'})
            data['api_key'] = settings.api_key.get_secret_value()
            json.dump(data, handle, separators=(',', ':'))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, SETTINGS_PATH)
    except OSError as exc:
        raise SettingsStoreError('Could not save settings. Check local file permissions.') from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def delete_settings():
    try:
        SETTINGS_PATH.unlink(missing_ok=True)
    except OSError as exc:
        raise SettingsStoreError('Could not remove saved settings. Check local file permissions.') from exc
