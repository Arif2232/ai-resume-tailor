"""Store only a browser-encrypted settings envelope, never a plaintext key."""

import base64
import binascii
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Literal

from platformdirs import user_config_path
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

SETTINGS_DIR = Path(os.environ.get('RESUME_TAILOR_CONFIG_DIR') or user_config_path('ai-resume-tailor', appauthor=False))
SETTINGS_PATH = SETTINGS_DIR / 'settings.json'
MAX_SETTINGS_BYTES = 10_000


class SettingsStoreError(ValueError):
    pass


class EncryptedSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version: Literal[1]
    kdf: Literal['PBKDF2-SHA256']
    iterations: Literal[600000]
    salt: str
    iv: str
    ciphertext: str

    @field_validator('version', 'iterations', mode='before')
    @classmethod
    def require_integer(cls, value):
        if type(value) is not int:
            raise ValueError('Invalid encrypted settings.')
        return value

    @model_validator(mode='after')
    def validate_envelope(self):
        try:
            decoded = [base64.b64decode(value, validate=True) for value in (self.salt, self.iv, self.ciphertext)]
            if any(base64.b64encode(item).decode('ascii') != value for item, value in zip(decoded, (self.salt, self.iv, self.ciphertext))):
                raise ValueError('Non-canonical base64')
        except (ValueError, binascii.Error) as exc:
            raise ValueError('Invalid encrypted settings.') from exc
        if len(decoded[0]) != 16 or len(decoded[1]) != 12 or not 16 <= len(decoded[2]) <= 4096:
            raise ValueError('Invalid encrypted settings.')
        return self


def load_settings() -> EncryptedSettings | None:
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
        return EncryptedSettings.model_validate_json(raw)
    except FileNotFoundError:
        return None
    except SettingsStoreError:
        raise
    except (OSError, ValueError) as exc:
        raise SettingsStoreError('Saved settings cannot be read. Remove them and connect again.') from exc


def save_settings(encrypted: EncryptedSettings):
    temporary = None
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix='.settings-', dir=SETTINGS_PATH.parent)
        temporary = Path(name)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            if os.name != 'nt':
                os.fchmod(handle.fileno(), 0o600)
            json.dump(encrypted.model_dump(), handle, separators=(',', ':'))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, SETTINGS_PATH)
    except OSError as exc:
        raise SettingsStoreError('Could not save encrypted settings. Check local file permissions.') from exc
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
