import unittest

from tools.tactile_experiment.protocol import ExperimentProtocol, POINTS, point_from_id


class ProtocolTests(unittest.TestCase):
    def test_point_numbering(self):
        self.assertEqual(point_from_id(1).label, "R1C1")
        self.assertEqual(point_from_id(6).label, "R1C6")
        self.assertEqual(point_from_id(7).label, "R2C1")
        self.assertEqual(point_from_id(18).label, "R3C6")
        self.assertEqual(point_from_id(36).label, "R6C6")
        self.assertEqual(len(POINTS), 36)

    def test_event_order_and_counts(self):
        clock = {"now": 0.0}
        events = []
        prompts = []
        printed = []

        def sleep_fn(seconds):
            clock["now"] += seconds

        def emit(kind, **fields):
            fields["kind"] = kind
            events.append(fields)
            return fields

        protocol = ExperimentProtocol(
            emit_event=emit,
            status_provider=lambda: None,
            baseline_s=0.2,
            press_s=0.1,
            release_s=0.1,
            confirm_each=True,
            points=POINTS[:3],
            print_fn=lambda *a, **k: printed.append(" ".join(str(x) for x in a)),
            input_fn=lambda prompt: prompts.append(prompt) or "",
            sleep_fn=sleep_fn,
            clock=lambda: clock["now"],
            tick_s=0.05,
        )
        result = protocol.run()
        self.assertEqual(result["completed"], 3)
        kinds = [e["kind"] for e in events]
        self.assertEqual(kinds[0], "EXPERIMENT_START")
        self.assertEqual(kinds[-1], "EXPERIMENT_END")
        self.assertEqual(kinds.count("PRESS_START"), 3)
        self.assertEqual(kinds.count("RELEASE_START"), 3)
        self.assertEqual(kinds.count("POINT_READY"), 3)
        self.assertEqual(kinds.count("USER_READY"), 3)
        self.assertEqual(kinds.count("BASELINE_START"), 2)
        self.assertEqual(kinds.count("BASELINE_END"), 2)
        self.assertEqual(len(prompts), 3)
        # Each press must be followed by a release before the point done.
        for index, kind in enumerate(kinds):
            if kind == "PRESS_START":
                self.assertEqual(kinds[index + 1], "RELEASE_START")
            if kind == "RELEASE_START":
                self.assertEqual(kinds[index + 1], "POINT_DONE")

    def test_no_confirm(self):
        clock = {"now": 0.0}
        events = []
        protocol = ExperimentProtocol(
            emit_event=lambda kind, **fields: events.append((kind, fields)),
            status_provider=lambda: None,
            baseline_s=0.0,
            press_s=0.05,
            release_s=0.05,
            confirm_each=False,
            points=POINTS[:1],
            print_fn=lambda *a, **k: None,
            input_fn=lambda prompt: (_ for _ in ()).throw(AssertionError("input must not be called")),
            sleep_fn=lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
            clock=lambda: clock["now"],
            tick_s=0.01,
        )
        result = protocol.run()
        self.assertEqual(result["completed"], 1)
        self.assertNotIn("USER_READY", [kind for kind, _ in events])


if __name__ == "__main__":
    unittest.main()
