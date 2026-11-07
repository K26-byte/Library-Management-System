"""Hand-written data structures used by the Library Management System.

    Trie          prefix search over titles / authors
    MinHeap       overdue tracking (earliest due date first)
    IndexedQueue  waitlists: FIFO queue + O(1) removal of any member
    merge_sort    stable O(n log n) sort
    top_k         the k largest items using a bounded min-heap
"""


# --------------------------------------------------------------------------- Trie
class TrieNode:
    __slots__ = ("children", "ids")

    def __init__(self):
        self.children = {}   # character -> TrieNode
        self.ids = set()     # items whose word ends exactly here


class Trie:
    """Prefix tree mapping words to a set of item ids (here: ISBNs)."""

    def __init__(self):
        self.root = TrieNode()

    def insert(self, word, item):
        """O(L), L = len(word)."""
        node = self.root
        for ch in word:
            node = node.children.setdefault(ch, TrieNode())
        node.ids.add(item)

    def remove(self, word, item):
        """O(L). Prunes branches that no longer lead to any item."""
        path, node = [], self.root
        for ch in word:
            if ch not in node.children:
                return
            path.append((node, ch))
            node = node.children[ch]
        node.ids.discard(item)
        for parent, ch in reversed(path):
            child = parent.children[ch]
            if child.children or child.ids:
                break
            del parent.children[ch]

    def starts_with(self, prefix):
        """O(L + size of the matching subtree). Returns a set of item ids."""
        node = self.root
        for ch in prefix:
            node = node.children.get(ch)
            if node is None:
                return set()
        found, stack = set(), [node]
        while stack:
            n = stack.pop()
            found |= n.ids
            stack.extend(n.children.values())
        return found


# ------------------------------------------------------------------------ MinHeap
class MinHeap:
    """Binary min-heap stored in a list; items are compared with < and <=."""

    def __init__(self):
        self._a = []

    def __len__(self):
        return len(self._a)

    def peek(self):
        """O(1)."""
        if not self._a:
            raise IndexError("peek at empty heap")
        return self._a[0]

    def push(self, item):
        """O(log n): add at the end, then sift up."""
        a = self._a
        a.append(item)
        i = len(a) - 1
        while i > 0:
            parent = (i - 1) // 2
            if a[parent] <= a[i]:
                break
            a[parent], a[i] = a[i], a[parent]
            i = parent

    def pop(self):
        """O(log n): remove the smallest; move the last item to the root and sift down."""
        a = self._a
        if not a:
            raise IndexError("pop from empty heap")
        top, last = a[0], a.pop()
        if a:
            a[0] = last
            i, n = 0, len(a)
            while True:
                left, right, smallest = 2 * i + 1, 2 * i + 2, i
                if left < n and a[left] < a[smallest]:
                    smallest = left
                if right < n and a[right] < a[smallest]:
                    smallest = right
                if smallest == i:
                    break
                a[i], a[smallest] = a[smallest], a[i]
                i = smallest
        return top

    # -- inspection helpers (used by self-checks and tests) --
    def items(self):
        return list(self._a)

    def is_valid(self):
        """True if every parent <= its children (the heap property)."""
        a = self._a
        return all(a[(i - 1) // 2] <= a[i] for i in range(1, len(a)))


# ------------------------------------------------------------------ IndexedQueue
class _QueueNode:
    __slots__ = ("key", "prev", "next")

    def __init__(self, key=None):
        self.key = key
        self.prev = None
        self.next = None


class IndexedQueue:
    """FIFO queue = doubly linked list + hash map (the same idea as an LRU cache).

    A plain list or deque cannot remove a member from the middle in O(1), and cannot
    answer "is X waiting?" in O(1). Here the hash map points straight at the node, so:

        enqueue / dequeue / push_front / remove(any member) / `in`  ->  O(1)
    """

    def __init__(self):
        self._head = _QueueNode()   # sentinels: no special cases for empty / end
        self._tail = _QueueNode()
        self._head.next = self._tail
        self._tail.prev = self._head
        self._index = {}            # key -> node

    def __len__(self):
        return len(self._index)

    def __contains__(self, key):
        return key in self._index

    def __iter__(self):
        node = self._head.next
        while node is not self._tail:
            yield node.key
            node = node.next

    def _insert_after(self, left, key):
        if key in self._index:
            raise ValueError(f"{key!r} is already in the queue")
        node = _QueueNode(key)
        node.prev, node.next = left, left.next
        left.next.prev = node
        left.next = node
        self._index[key] = node

    def enqueue(self, key):
        self._insert_after(self._tail.prev, key)

    def push_front(self, key):
        self._insert_after(self._head, key)

    def insert_after(self, pred_key, key):
        """Insert `key` right behind `pred_key` (None = at the front)."""
        left = self._head if pred_key is None else self._index[pred_key]
        self._insert_after(left, key)

    def remove(self, key):
        """Remove `key` from anywhere in the queue. KeyError if it is not there."""
        node = self._index.pop(key)
        node.prev.next = node.next
        node.next.prev = node.prev

    def dequeue(self):
        if not self._index:
            raise IndexError("dequeue from empty queue")
        key = self._head.next.key
        self.remove(key)
        return key

    def predecessor(self, key):
        """The member directly ahead of `key` (None if `key` is first)."""
        prev = self._index[key].prev
        return None if prev is self._head else prev.key


# --------------------------------------------------------------------- algorithms
def merge_sort(items, key=None, reverse=False):
    """Stable merge sort. O(n log n) time, O(n) extra space.

    Keys are computed once per item (decorate-sort-undecorate) instead of once per
    comparison. Stable means equal items keep their original order, which lets us
    sort by title first and then by year to get "year, ties broken by title".
    """
    keyed = [((key(x) if key else x), x) for x in items]
    return [x for _, x in _merge_sort(keyed, reverse)]


def _merge_sort(pairs, reverse):
    n = len(pairs)
    if n <= 1:
        return pairs
    mid = n // 2
    left, right = _merge_sort(pairs[:mid], reverse), _merge_sort(pairs[mid:], reverse)
    out, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        a, b = left[i][0], right[j][0]
        if (a >= b) if reverse else (a <= b):   # <= / >= on ties keeps it stable
            out.append(left[i])
            i += 1
        else:
            out.append(right[j])
            j += 1
    out.extend(left[i:])
    out.extend(right[j:])
    return out


def top_k(items, k, key):
    """The k items with the largest key, best first. O(n log k) time, O(k) space.

    Keeps a min-heap of size k: the smallest of the current best-k sits on top, so a
    new item only has to beat that one. Ties favour the item that came first.
    """
    if k <= 0:
        return []
    heap = MinHeap()
    for n, item in enumerate(items):
        heap.push((key(item), -n, item))   # unique -n means `item` is never compared
        if len(heap) > k:
            heap.pop()
    best = []
    while len(heap):
        best.append(heap.pop()[2])
    best.reverse()
    return best
