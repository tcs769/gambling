"""Settings and credentials.

Trading parameters come from ``config.yaml``; secrets come only from the
environment and are never logged or echoed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path

import yaml


class ConfigError(RuntimeError):
    pass


@dataclass
class Settings:
    entry_gap: int = 15
    exit_gap: int = 5
    jev_interval_s: float = 5.0
    transcript_window_s: int = 120
    contracts_per_entry: int = 1
    max_contracts_per_market: int = 5
    max_dollars_per_event: float = 25.0
    max_loss_per_event: float = 25.0
    min_word_confidence: float = 0.85
    max_price_after_mention: int = 95
    order_timeout_s: float = 10.0
    stale_data_s: float = 10.0
    jev_model: str = "jev-1.13.0"
    jev_timeout_s: float = 8.0
    speech_model: str = "universal-streaming-english"
    sample_rate: int = 16000

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> Settings:
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"config file not found: {p}")
        raw = yaml.safe_load(p.read_text()) or {}
        if not isinstance(raw, dict):
            raise ConfigError(f"{p} must contain a YAML mapping")

        known = {f.name: f for f in fields(cls)}
        unknown = set(raw) - set(known)
        if unknown:
            raise ConfigError(f"unknown settings in {p}: {', '.join(sorted(unknown))}")

        kwargs = {}
        for name, value in raw.items():
            target = known[name].type
            try:
                if target is int or target == "int":
                    kwargs[name] = int(value)
                elif target is float or target == "float":
                    kwargs[name] = float(value)
                else:
                    kwargs[name] = value
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"setting {name!r} has a bad value {value!r}") from exc
        settings = cls(**kwargs)
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.entry_gap <= 0:
            raise ConfigError("entry_gap must be positive")
        if self.contracts_per_entry < 1:
            raise ConfigError("contracts_per_entry must be at least 1")
        if self.contracts_per_entry > self.max_contracts_per_market:
            raise ConfigError("contracts_per_entry exceeds max_contracts_per_market")
        if not 0.0 <= self.min_word_confidence <= 1.0:
            raise ConfigError("min_word_confidence must be between 0 and 1")
        if not 1 <= self.max_price_after_mention <= 99:
            raise ConfigError("max_price_after_mention must be 1..99 cents")
        if self.max_dollars_per_event <= 0:
            raise ConfigError("max_dollars_per_event must be positive")
        if self.max_loss_per_event <= 0:
            raise ConfigError("max_loss_per_event must be positive")
        if self.jev_model.endswith("-latest") or self.jev_model.endswith("-preview"):
            raise ConfigError(
                f"jev_model must be a pinned version, not the moving alias "
                f"{self.jev_model!r} (e.g. 'jev-1.13.0')"
            )

    @property
    def max_cents_per_event(self) -> int:
        return int(round(self.max_dollars_per_event * 100))

    @property
    def max_loss_cents(self) -> int:
        return int(round(self.max_loss_per_event * 100))


@dataclass
class Credentials:
    kalshi_key_id: str
    kalshi_private_key_path: str
    assemblyai_api_key: str
    typesafe_api_key: str

    @classmethod
    def from_env(cls) -> Credentials:
        missing: list[str] = []

        def need(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                missing.append(name)
            return value

        key_id = need("KALSHI_API_KEY_ID")
        key_path = need("KALSHI_PRIVATE_KEY_PATH")
        assembly = need("ASSEMBLYAI_API_KEY")

        # Jev may be reached directly or via a Vercel AI Gateway.
        typesafe = (
            os.environ.get("TYPESAFE_API_KEY", "").strip()
            or os.environ.get("AI_GATEWAY_API_KEY", "").strip()
        )
        if not typesafe:
            missing.append("TYPESAFE_API_KEY (or AI_GATEWAY_API_KEY)")

        if missing:
            raise ConfigError(
                "missing required environment variables: " + ", ".join(missing)
            )
        if key_path and not Path(key_path).exists():
            raise ConfigError(f"KALSHI_PRIVATE_KEY_PATH does not exist: {key_path}")

        return cls(key_id, key_path, assembly, typesafe)

    def __repr__(self) -> str:  # never leak secrets into logs or tracebacks
        return "Credentials(<redacted>)"
