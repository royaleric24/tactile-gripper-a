import unittest

from tools.tactile_experiment.multiround import (
    APPROACH,
    NO_CONTACT,
    PRESS,
    RoundProtocol,
    RoundSchedule,
    Segment,
)
from tools.tactile_experiment.protocol import POINTS


class RoundProtocolTests(unittest.TestCase):
    def test_press_and_control_event_order(self):
        clock = {"now": 0.0}
        events = []
        prompts = []
        schedule = RoundSchedule(
            1, 42,
            [
                Segment(1, PRESS, POINTS[0], None, 0.1, 0.1),
                Segment(2, APPROACH, POINTS[1], 1, 0.1, 0.1),
                Segment(3, NO_CONTACT, None, 1, 0.1, 0.1),
            ],
            [1],
        )

        def emit(kind, **fields):
            events.append((kind, fields))
            return fields

        protocol = RoundProtocol(
            schedule,
            emit_event=emit,
            status_provider=lambda: None,
            baseline_s=0.1,
            confirm_each=True,
            print_fn=lambda *a, **k: None,
            input_fn=lambda prompt: prompts.append(prompt) or "",
            sleep_fn=lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
            clock=lambda: clock["now"],
            tick_s=0.05,
        )
        result = protocol.run()
        kinds = [kind for kind, _ in events]
        self.assertEqual(result["completed_presses"], 1)
        self.assertEqual(kinds[0], "ROUND_START")
        self.assertEqual(kinds[-1], "ROUND_END")
        self.assertIn("PRESS_START", kinds)
        self.assertIn("RELEASE_START", kinds)
        self.assertIn("APPROACH_START", kinds)
        self.assertIn("APPROACH_END", kinds)
        self.assertIn("NO_CONTACT_START", kinds)
        self.assertIn("NO_CONTACT_END", kinds)
        self.assertEqual(len(prompts), 3)
        press_index = kinds.index("PRESS_START")
        self.assertEqual(kinds[press_index + 1], "RELEASE_START")
        approach_index = kinds.index("APPROACH_START")
        self.assertEqual(kinds[approach_index + 1], "APPROACH_END")
        no_contact_index = kinds.index("NO_CONTACT_START")
        self.assertEqual(kinds[no_contact_index + 1], "NO_CONTACT_END")
        # Labels are present in events but not in the protocol's feature path.
        press_event = dict(events[press_index][1])
        self.assertEqual(press_event["segment_kind"], PRESS)
        self.assertEqual(press_event["point_id"], 1)


if __name__ == "__main__":
    unittest.main()
