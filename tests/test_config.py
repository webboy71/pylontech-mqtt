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
            del os.environ["PYLON_SERIAL_PORT"]
            del os.environ["MQTT_HOST"]
            del os.environ["PYLON_BATTERY_COUNT"]


if __name__ == "__main__":
    unittest.main()
