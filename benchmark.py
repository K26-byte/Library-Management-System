#!/usr/bin/env python3
"""Measures the complexity claims instead of just asserting them.  Run: python benchmark.py

Everything is timed on your machine; the absolute numbers will differ, the SHAPE will not.
"""
import math
import random
import time
from datetime import date, timedelta

from library import Library
from library.structures import merge_sort
from library.text import tokenize


def timed(fn, repeat):
    """Average seconds per call over `repeat` calls."""
    start = time.perf_counter()
    for _ in range(repeat):
        fn()
    return (time.perf_counter() - start) / repeat


def best_of(fn, repeat):
    """Fastest single call out of `repeat` (the standard way to reduce timing noise)."""
    best = float("inf")
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def pseudo_words(rng, count):
    letters = "abcdefghijklmnopqrstuvwxyz"
    return ["".join(rng.choice(letters) for _ in range(rng.randint(5, 9))) for _ in range(count)]


def prefix_search_benchmark():
    print("\n1. Prefix lookup: Trie vs scanning every book")
    print(f"   {'books':>8}  {'trie':>12}  {'linear scan':>12}  {'speed-up':>9}")
    rng = random.Random(7)
    vocabulary = pseudo_words(rng, 4000)
    for n in (2_000, 10_000, 40_000):
        lib, scan_data = Library(), []
        for i in range(n):
            title = " ".join(rng.choice(vocabulary) for _ in range(3))
            author = " ".join(rng.choice(vocabulary) for _ in range(2))
            lib.add_book(str(i), title, author, 2000)
            scan_data.append((str(i), tokenize(title) + tokenize(author)))
        prefixes = [rng.choice(vocabulary)[:4] for _ in range(50)]
        trie = timed(lambda: [lib.title_index.starts_with(p) | lib.author_index.starts_with(p)
                              for p in prefixes], 5) / len(prefixes)
        scan = timed(lambda: [[i for i, toks in scan_data if any(t.startswith(p) for t in toks)]
                              for p in prefixes[:5]], 1) / 5
        print(f"   {n:>8,}  {trie * 1e6:>9.1f} us  {scan * 1e3:>9.2f} ms  {scan / trie:>8.0f}x")


def overdue_benchmark():
    print("\n2. Finding overdue loans: min-heap vs checking every loan (always 10 overdue)")
    print(f"   {'open loans':>10}  {'heap':>12}  {'check all':>12}  {'speed-up':>9}")
    for n in (2_000, 10_000, 40_000):
        now = [date(2026, 1, 1)]
        lib = Library(today=lambda: now[0])
        for i in range(n):
            lib.add_book(f"B{i}", f"Title {i}", "Author", 2000)
        for i in range(10):
            lib.add_member(f"U{i}", "late")
            lib.issue_book(f"B{i}", f"U{i}")
        now[0] += timedelta(days=20)                          # those 10 are now overdue
        for i in range(10, n):
            member = f"V{i // 3}"
            if member not in lib.members:
                lib.add_member(member, "on time")
            lib.issue_book(f"B{i}", member)
        assert len(lib.overdue_loans()) == 10
        heap = best_of(lib.overdue_loans, 200)
        scan = timed(lambda: [l for l in lib.loans.values()
                              if l.returned_on is None and l.due < now[0]], 20)
        print(f"   {n:>10,}  {heap * 1e6:>9.1f} us  {scan * 1e3:>9.2f} ms  {scan / heap:>8.0f}x")


def sort_benchmark():
    print("\n3. Merge sort grows like n log n (time / (n log2 n) stays roughly constant)")
    print(f"   {'n':>8}  {'merge_sort':>12}  {'ns per n*log2(n)':>17}  {'built-in sorted':>16}")
    rng = random.Random(3)
    for n in (10_000, 20_000, 40_000, 80_000):
        data = [rng.random() for _ in range(n)]
        mine = best_of(lambda: merge_sort(data), 7)
        theirs = best_of(lambda: sorted(data), 7)
        print(f"   {n:>8,}  {mine * 1e3:>9.1f} ms  {mine / (n * math.log2(n)) * 1e9:>17.1f}  "
              f"{theirs * 1e3:>13.2f} ms")
    print("   (The built-in is far faster because it is written in C; this one exists to be understood.)")


if __name__ == "__main__":
    prefix_search_benchmark()
    overdue_benchmark()
    sort_benchmark()
