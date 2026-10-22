"""Fixtures IPP synthétiques ; aucune impression ni annulation réelle."""

import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location("printing_backend", Path(__file__).with_name("backend.py"))
backend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backend)


class FakeConnection:
    def __init__(self, default=None, printers=None, jobs=None):
        self.default = default
        self.printers = printers or {}
        self.jobs = jobs or {}

    def getDefault(self):
        return self.default

    def getPrinters(self):
        return self.printers

    def getJobs(self, *, which_jobs, my_jobs):
        assert which_jobs == "not-completed" and my_jobs is False
        return self.jobs


class PrintingBackendTests(unittest.TestCase):
    def test_scheduler_inactive(self):
        self.assertEqual(backend.unavailable(), {
            "schema": "labfy.printing", "version": 1, "scheduler": False,
            "default_printer": None, "printers": [], "jobs": []})

    def test_scheduler_active_without_printer(self):
        value = backend.snapshot(FakeConnection())
        self.assertTrue(value["scheduler"])
        self.assertIsNone(value["default_printer"])
        self.assertEqual(value["printers"], [])
        self.assertEqual(value["jobs"], [])

    def test_default_and_multiple_printers(self):
        value = backend.snapshot(FakeConnection("A", {
            "B": {"printer-state": 5},
            "A": {"printer-state": 3, "printer-state-reasons": ["none"]},
        }))
        self.assertEqual(value["default_printer"], "A")
        self.assertEqual(value["printers"], [
            {"name": "A", "state": "ready", "default": True},
            {"name": "B", "state": "stopped", "default": False},
        ])

    def test_single_default_printer(self):
        value = backend.snapshot(FakeConnection("Laser", {
            "Laser": {"printer-state": 3}}))
        self.assertEqual(value["printers"], [
            {"name": "Laser", "state": "ready", "default": True}])

    def test_jobs_pending_processing_stopped_and_error(self):
        value = backend.snapshot(FakeConnection("A", {
            "A": {"printer-state": 4},
            "B": {"printer-state": 3, "printer-state-reasons": ["media-empty-error"]},
        }, {
            13: {"job-state": 6, "job-name": "privé.pdf", "job-printer-uri": "ipp://local/printers/B"},
            11: {"job-state": 3, "job-name": "doc.pdf", "job-printer-uri": "ipp://local/printers/A"},
            12: {"job-state": 5, "job-printer-uri": "ipp://local/printers/A"},
        }))
        self.assertEqual([job["state"] for job in value["jobs"]],
                         ["pending", "processing", "stopped"])
        self.assertEqual(value["jobs"][1]["document"], "Document sans nom")
        self.assertEqual(value["printers"][0]["state"], "printing")
        self.assertEqual(value["printers"][1]["state"], "error")

    def test_unknown_printer_is_not_ready(self):
        self.assertEqual(backend.printer_state({}), "unknown")
        self.assertEqual(backend.printer_state({"printer-state": 9}), "unknown")
        self.assertEqual(backend.printer_state({"printer-state": 3,
            "printer-state-reasons": ["device-offline"]}), "offline")

    def test_cancel_validates_id_and_passes_direct_argv(self):
        calls = []

        def runner(argv, **kwargs):
            calls.append(argv)
            return type("Result", (), {"returncode": 0})()

        for invalid in ("0", "-1", "1;echo", "A-12", "2147483648", " 12"):
            with self.assertRaises(ValueError):
                backend.cancel_job(invalid, runner)
        self.assertEqual(calls, [])
        self.assertTrue(backend.cancel_job("12", runner))
        self.assertEqual(calls, [["/usr/bin/cancel", "12"]])

    def test_cancel_failure(self):
        def runner(argv, **kwargs):
            return type("Result", (), {"returncode": 1})()
        self.assertFalse(backend.cancel_job("12", runner))


if __name__ == "__main__":
    unittest.main()
