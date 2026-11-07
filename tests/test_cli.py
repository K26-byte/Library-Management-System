import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

import main as cli
from library import load_library


def run_cli(args, inputs):
    """Run the CLI with scripted keyboard input; returns (exit code, printed text)."""
    out = io.StringIO()
    with mock.patch("builtins.input", side_effect=inputs), contextlib.redirect_stdout(out):
        code = cli.main(args)
    return code, out.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "data.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_issue_report_undo_and_autosave(self):
        code, text = run_cli(["--data", self.path, "--demo"], [
            "6", "9780262033848", "m1",          # issue
            "12", "M1",                          # member report
            "18", "y",                           # undo
            "0"])
        self.assertEqual(code, 0)
        self.assertIn("Issued 'Introduction to Algorithms' to Asha", text)
        self.assertIn("Introduction to Algorithms", text.split("Currently borrowing")[1])
        self.assertIn("Undid issue of", text)
        lib = load_library(self.path)
        self.assertEqual(lib.members["M1"].active, {})           # the undo was saved too

    def test_errors_are_reported_not_raised(self):
        code, text = run_cli(["--data", self.path, "--demo"], [
            "6", "000", "M1",                    # unknown book
            "13", "M1",                          # no fines to pay
            "1", "1", "T", "A", "abc",           # year is not a number
            "99", "0"])
        self.assertEqual(code, 0)
        self.assertIn("! No book with ISBN 000", text)
        self.assertIn("! Asha has no fines to pay", text)
        self.assertIn("! Please enter a whole number", text)
        self.assertIn("Invalid choice", text)

    def test_search_prints_a_table(self):
        _, text = run_cli(["--data", self.path, "--demo"], ["4", "robert alg", "title", "0"])
        self.assertIn("Algorithms", text)
        self.assertIn("Robert Sedgewick", text)
        self.assertNotIn("Clean Code", text)

    def test_end_of_input_exits_cleanly(self):
        code, text = run_cli(["--data", self.path, "--demo"], [EOFError()])
        self.assertEqual(code, 0)
        self.assertIn("Goodbye", text)

    def test_ctrl_d_or_ctrl_c_at_the_startup_question_exits_cleanly(self):
        """(Bug found by a manual run: EOF at the very first prompt printed a traceback.)"""
        for interrupt in (EOFError(), KeyboardInterrupt()):
            code, text = run_cli(["--data", self.path], [interrupt])
            self.assertEqual(code, 0)
            self.assertIn("Goodbye", text)
            self.assertFalse(os.path.exists(self.path))          # nothing half-created

    def test_answering_no_to_demo_data_starts_an_empty_library(self):
        code, _ = run_cli(["--data", self.path], ["n", "11", "m9", "Zed", "0"])
        self.assertEqual(code, 0)
        lib = load_library(self.path)
        self.assertEqual((len(lib.books), list(lib.members)), (0, ["M9"]))

    def test_existing_data_is_loaded_and_today_can_be_simulated(self):
        run_cli(["--data", self.path, "--demo"], ["6", "9780262033848", "M1", "0"])
        _, text = run_cli(["--data", self.path, "--today", "2099-01-01"], ["14", "0"])
        self.assertIn("Loaded", text)
        self.assertIn("Simulated date: 2099-01-01", text)
        self.assertIn("Asha (M1)", text)                         # listed as overdue

    def test_damaged_data_file_is_not_overwritten(self):
        with open(self.path, "w") as f:
            f.write("{ broken")
        code, text = run_cli(["--data", self.path], [])
        self.assertEqual(code, 1)
        self.assertIn("Could not open", text)
        with open(self.path) as f:
            self.assertEqual(f.read(), "{ broken")


if __name__ == "__main__":
    unittest.main()
