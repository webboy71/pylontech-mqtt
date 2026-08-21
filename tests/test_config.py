"""Unit tests for configuration loader."""

import os
import unittest
from pylontech_mqtt.config import load_config


class TestConfig(unittest.TestCase):

    def test_default_config(self):
        cfg = load_config()
        self.assertEqual(cfg.serial.port, "/dev/ttyUSB0")
        self.assertEqual(cfg.serial.baudrate, 115200)
        self.assertEqual(cfg.polling.battery_count, 4)
        self.assertEqual(cfg.mqtt.topic_prefix, "pylontech")
        self.assertTrue(cfg.mqtt.ha_discovery_enabled)

    def test_env_override(self):
        os.environ["PYLON_SERIAL_PORT"] = "/dev/serial/by-id/usb-adapter-1"
        os.environ["MQTT_HOST"] = "10.0.0.99"
        os.environ["PYLON_BATTERY_COUNT"] = "6"

        try:
            cfg = load_config()
            self.assertEqual(cfg.serial.port, "/dev/serial/by-id/usb-adapter-1")
            self.assertEqual(cfg.mqtt.host, "10.0.0.99")
            self.assertEqual(cfg.polling.battery_count, 6)
        finally:
            os.environ.pop("PYLON_SERIAL_PORT", None)
            os.environ.pop("MQTT_HOST", None)
            os.environ.pop("PYLON_BATTERY_COUNT", None)

    def test_battery_count_aliases(self):
        import tempfile
        
        # Test 'units: 4'
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("polling:\n  units: 4\n")
            tmp_name = f.name

        try:
            cfg = load_config(tmp_name)
            self.assertEqual(cfg.polling.battery_count, 4)
        finally:
            os.remove(tmp_name)

        # Test 'batteries: 3'
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("polling:\n  batteries: 3\n")
            tmp_name = f.name

        try:
            cfg = load_config(tmp_name)
            self.assertEqual(cfg.polling.battery_count, 3)
        finally:
            os.remove(tmp_name)

        # Test top-level 'battery_count: 5'
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("battery_count: 5\n")
            tmp_name = f.name

        try:
            cfg = load_config(tmp_name)
            self.assertEqual(cfg.polling.battery_count, 5)
        finally:
            os.remove(tmp_name)


if __name__ == "__main__":
    unittest.main()
