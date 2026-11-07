"""Demo books and members (shared by main.py --demo and demo.py)."""

BOOKS = [
    # isbn,            title,                          author,              year, copies
    ("9780262033848", "Introduction to Algorithms",   "Thomas H. Cormen",   2009, 2),
    ("9780321573513", "Algorithms",                   "Robert Sedgewick",   2011, 1),
    ("9780132350884", "Clean Code",                   "Robert C. Martin",   2008, 1),
    ("9780201633610", "Design Patterns",              "Erich Gamma",        1994, 1),
    ("9780131103627", "The C Programming Language",   "Brian Kernighan",    1988, 2),
    ("9780262510875", "Structure and Interpretation of Computer Programs",
                                                      "Harold Abelson",     1996, 1),
    ("9780134685991", "Effective Java",               "Joshua Bloch",       2018, 1),
    ("9780596517748", "JavaScript: The Good Parts",   "Douglas Crockford",  2008, 1),
    ("9780201616224", "The Pragmatic Programmer",     "Andrew Hunt",        1999, 1),
    ("9781492056355", "Fluent Python",                "Luciano Ramalho",    2022, 2),
]

MEMBERS = [("M1", "Asha"), ("M2", "Ravi"), ("M3", "Meera"), ("M4", "Kiran")]


def seed(lib):
    for book in BOOKS:
        lib.add_book(*book)
    for member in MEMBERS:
        lib.add_member(*member)
