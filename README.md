# Library Management System

A command-line library system in Python where every feature is built around a data structure chosen for the job. Three of those structures (a Trie, a min-heap and a linked-list queue) plus merge sort are written from scratch. Standard library only, no installs.

## Try it in two minutes

```
python main.py --demo         # interactive menu; a NEW library starts with 10 sample books and 4 members
                              # (later runs reload your saved data)
python demo.py                # a narrated walkthrough of every feature (nothing to type)
python benchmark.py           # measures the complexity claims on your own machine
python -m unittest            # runs the 76 tests (run from this folder)
```

Written for Python 3.8+ (standard library only); developed and tested on 3.12. Data is saved automatically to `library_data.json`.

**See overdue loans and fines without waiting two weeks:** issue a book in the menu, quit, then start again with a later date:
`python main.py --today 2030-01-01` and choose "Overdue loans" (any date after the due date works).

## What it can do

- **Catalog:** add titles, add copies, remove titles, with input validation.
- **Search:** by any word (or word *prefix*) of the title or author, accent-insensitive (`miserables` finds *Les Misérables*), sortable by title, author, year or popularity.
- **Loans:** issue, return and renew, with a 14-day period, a 3-book limit and 2 renewals.
- **Waitlist:** reserve a book that is out; when it comes back it goes to the first *eligible* person in the queue automatically. Cancelling a reservation is instant.
- **Fines:** Rs 2 per day late, recorded on the member's account. Members with unpaid fines or overdue books cannot borrow more.
- **Overdue report:** most overdue first.
- **Undo:** reverses the last action exactly (issue, return including a waitlist hand-off, renewal, reservation, cancellation, fine payment).
- **Insights:** most popular titles, and "members who borrowed this also borrowed...".
- **Persistence:** JSON file, written atomically; checked for consistency when loaded.

## Data structures and where they are used

| Feature | Structure | Written by | Time |
|---|---|---|---|
| Look up a book, member or loan by ID | Hash map (`dict`) | built-in | O(1) |
| "Has this member borrowed this title before?" | Hash set | built-in | O(1) |
| Search by word prefix | **Trie** | hand-written (`structures.py`) | O(L + matches) |
| Order search results | **Merge sort** (stable) | hand-written | O(n log n) |
| Overdue loans | **Min-heap** keyed by due date | hand-written | O(log n) per push/pop; a report costs O(k log n) for k overdue loans |
| Waitlist per book | **Doubly linked list + hash map** (`IndexedQueue`) | hand-written | O(1) join, serve, cancel, "is X waiting?" |
| Undo | Stack of reversal closures | `list`/`deque` | O(1) |
| Most popular titles | **Bounded min-heap** (top-k) | hand-written | O(n log k) |
| Recommendations | Weighted **graph** (adjacency dict) + top-k | built-in + hand-written | O(d log k), d = neighbours |

## Design decisions worth knowing (and defending)

**Why the waitlist is not a plain queue.** A `deque` can't remove someone from the middle in O(1), and can't answer "is Ravi already waiting?" in O(1). `IndexedQueue` keeps a doubly linked list for order and a hash map pointing straight at each node (the same idea as an LRU cache). Cancelling is then O(1), and undo can put a member back at their exact original position.

**Why the heap uses lazy deletion.** A heap cannot cheaply remove or re-prioritise an item in the middle. So when a loan is returned, undone or renewed, its old heap entry is simply left behind and discarded when it reaches the top, by checking it against the live loan record. A renewal costs one push. Every entry is popped at most once, so the extra work is amortised away.

**Why undo is a stack of closures (command pattern).** Each action stores exactly how to reverse itself, so there is no giant `if action == "issue"` ladder, and adding a new undoable action is one function. Catalog changes (adding copies, removing a title) are not undoable and discard undo entries for that title, because those entries would no longer be valid.

**Why the recommendation weight counts members, not borrowings.** An edge is added only the first time a member borrows a title, so one keen reader borrowing the same two books five times counts once.

**Why the Trie indexes words, not whole titles.** So `alg` matches *Introduction to **Alg**orithms*. A multi-word query intersects the sets from each word.

**Why persistence stores only facts.** Books, members, loans, queues and graph weights are saved; the tries and heap are rebuilt on load, and `Library.verify()` cross-checks every structure against the others. A hand-edited or damaged file is refused with a clear message instead of being silently trusted (and the CLI will not overwrite it).

**Why my merge sort is slower than `sorted()`.** Python's built-in is written in C. The benchmark shows this honestly; the point of the hand-written version is that it is stable (so "sort by year, ties by title" works as two passes) and can be explained line by line.

## How it is tested

- **Targeted tests** for every rule and every bug fixed along the way.
- **Randomised tests** perform about 15,000 random operations and, after *every* step, check that all structures agree with each other (`verify()`), that the recommendation graph matches a from-scratch recomputation, that the overdue list matches a brute-force scan, that a failed action changed nothing, and that **undo restores the exact previous state** (and that undoing a whole session returns to the start).
- **Mutation check:** I deliberately injected 12 different bugs (wrong heap direction, lost stability, stale heap entries, broken undo, ...) and confirmed the suite catches every one.

## Measured behaviour (`python benchmark.py`, one run on my machine)

| | small | large |
|---|---|---|
| Prefix lookup, Trie vs scanning every book (2,000 → 40,000 books) | ~3 µs vs ~2 ms | ~7 µs vs ~30-50 ms |
| Overdue loans, heap vs checking every loan (2,000 → 40,000 loans) | ~35 µs vs 0.1 ms | ~40 µs vs 1.8 ms |
| Merge sort, time per n·log₂n (10k → 80k items) | ~130 ns | ~140-170 ns (flat, as O(n log n) predicts) |

The Trie and heap times stay almost flat as the data grows twentyfold, while the naive approaches grow with it. Exact numbers depend on your machine.

## Project layout

```
main.py             interactive menu (autosaves; --data, --today, --demo)
demo.py             scripted walkthrough
benchmark.py        timing experiments
library/
  structures.py     Trie, MinHeap, IndexedQueue, merge_sort, top_k   (hand-written)
  system.py         Library: the rules, undo, search, reports, verify()
  models.py         Book, Member, Loan records
  storage.py        JSON save/load (atomic write, consistency check)
  text.py           accent folding and tokenising (handles Indian scripts too)
  sample_data.py    demo books and members
tests/              76 tests, including the randomised ones
```

## Known limits

- One user at a time. Two programs editing the same data file would overwrite each other.
- No member deletion, passwords or ISBN checksum validation.
- Undo history lasts for the current session only (it is not saved).
- If a waiting member becomes eligible later (e.g. pays their fines) they are not served automatically; they can still borrow the copy if it is free.

## Ideas for extending it

A Tkinter or Flask front end, an AVL tree for year-range queries, fuzzy search using edit distance, email reminders for due dates.
