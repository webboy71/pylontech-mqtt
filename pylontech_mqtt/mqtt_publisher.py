"""MQTT publisher handling Home Assistant discovery and live telemetry streaming."""

from __future__ import annotations

import dataclasses
import json
import logging
import ssl
import time
try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from .config import AppConfig
from .ha_discovery import HomeAssistantDiscovery
from .parser import StackTelemetry, UnitInfo

logger = logging.getLogger(__name__)


class MQTTPublisher:
    """Manages MQTT connection, LWT status, HA discovery, and state telemetry publishing."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.mqtt_cfg = config.mqtt
        self.discovery = HomeAssistantDiscovery(config)
        self._client: Optional[Any] = None
        self._connected = False
        self._discovery_published = False
        self._status_topic = f"{self.mqtt_cfg.topic_prefix}/status"
        self._event_log: list[str] = []
        self._last_event_summary: str = "OK"
        self._last_event_time: float = 0.0
        self._unit_last_events: dict[int, str] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        """Initialize MQTT client and connect in background loop."""
        if mqtt is None:
            logger.error("paho-mqtt package is not installed. Please install paho-mqtt.")
            return

        logger.info(
            "Connecting to MQTT broker %s:%d (Client ID: %s)...",
            self.mqtt_cfg.host,
            self.mqtt_cfg.port,
            self.mqtt_cfg.client_id,
        )

        try:
            # Handle paho-mqtt v2.0+ and v1.x compatibility
            try:
                from paho.mqtt.enums import CallbackAPIVersion
                self._client = mqtt.Client(
                    CallbackAPIVersion.VERSION2,
                    client_id=self.mqtt_cfg.client_id,
                    protocol=mqtt.MQTTv311,
                )
            except (ImportError, AttributeError):
                self._client = mqtt.Client(
                    client_id=self.mqtt_cfg.client_id,
                    protocol=mqtt.MQTTv311,
                )

            # Setup Last Will and Testament (LWT)
            self._client.will_set(
                topic=self._status_topic,
                payload="offline",
                qos=1,
                retain=True,
            )

            # Authentication
            if self.mqtt_cfg.username and self.mqtt_cfg.password:
                self._client.username_pw_set(self.mqtt_cfg.username, self.mqtt_cfg.password)

            # TLS if enabled
            if self.mqtt_cfg.tls:
                self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

            # Callbacks
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect

            self._client.connect_async(self.mqtt_cfg.host, self.mqtt_cfg.port, keepalive=60)
            self._client.loop_start()

        except Exception as e:
            logger.error("Failed to initialize MQTT client: %s", e)
            raise

    def stop(self) -> None:
        """Publish offline status and disconnect cleanly."""
        if self._client:
            logger.info("Disconnecting from MQTT broker...")
            try:
                self._client.publish(self._status_topic, "offline", qos=1, retain=True)
                time.sleep(0.2)
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as e:
                logger.debug("Error during MQTT disconnect: %s", e)
            finally:
                self._connected = False
                self._client = None

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, *args: Any) -> None:
        # rc is integer in v1 and ReasonCode in v2
        rc_val = getattr(rc, "value", rc)
        if rc_val == 0:
            logger.info("Successfully connected to MQTT broker.")
            self._connected = True
            # Publish online status
            self._client.publish(self._status_topic, "online", qos=1, retain=True)
            self._discovery_published = False
        else:
            logger.error("MQTT connection failed with code %s", rc)
            self._connected = False

    def _on_disconnect(self, client: Any, userdata: Any, *args: Any) -> None:
        logger.warning("Disconnected from MQTT broker.")
        self._connected = False

    def publish_discovery(
        self,
        battery_count: Optional[int] = None,
        unit_infos: Optional[Dict[int, UnitInfo]] = None,
    ) -> None:
        """Publish Home Assistant discovery messages."""
        if not self._connected or not self._client:
            return

        if not self.mqtt_cfg.ha_discovery_enabled:
            return

        effective_count = (
            battery_count
            if battery_count is not None and battery_count > 0
            else (self.config.polling.battery_count if self.config.polling.battery_count > 0 else 4)
        )

        logger.info("Publishing Home Assistant MQTT discovery payloads for %d batteries...", effective_count)
        messages = self.discovery.build_all_discovery_messages(
            battery_count=effective_count,
            unit_infos=unit_infos,
        )

        for topic, payload in messages:
            self._client.publish(topic, payload, qos=1, retain=True)

        # Clear any excess orphaned discovery entities (e.g. units 5..16 if stack was resized or previously discovered as 8)
        cleanup_messages = self.discovery.build_cleanup_discovery_messages(
            configured_count=effective_count,
            max_count=16,
        )
        for topic, empty_payload in cleanup_messages:
            self._client.publish(topic, empty_payload, qos=1, retain=True)

        self._discovery_published = True
        logger.info(
            "Published %d Home Assistant discovery entities (and purged %d excess entity slots).",
            len(messages),
            len(cleanup_messages),
        )

    def publish_telemetry(self, stack: StackTelemetry) -> None:
        """Publish real-time telemetry for stack totals and individual units."""
        if not self._connected or not self._client:
            logger.debug("Skipping MQTT publish: not connected to broker.")
            return

        # Publish discovery once when data is first available
        if not self._discovery_published:
            effective_count = (
                self.config.polling.battery_count
                if self.config.polling.battery_count > 0
                else len(stack.unit_telemetries)
            )
            self.publish_discovery(
                battery_count=effective_count,
                unit_infos=stack.unit_infos,
            )

        # 1. Publish Master Stack State
        stack_dict = {
            "total_voltage_v": stack.total_voltage_v,
            "total_current_a": stack.total_current_a,
            "total_power_w": stack.total_power_w,
            "soc_percent": stack.soc_percent,
            "min_soc_percent": stack.min_soc_percent,
            "max_soc_percent": stack.max_soc_percent,
            "min_cell_voltage_mv": stack.min_cell_voltage_mv,
            "max_cell_voltage_mv": stack.max_cell_voltage_mv,
            "cell_delta_mv": stack.cell_delta_mv,
            "highest_temp_c": stack.highest_temp_c,
            "lowest_temp_c": stack.lowest_temp_c,
            "total_remaining_capacity_ah": stack.total_remaining_capacity_ah,
            "total_capacity_ah": stack.total_capacity_ah,
            "total_cycles_avg": stack.total_cycles_avg,
            "active_units_count": stack.active_units_count,
            "stack_state": stack.stack_state,
            "is_charging": stack.is_charging,
            "is_discharging": stack.is_discharging,
            "has_warning": stack.has_warning,
            "has_alarm": stack.has_alarm,
            "timestamp": int(time.time()),
        }

        stack_topic = self.discovery.get_stack_state_topic()
        self._client.publish(stack_topic, json.dumps(stack_dict), qos=0, retain=False)

        # 2. Publish Individual Unit States
        now = time.time()
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        for unit_id, unit_telem in stack.unit_telemetries.items():
            volt_abnormal = unit_telem.voltage_state.lower() not in ("normal", "idle", "")
            high_cell = unit_telem.volt_high_mv >= 3500.0
            high_delta = unit_telem.cell_delta_mv >= 50.0
            if volt_abnormal or high_cell or high_delta:
                high_desc = unit_telem.highest_cell or f"Vhigh={unit_telem.volt_high_mv:.0f}mV"
                summary = (
                    f"Unit {unit_id} {unit_telem.voltage_state} @ {unit_telem.soc_percent:.0f}% SoC | "
                    f"{high_desc} | Delta={unit_telem.cell_delta_mv:.0f}mV"
                )[:255]
                entry = f"{ts_str} | {summary}"
                self._unit_last_events[unit_id] = entry[:255]
                if summary != self._last_event_summary or (now - self._last_event_time) >= 60.0:
                    self._last_event_summary = summary
                    self._last_event_time = now
                    self._event_log.insert(0, entry)
                    self._event_log = self._event_log[:30]

            unit_dict = dataclasses.asdict(unit_telem)
            unit_dict["last_voltage_event"] = self._unit_last_events.get(unit_id, "OK")
            unit_dict["timestamp"] = int(now)
            unit_topic = self.discovery.get_unit_state_topic(unit_id)
            self._client.publish(unit_topic, json.dumps(unit_dict), qos=0, retain=False)

        # 3. Publish Stack Event Log (retained so HA keeps latest event across restarts)
        events_payload = {
            "last_event": self._last_event_summary[:255],
            "event_count": len(self._event_log),
            "events": self._event_log,
            "timestamp": int(now),
        }
        self._client.publish(
            self.discovery.get_stack_events_topic(),
            json.dumps(events_payload),
            qos=0,
            retain=True,
        )

        logger.debug("Published telemetry for Stack and %d units.", len(stack.unit_telemetries))
