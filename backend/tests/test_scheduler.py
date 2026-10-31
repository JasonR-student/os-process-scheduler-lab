import unittest

from backend.app.models import SessionConfig
from backend.app.simulation import SimulationSession


class SimulationSessionTests(unittest.TestCase):
    def make_session(self, seed: int = 42) -> SimulationSession:
        return SimulationSession(
            SessionConfig(
                mode="simulation",
                seed=seed,
                initial_processes=6,
                max_processes=6,
                tick_ms=100,
            )
        )

    def test_fixed_seed_is_reproducible(self) -> None:
        first = self.make_session(42)
        second = self.make_session(42)
        for _ in range(5):
            first.step()
            second.step()
        self.assertEqual(first.snapshot()["gantt"], second.snapshot()["gantt"])
        self.assertEqual(first.snapshot()["priority_history"], second.snapshot()["priority_history"])

    def test_back_restores_previous_tick(self) -> None:
        session = self.make_session()
        initial = session.snapshot()
        session.step()
        self.assertEqual(session.snapshot()["time"], 1)
        session.back()
        restored = session.snapshot()
        self.assertEqual(restored["time"], initial["time"])
        self.assertEqual(restored["running"]["name"], initial["running"]["name"])

    def test_priority_changes_follow_course_rule(self) -> None:
        session = self.make_session()
        running_name = session.snapshot()["running"]["name"]
        session.processes[running_name].needtime = 2
        before = session.processes[running_name].prio
        waiting_name = session.ready[0]
        waiting_before = session.processes[waiting_name].prio
        session.step()
        self.assertEqual(session.processes[running_name].prio, before - 3)
        self.assertEqual(session.processes[waiting_name].prio, waiting_before + 1)

    def test_report_formula(self) -> None:
        session = self.make_session()
        process = session.processes["P1"]
        process.state = "F"
        process.finish_time = 10
        process.cputime = 3
        process.io_total = 2
        session.finished = ["P1"]
        report = session.report()["rows"][0]
        self.assertEqual(report["turnaround"], 10)
        self.assertEqual(report["wait"], 5)
        self.assertEqual(report["weighted"], 3.33)

    def test_snapshot_events_do_not_nest_snapshots(self) -> None:
        session = SimulationSession(
            SessionConfig(
                mode="simulation",
                continuous=True,
                initial_processes=6,
                max_processes=48,
                tick_ms=100,
            )
        )
        for _ in range(12):
            session.step()
        event_types = {event["type"] for event in session.snapshot()["events"]}
        self.assertNotIn("snapshot", event_types)

    def test_continuous_session_keeps_process_count_bounded(self) -> None:
        session = SimulationSession(
            SessionConfig(
                mode="simulation",
                continuous=True,
                initial_processes=6,
                max_processes=10,
                tick_ms=100,
            )
        )
        for _ in range(30):
            session.step()
        self.assertLessEqual(len(session.processes), 10)
        self.assertGreater(session.total_created, 6)


if __name__ == "__main__":
    unittest.main()
