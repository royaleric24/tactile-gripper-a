import unittest
from pathlib import Path

from tools.cup_grasp.model import ConfigurationError, load_config


class ConfigTests(unittest.TestCase):
    def test_template_is_blocked(self):
        config = load_config(Path("config/cup_grasp.template.json"))
        with self.assertRaises(ConfigurationError):
            config.require_gripper()
        with self.assertRaises(ConfigurationError):
            config.require_tactile_thresholds()

    def test_simulated_config_is_explicit(self):
        config = load_config(Path("config/cup_grasp.simulated.json"))
        self.assertTrue(config.simulated)
        self.assertEqual(config.data_kind, "SIMULATED")
        config.require_tactile_thresholds()
        config.require_gripper()


if __name__ == "__main__":
    unittest.main()
