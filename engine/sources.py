from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# ---- Data model ----

ALLOWED_SOURCE_TYPES = {"rss", "html"}  # rss-first; html as escape hatch
ALLOWED_TIERS = {1, 2, 3}


@dataclass(frozen=True)
class SourceSpec:
    name: str
    type: str  # "rss" | "html"
    url: str
    tier: int = 2
    region: Optional[str] = None
    tags: Tuple[str, ...] = ()
    enabled: bool = True


@dataclass(frozen=True)
class ChannelSpec:
    key: str
    title: str
    sources: Tuple[SourceSpec, ...] = ()


@dataclass(frozen=True)
class SourcesConfig:
    version: int
    channels: Tuple[ChannelSpec, ...]


# ---- Loader ----

class SourcesConfigError(ValueError):
    pass


def _as_tuple_str(x: Any) -> Tuple[str, ...]:
    if x is None:
        return ()
    if isinstance(x, (list, tuple)):
        return tuple(str(i).strip() for i in x if str(i).strip())
    return (str(x).strip(),)


def _validate_source(raw: Dict[str, Any], channel_key: str) -> SourceSpec:
    if not isinstance(raw, dict):
        raise SourcesConfigError(f"Source in channel '{channel_key}' must be a mapping/dict.")

    name = str(raw.get("name", "")).strip()
    stype = str(raw.get("type", "")).strip().lower()
    url = str(raw.get("url", "")).strip()
    tier = int(raw.get("tier", 2))
    region = raw.get("region")
    tags = _as_tuple_str(raw.get("tags"))
    enabled = bool(raw.get("enabled", True))

    if not name:
        raise SourcesConfigError(f"Missing 'name' in source for channel '{channel_key}'.")
    if stype not in ALLOWED_SOURCE_TYPES:
        raise SourcesConfigError(
            f"Invalid source type '{stype}' for '{name}' in '{channel_key}'. Allowed: {sorted(ALLOWED_SOURCE_TYPES)}"
        )
    if not (url.startswith("http://") or url.startswith("https://")):
        raise SourcesConfigError(f"Invalid 'url' for '{name}' in '{channel_key}': must be http(s).")
    if tier not in ALLOWED_TIERS:
        raise SourcesConfigError(f"Invalid 'tier'={tier} for '{name}' in '{channel_key}'. Allowed: {sorted(ALLOWED_TIERS)}")

    region_str = str(region).strip() if region is not None else None
    return SourceSpec(
        name=name,
        type=stype,
        url=url,
        tier=tier,
        region=region_str if region_str else None,
        tags=tags,
        enabled=enabled,
    )


def load_sources_config(path: str | Path = "sources.yaml") -> SourcesConfig:
    p = Path(path)
    if not p.exists():
        raise SourcesConfigError(f"Sources config not found: {p.resolve()}")

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SourcesConfigError("Top-level YAML must be a mapping/dict.")

    version = int(data.get("version", 1))
    channels_raw = data.get("channels")
    if not isinstance(channels_raw, dict) or not channels_raw:
        raise SourcesConfigError("Missing or invalid 'channels' mapping in sources.yaml.")

    channels: List[ChannelSpec] = []
    for ch_key, ch_val in channels_raw.items():
        if not isinstance(ch_val, dict):
            raise SourcesConfigError(f"Channel '{ch_key}' must be a mapping/dict.")
        title = str(ch_val.get("title", ch_key)).strip()
        sources_list = ch_val.get("sources", [])
        if sources_list is None:
            sources_list = []
        if not isinstance(sources_list, list):
            raise SourcesConfigError(f"Channel '{ch_key}.sources' must be a list.")

        sources: List[SourceSpec] = []
        for raw_source in sources_list:
            spec = _validate_source(raw_source, ch_key)
            sources.append(spec)

        channels.append(ChannelSpec(key=str(ch_key), title=title, sources=tuple(sources)))

    return SourcesConfig(version=version, channels=tuple(channels))


def flatten_enabled_sources(cfg: SourcesConfig) -> List[Tuple[ChannelSpec, SourceSpec]]:
    out: List[Tuple[ChannelSpec, SourceSpec]] = []
    for ch in cfg.channels:
        for s in ch.sources:
            if s.enabled:
                out.append((ch, s))
    return out
