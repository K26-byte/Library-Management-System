import random
import unittest

from library.structures import IndexedQueue, MinHeap, Trie, merge_sort, top_k
from library.text import fold, tokenize


class MergeSortTests(unittest.TestCase):
    def test_matches_builtin_sorted(self):
        rng = random.Random(1)
        for n in (0, 1, 2, 3, 10, 257):
            data = [rng.randint(0, 50) for _ in range(n)]
            self.assertEqual(merge_sort(data), sorted(data))
            self.assertEqual(merge_sort(data, reverse=True), sorted(data, reverse=True))

    def test_stable_in_both_directions(self):
        pairs = [(1, "a"), (0, "b"), (1, "c"), (0, "d")]
        self.assertEqual(merge_sort(pairs, key=lambda p: p[0]),
                         [(0, "b"), (0, "d"), (1, "a"), (1, "c")])
        self.assertEqual(merge_sort(pairs, key=lambda p: p[0], reverse=True),
                         [(1, "a"), (1, "c"), (0, "b"), (0, "d")])

    def test_does_not_modify_its_input(self):
        data = [3, 1, 2]
        merge_sort(data)
        self.assertEqual(data, [3, 1, 2])

    def test_key_is_computed_once_per_item(self):
        calls = []
        merge_sort(list(range(50)), key=lambda x: calls.append(x) or x)
        self.assertEqual(len(calls), 50)


class HeapTests(unittest.TestCase):
    def test_pops_in_sorted_order_and_keeps_heap_property(self):
        rng = random.Random(2)
        heap, data = MinHeap(), [rng.randint(0, 999) for _ in range(300)]
        for x in data:
            heap.push(x)
            self.assertTrue(heap.is_valid())
        self.assertEqual(heap.peek(), min(data))
        self.assertEqual([heap.pop() for _ in data], sorted(data))

    def test_interleaved_push_pop_matches_reference(self):
        rng, heap, model = random.Random(3), MinHeap(), []
        for _ in range(500):
            if model and rng.random() < 0.4:
                model.sort()
                self.assertEqual(heap.pop(), model.pop(0))
            else:
                x = rng.randint(0, 100)
                heap.push(x)
                model.append(x)
            self.assertTrue(heap.is_valid())
            self.assertEqual(len(heap), len(model))

    def test_empty_heap_errors(self):
        with self.assertRaises(IndexError):
            MinHeap().pop()
        with self.assertRaises(IndexError):
            MinHeap().peek()


class TrieTests(unittest.TestCase):
    def test_prefix_search_and_remove(self):
        t = Trie()
        t.insert("python", "1")
        t.insert("pytorch", "2")
        t.insert("java", "3")
        self.assertEqual(t.starts_with("py"), {"1", "2"})
        self.assertEqual(t.starts_with("python"), {"1"})
        self.assertEqual(t.starts_with("pythons"), set())
        t.remove("python", "1")
        self.assertEqual(t.starts_with("py"), {"2"})

    def test_remove_prunes_empty_branches(self):
        t = Trie()
        t.insert("abc", "1")
        t.insert("abd", "2")
        t.remove("abc", "1")
        t.remove("abd", "2")
        self.assertEqual(t.root.children, {})

    def test_remove_keeps_shorter_words_that_share_a_path(self):
        t = Trie()
        t.insert("car", "1")
        t.insert("cart", "2")
        t.remove("cart", "2")
        self.assertEqual(t.starts_with("car"), {"1"})

    def test_remove_missing_word_is_harmless(self):
        t = Trie()
        t.insert("abc", "1")
        t.remove("xyz", "1")
        t.remove("ab", "9")
        self.assertEqual(t.starts_with("a"), {"1"})


class IndexedQueueTests(unittest.TestCase):
    def test_fifo_order(self):
        q = IndexedQueue()
        for k in "abc":
            q.enqueue(k)
        self.assertEqual([q.dequeue(), q.dequeue(), q.dequeue()], ["a", "b", "c"])
        with self.assertRaises(IndexError):
            q.dequeue()

    def test_remove_from_middle_and_membership(self):
        q = IndexedQueue()
        for k in "abcd":
            q.enqueue(k)
        q.remove("b")
        self.assertNotIn("b", q)
        self.assertIn("c", q)
        self.assertEqual(list(q), ["a", "c", "d"])
        with self.assertRaises(KeyError):
            q.remove("zzz")

    def test_duplicate_enqueue_rejected(self):
        q = IndexedQueue()
        q.enqueue("a")
        with self.assertRaises(ValueError):
            q.enqueue("a")

    def test_predecessor_and_insert_after_restore_position(self):
        q = IndexedQueue()
        for k in "abc":
            q.enqueue(k)
        self.assertIsNone(q.predecessor("a"))
        self.assertEqual(q.predecessor("c"), "b")
        pred = q.predecessor("b")
        q.remove("b")
        q.insert_after(pred, "b")
        self.assertEqual(list(q), ["a", "b", "c"])
        q.remove("a")
        q.insert_after(None, "a")
        self.assertEqual(list(q), ["a", "b", "c"])

    def test_random_operations_match_a_plain_list(self):
        rng, q, model, fresh = random.Random(4), IndexedQueue(), [], 0
        for _ in range(2000):
            op = rng.choice(["enqueue", "dequeue", "remove", "front", "after"])
            if op == "enqueue":
                fresh += 1
                q.enqueue(fresh)
                model.append(fresh)
            elif op == "front":
                fresh += 1
                q.push_front(fresh)
                model.insert(0, fresh)
            elif op == "after":
                fresh += 1
                pred = rng.choice(model) if model else None
                q.insert_after(pred, fresh)
                model.insert(model.index(pred) + 1 if pred is not None else 0, fresh)
            elif op == "dequeue" and model:
                self.assertEqual(q.dequeue(), model.pop(0))
            elif op == "remove" and model:
                victim = rng.choice(model)
                q.remove(victim)
                model.remove(victim)
            self.assertEqual(list(q), model)
            self.assertEqual(len(q), len(model))


class TopKTests(unittest.TestCase):
    def test_matches_sorting_including_tie_order(self):
        rng = random.Random(5)
        items = [(rng.randint(0, 9), i) for i in range(80)]
        for k in (0, 1, 5, 80, 200):
            expected = sorted(items, key=lambda t: -t[0])[:k]   # stable: earlier first on ties
            self.assertEqual(top_k(items, k, key=lambda t: t[0]), expected)


class TextTests(unittest.TestCase):
    def test_accents_and_case_are_folded(self):
        self.assertEqual(fold("Les Misérables"), "les miserables")
        self.assertEqual(tokenize("Crème brûlée à la façon de ZOË"),
                         ["creme", "brulee", "a", "la", "facon", "de", "zoe"])

    def test_punctuation_splits_words(self):
        self.assertEqual(tokenize("C++ & Python 3.12!"), ["c", "python", "3", "12"])

    def test_indic_scripts_keep_their_vowel_signs(self):
        self.assertEqual(tokenize("भारत का संविधान"), ["भारत", "का", "संविधान"])
        self.assertEqual(tokenize("ಕನ್ನಡ ಸಾಹಿತ್ಯ"), ["ಕನ್ನಡ", "ಸಾಹಿತ್ಯ"])


if __name__ == "__main__":
    unittest.main()
