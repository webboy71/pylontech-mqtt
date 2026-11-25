"""Unit tests for Home Assistant MQTT Discovery generator."""

import json
import unittest
from pylontech_mqtt.config import AppConfig
from pylontech_mqtt.ha_discovery import HomeAssistantDiscovery
from pylontech_mqtt.parser import UnitInfo


class TestHADiscovery(unittest.TestCase):

    def test_discovery_generation(self):
        config = AppConfig()
        discovery = HomeAssistantDiscovery(config)

        unit_infos = {
            1: UnitInfo(unit_id=1, serial_number="PPTA01", firmware_version="B65.12"),
            2: UnitInfo(unit_id=2, serial_number="PPTA02", firmware_version="B65.12"),
            3: UnitInfo(unit_id=3, serial_number="PPTA03", firmware_version="B65.12"),
            4: UnitInfo(unit_id=4, serial_number="PPTA04", firmware_version="B65.12"),
        }

        messages = discovery.build_all_discovery_messages(battery_count=4, unit_infos=unit_infos, cell_count=15)
        self.assertGreater(len(messages), 0)

        topics = [m[0] for m in messages]

        # Check Stack entities
        self.assertIn("homeassistant/sensor/pylontech_battery_stack/total_voltage/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_battery_stack/total_power/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_battery_stack/soc/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_battery_stack/cell_delta/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_battery_stack/last_event/config", topics)
        self.assertIn("homeassistant/binary_sensor/pylontech_battery_stack/is_charging/config", topics)

        # Check Unit 1 entities
        self.assertIn("homeassistant/sensor/pylontech_unit_1/voltage/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/highest_cell/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/lowest_cell/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/last_voltage_event/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/cell_1_voltage/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/cell_15_voltage/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/cell_1_temperature/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/cell_15_temperature/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/discharged_capacity/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/max_charge_current/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/soh_status/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/voltage_state/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/hv_count/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/bat_ov_times/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_1/pwr_ov_times/config", topics)
        self.assertIn("homeassistant/binary_sensor/pylontech_unit_1/voltage_warning/config", topics)

        # Check Unit 4 entities
        self.assertIn("homeassistant/sensor/pylontech_unit_4/voltage/config", topics)

        # Check payload structure of one entity
        for topic, raw_payload in messages:
            if topic == "homeassistant/sensor/pylontech_battery_stack/total_power/config":
                payload = json.loads(raw_payload)
                self.assertEqual(payload["name"], "Pylontech Stack Power")
                self.assertEqual(payload["device_class"], "power")
                self.assertEqual(payload["unit_of_measurement"], "W")
                self.assertEqual(payload["device"]["name"], "Pylontech Battery Stack")
                self.assertEqual(payload["availability_topic"], "pylontech/status")
                self.assertEqual(payload["payload_available"], "online")
            elif topic == "homeassistant/sensor/pylontech_unit_1/cell_1_voltage/config":
                payload = json.loads(raw_payload)
                self.assertEqual(payload["name"], "Unit 1 Cell 01 Voltage")
                self.assertEqual(payload["entity_category"], "diagnostic")
            elif topic == "homeassistant/sensor/pylontech_unit_1/cell_1_temperature/config":
                payload = json.loads(raw_payload)
                self.assertEqual(payload["name"], "Unit 1 Cell 01 Temperature")
                self.assertEqual(payload["entity_category"], "diagnostic")


        # Verify unit 5 is not present when battery_count=4
        self.assertNotIn("homeassistant/sensor/pylontech_unit_5/voltage/config", topics)

    def test_discovery_default_from_config(self):
        config = AppConfig()
        config.polling.battery_count = 2
        discovery = HomeAssistantDiscovery(config)

        messages = discovery.build_all_discovery_messages()
        topics = [m[0] for m in messages]

        # Should contain Unit 1 and 2
        self.assertIn("homeassistant/sensor/pylontech_unit_1/voltage/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_2/voltage/config", topics)
        # Should not contain Unit 3 or 4
        self.assertNotIn("homeassistant/sensor/pylontech_unit_3/voltage/config", topics)
        self.assertNotIn("homeassistant/sensor/pylontech_unit_4/voltage/config", topics)

    def test_cleanup_discovery_generation(self):
        config = AppConfig()
        discovery = HomeAssistantDiscovery(config)

        cleanup_messages = discovery.build_cleanup_discovery_messages(configured_count=4, max_count=8)
        self.assertGreater(len(cleanup_messages), 0)

        # All payloads must be empty string
        for topic, payload in cleanup_messages:
            self.assertEqual(payload, "")

        topics = [m[0] for m in cleanup_messages]
        # Should contain Unit 5 through Unit 8
        self.assertIn("homeassistant/sensor/pylontech_unit_5/voltage/config", topics)
        self.assertIn("homeassistant/sensor/pylontech_unit_8/voltage/config", topics)
        # Should not contain Unit 1..4
        self.assertNotIn("homeassistant/sensor/pylontech_unit_1/voltage/config", topics)
        self.assertNotIn("homeassistant/sensor/pylontech_unit_4/voltage/config", topics)

    def test_mqtt_publisher_logs_overvoltage_events(self):
        from unittest.mock import MagicMock
        from pylontech_mqtt.mqtt_publisher import MQTTPublisher
        from pylontech_mqtt.parser import BatteryTelemetry, StackTelemetry

        config = AppConfig()
        pub = MQTTPublisher(config)
        pub._connected = True
        pub._discovery_published = True
        pub._client = MagicMock()

        unit1 = BatteryTelemetry(
            unit_id=1,
            voltage_v=52.5,
            soc_percent=82.0,
            volt_low_mv=3340.0,
            volt_high_mv=3582.0,
            cell_delta_mv=242.0,
            voltage_state="OV",
            highest_cell="Cell 07 (3582mV)",
            lowest_cell="Cell 02 (3340mV)",
        )
        stack = StackTelemetry(unit_telemetries={1: unit1})

        pub.publish_telemetry(stack)

        published = {call.args[0]: json.loads(call.args[1]) for call in pub._client.publish.call_args_list}
        events_payload = published["pylontech/stack/events"]
        self.assertIn("Unit 1 OV @ 82% SoC", events_payload["last_event"])
        self.assertIn("Cell 07 (3582mV)", events_payload["last_event"])
        self.assertEqual(events_payload["event_count"], 1)
        self.assertEqual(len(events_payload["events"]), 1)

        unit_payload = published["pylontech/unit/1/state"]
        self.assertIn("Unit 1 OV @ 82% SoC", unit_payload["last_voltage_event"])


if __name__ == "__main__":
    unittest.main()
