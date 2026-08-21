"""Configuration loader and schema validation for pylontech-mqtt."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
try:
    import yaml
except ImportError:
    yaml = None



@dataclass
class SerialConfig:
    port: str = "/dev/ttyUSB0"
    baudrate: int = 115200
    timeout: float = 3.0
    reconnect_delay: float = 5.0


@dataclass
class PollingConfig:
    interval_seconds: float = 15.0
    info_interval_seconds: float = 3600.0
    battery_count: int = 4
    read_cell_details: bool = True


@dataclass
class MQTTConfig:
    host: str = "127.0.0.1"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    topic_prefix: str = "pylontech"
    ha_discovery_prefix: str = "homeassistant"
    ha_discovery_enabled: bool = True
    client_id: str = "pylontech-mqtt"
    tls: bool = False


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class AppConfig:
    serial: SerialConfig = field(default_factory=SerialConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Fallback parser for basic YAML files when PyYAML is not installed."""
    result: Dict[str, Any] = {}
    current_section: Optional[str] = None
    for line in text.splitlines():
        line_clean = line.split("#")[0].rstrip()
        if not line_clean.strip():
            continue
        if line_clean.startswith("  ") and current_section is not None:
            subline = line_clean.strip()
            if ":" in subline:
                k, v = subline.split(":", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                val: Any
                if v.lower() == "true":
                    val = True
                elif v.lower() == "false":
                    val = False
                elif v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                    val = int(v)
                else:
                    try:
                        val = float(v)
                    except ValueError:
                        val = v
                result[current_section][k] = val
        elif ":" in line_clean:
            k, v = line_clean.split(":", 1)
            k = k.strip()
            v = v.strip().strip("\"'")
            if v == "":
                current_section = k
                if current_section not in result:
                    result[current_section] = {}
            else:
                current_section = None
                val: Any
                if v.lower() == "true":
                    val = True
                elif v.lower() == "false":
                    val = False
                elif v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                    val = int(v)
                else:
                    try:
                        val = float(v)
                    except ValueError:
                        val = v
                result[k] = val
    return result


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if yaml is not None:
        data = yaml.safe_load(content)
        return data if isinstance(data, dict) else {}
    return _parse_simple_yaml(content)



def load_config(config_path: Optional[str | Path] = None) -> AppConfig:
    """Load configuration from file and environment variables."""
    paths_to_check = []
    if config_path:
        paths_to_check.append(Path(config_path))
    else:
        # Default search paths
        if os.environ.get("PYLONTECH_CONFIG"):
            paths_to_check.append(Path(os.environ["PYLONTECH_CONFIG"]))
        paths_to_check.append(Path("config.yaml"))
        paths_to_check.append(Path("/etc/pylontech-mqtt/config.yaml"))
        paths_to_check.append(Path.home() / ".config" / "pylontech-mqtt" / "config.yaml")

    raw_data: Dict[str, Any] = {}
    for p in paths_to_check:
        if p.is_file():
            raw_data = _load_yaml(p)
            break

    # Parse Serial config
    s_raw = raw_data.get("serial", {})
    serial_cfg = SerialConfig(
        port=os.environ.get("PYLON_SERIAL_PORT", s_raw.get("port", "/dev/ttyUSB0")),
        baudrate=int(os.environ.get("PYLON_SERIAL_BAUDRATE", s_raw.get("baudrate", 115200))),
        timeout=float(os.environ.get("PYLON_SERIAL_TIMEOUT", s_raw.get("timeout", 3.0))),
        reconnect_delay=float(os.environ.get("PYLON_SERIAL_RECONNECT_DELAY", s_raw.get("reconnect_delay", 5.0))),
    )

    # Parse Polling config
    p_raw = raw_data.get("polling", {})
    raw_bat_count = (
        p_raw.get("battery_count")
        or p_raw.get("units")
        or p_raw.get("batteries")
        or p_raw.get("battery_units")
        or p_raw.get("unit_count")
        or raw_data.get("battery_count")
        or raw_data.get("units")
        or raw_data.get("batteries")
        or 4
    )
    polling_cfg = PollingConfig(
        interval_seconds=float(os.environ.get("PYLON_POLL_INTERVAL", p_raw.get("interval_seconds", 15.0))),
        info_interval_seconds=float(os.environ.get("PYLON_INFO_INTERVAL", p_raw.get("info_interval_seconds", 3600.0))),
        battery_count=int(os.environ.get("PYLON_BATTERY_COUNT", raw_bat_count)),
        read_cell_details=bool(
            str(os.environ.get("PYLON_READ_CELL_DETAILS", p_raw.get("read_cell_details", True))).lower() in ("true", "1", "yes")
        ),
    )

    # Parse MQTT config
    m_raw = raw_data.get("mqtt", {})
    mqtt_cfg = MQTTConfig(
        host=os.environ.get("MQTT_HOST", m_raw.get("host", "127.0.0.1")),
        port=int(os.environ.get("MQTT_PORT", m_raw.get("port", 1883))),
        username=os.environ.get("MQTT_USERNAME", m_raw.get("username")),
        password=os.environ.get("MQTT_PASSWORD", m_raw.get("password")),
        topic_prefix=os.environ.get("MQTT_TOPIC_PREFIX", m_raw.get("topic_prefix", "pylontech")),
        ha_discovery_prefix=os.environ.get("MQTT_HA_DISCOVERY_PREFIX", m_raw.get("ha_discovery_prefix", "homeassistant")),
        ha_discovery_enabled=bool(
            str(os.environ.get("MQTT_HA_DISCOVERY_ENABLED", m_raw.get("ha_discovery_enabled", True))).lower() in ("true", "1", "yes")
        ),
        client_id=os.environ.get("MQTT_CLIENT_ID", m_raw.get("client_id", "pylontech-mqtt")),
        tls=bool(str(os.environ.get("MQTT_TLS", m_raw.get("tls", False))).lower() in ("true", "1", "yes")),
    )

    # Parse Logging config
    l_raw = raw_data.get("logging", {})
    logging_cfg = LoggingConfig(
        level=os.environ.get("LOG_LEVEL", l_raw.get("level", "INFO")).upper(),
    )

    return AppConfig(
        serial=serial_cfg,
        polling=polling_cfg,
        mqtt=mqtt_cfg,
        logging=logging_cfg,
    )
