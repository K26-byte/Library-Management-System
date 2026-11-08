# Library Management System

A library system you run from the command line(GUI is difficult [ T—T ] ), written in Python. I built it as the final project for my data structures and algorithms course. The brief was only "build a library management system", so I decided the data structures should be the whole point. Every feature runs on a structure chosen for that job, and the main ones are written by hand instead of borrowed from Python.

## What it does

You can add, remove and search books, lend them out, take them back, and keep track of who owes what. A few things I'm semi-happy with:

- **Search as you'd actually type it.** Any word or the start of a word in the title or author works, so `alg` finds *Introduction to Algorithms*. Accents don't matter either: `miserables` finds *Les Misérables*, honestly the book is a bit over hyped by it's fans.
- **A waitlist.** If a book is out, you can join the queue. When it comes back, it goes to the next person in line automatically.
- **Fines and renewals.** Late books cost Rs 2 a day, added to the member's account. Anyone with unpaid fines or an overdue book can't borrow more until they sort it out.
- **Undo.** It's rather obvious...
- **Recommendations.** "Members who borrowed this also borrowed...". No I am not stealing your personal details for this.
- **It remembers.** The title makes it sound dramatic. Everything is saved to a file, so closing the program doesn't lose anything. 

The default rules are a 14-day loan, 3 books per member at a time, and 2 renewals. They're constants at the top of the `Library` class if you want to change them.

## Running it

You need Python 3.8 or newer. There is nothing to install. I developed it on Python 3.15.

```
python main.py --demo      # the interactive menu, with sample books and members to play with
python demo.py             # a walkthrough of every feature that runs by itself
python benchmark.py        # timing experiments (about 6 seconds)
python -m unittest         # the test suite (run it from this folder)
```

The first time you run `main.py --demo` it creates a new library with 10 books and 4 members (M1 to M4). After that it reloads whatever you saved in `library_data.json`.

If you want to see overdue books and fines without waiting two weeks, lend a book, quit, and start it again with a pretend date:

```
python main.py --today 2030-01-01
```

Then pick "Overdue loans" from the menu.

## The data structures

| What it's used for | Structure | Written by me? |
|---|---|---|
| Finding a book, member or loan by ID | Hash map (`dict`) | No, built in |
| Searching by word prefix | Trie | Yes |
| Sorting search results | Merge sort | Yes |
| Spotting overdue loans | Min-heap ordered by due date | Yes |
| The waitlist for each book | Linked list + hash map | Yes |
| Undo | A stack | Built in |
| Most popular books | Min-heap that only keeps the top k | Yes |
| Recommendations | Weighted graph | Built in |

The hand-written ones are all in `library/structures.py`, and the rules that tie them together are in `library/system.py`.

## A few choices worth explaining

**The waitlist isn't a plain queue.** With a normal queue you can't pull someone out of the middle quickly, and you can't ask "is this person already waiting?" without scanning the whole thing. So each queue is a doubly linked list with a hash map pointing at every node. Joining, serving and cancelling are all O(1). It also lets undo put someone back in exactly the spot they left.

**The overdue heap never deletes anything from the middle.** Removing an item from the middle of a heap is awkward. So when a loan is returned or renewed, I leave its old entry in the heap and just ignore it when it eventually reaches the top, by checking it against the real loan record. Lazy deletion. A renewal costs one push, and checking for overdue books only touches the loans that are actually overdue instead of looking at all of them.

**Undo is a stack of "how to reverse this" functions.** Each action saves the exact steps to undo itself at the moment it happens, so there's no giant if/else deciding what to do later. The one exception is changes to the catalog (adding copies, removing a title). Those aren't undoable, and they clear the undo history for that title, because the old entries wouldn't make sense any more(at least that's how I did that, there might be better ways to implement this function).

**Recommendations count people, not borrowings.** A link between two books is only added the first time a member borrows each one. Otherwise one person re-borrowing the same two books five times would look like five people.

**My merge sort is slower than Python's `sorted()`.** That's expected(it is to me), since the built-in one is written in C. `benchmark.py` shows this honestly. I kept my own because it's stable (equal items stay in their original order), which is how "sort by year, ties broken by title" works, and because I can explain every line of it(somewhat...).

## How I tested it (Yeah I didn't just let it free into GitHub immediately after creating it)

There are 76 tests. Most check one rule each, and I wrote a test for every bug I found along the way. The most useful ones are randomised: they run around 15,000 random actions and, after every single step, check that all the structures still agree with each other and that undo puts everything back exactly as it was. Failed actions are also checked to make sure they change nothing.

`benchmark.py` backs up the complexity claims with real timings. In my runs, looking up a word prefix with the Trie was hundreds to thousands of times faster than scanning every book, and the gap grew as the library got bigger.

## What it doesn't do (As awesome as I am, I unfortunately cannot do everything.)

- It's for one person at a time. If two copies of the program edit the same data file, the last one to save wins.
- Members can't be deleted, and there are no passwords.
- ISBNs aren't checked for validity. The ones in the sample data are just examples.
- Undo only lasts for the current session.
- If someone on a waitlist becomes allowed to borrow later (for example by paying their fines), the book isn't handed to them automatically. They can still borrow it themselves if it's free.

## Project layout

```
main.py            the interactive menu
demo.py            the walkthrough
benchmark.py       timing experiments
library/
  structures.py    Trie, heap, linked-list queue, merge sort, top-k
  system.py        the Library class: rules, search, undo, reports
  models.py        Book, Member and Loan records
  storage.py       saving and loading the JSON file
  text.py          lowercasing and accent handling for search
  sample_data.py   the demo books and members
tests/             the test suite
```

## What I'd add next (Being very optimistic here)

A tree for searching by year range, typo-tolerant search, and due-date reminders.

## Added the GUI (Calm down it's just Tkinter)

Simple stuff. I added it cause I had enough time to design some very basic stuff.
