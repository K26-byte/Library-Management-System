import json
import os
import tempfile
import unittest

from library import Library, LibraryError, load_library, save_library
from library.storage import from_dict, to_dict
from tests.helpers import make_library


def busy_library():
    """A library with loans, a late fine, a queue, renewals and graph edges."""
    lib, clock = make_library()
    lib.add_book("5", "Les Misérables", "Victor Hugo", 1862)
    lib.add_copies("1", 1)
    lib.issue_book("1", "A"); lib.issue_book("3", "A")          # A borrows two titles -> graph edge
    lib.issue_book("1", "B")                                    # the second copy of title 1
    lib.reserve_book("3", "C")                                  # C waits for title 3
    lib.renew_loan("1", "B")
    clock.advance(20)
    lib.return_book("1", "A")                                   # 6 days late -> Rs 12 fine
    return lib, clock


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "lib.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_round_trip_preserves_everything(self):
        lib, clock = busy_library()
        save_library(lib, self.path)
        loaded = load_library(self.path, clock)
        self.assertEqual(to_dict(loaded), to_dict(lib))
        self.assertEqual(loaded.verify(), [])

    def test_indexes_are_rebuilt_after_loading(self):
        lib, clock = busy_library()
        save_library(lib, self.path)
        loaded = load_library(self.path, clock)
        self.assertEqual([b.isbn for b in loaded.search("miserables")], ["5"])      # trie
        self.assertEqual([l.isbn for l in loaded.overdue_loans()],
                         [l.isbn for l in lib.overdue_loans()])                     # heap
        self.assertEqual(loaded.waitlist("3"), lib.waitlist("3"))                   # queue
        self.assertEqual(loaded.recommend("1")[0][1], lib.recommend("1")[0][1])     # graph

    def test_loaded_library_keeps_working(self):
        lib, clock = busy_library()
        save_library(lib, self.path)
        loaded = load_library(self.path, clock)
        fine, passed_to = loaded.return_book("3", "A")           # 6 days late; C is waiting
        self.assertEqual((fine, passed_to), (12, "C"))
        loaded.issue_book("4", "C")
        self.assertEqual(loaded.verify(), [])
        self.assertIn("3", lib.members["A"].active)              # the original is untouched

    def test_file_is_valid_utf8_json_and_no_temp_files_remain(self):
        lib, _ = busy_library()
        save_library(lib, self.path)
        with open(self.path, encoding="utf-8") as f:
            self.assertIn("Misérables", f.read())                # not escaped as \u00e9
        self.assertEqual(os.listdir(self.dir.name), ["lib.json"])

    def test_failed_save_leaves_the_old_file_untouched(self):
        lib, _ = busy_library()
        save_library(lib, self.path)
        with open(self.path, "rb") as f:
            original = f.read()
        lib.books["1"].title = object()                          # makes json.dump fail midway
        with self.assertRaises(TypeError):
            save_library(lib, self.path)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), original)
        self.assertEqual(os.listdir(self.dir.name), ["lib.json"])

    def test_bad_files_are_rejected_with_a_clear_error(self):
        with open(self.path, "w") as f:
            f.write("{ not json")
        with self.assertRaisesRegex(LibraryError, "not valid JSON"):
            load_library(self.path)
        lib, _ = busy_library()
        good = to_dict(lib)
        for mutate, message in [
            (lambda d: d.pop("books"), "damaged"),
            (lambda d: d.update(version=99), "version"),
            (lambda d: d["books"][0].update(available=99), "inconsistent"),
            (lambda d: d["waitlists"].update({"NOPE": ["A"]}), "inconsistent"),
        ]:
            data = json.loads(json.dumps(good))
            mutate(data)
            with self.assertRaisesRegex(LibraryError, message):
                from_dict(data)

    def test_empty_library_round_trip(self):
        save_library(Library(), self.path)
        self.assertEqual(load_library(self.path).books, {})


if __name__ == "__main__":
    unittest.main()
