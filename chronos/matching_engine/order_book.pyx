# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: nonecheck=False
"""
ChronosMatch Limit Order Book — Cython Extension (Commit 2).

Implements Price-Time Priority:
  - BUY (bid) side: highest price gets priority
  - SELL (ask) side: lowest price gets priority
  - Within the same price level, earlier orders (FIFO) get priority

Binary layout matches the Week 1 protocol (protocol.py):
    order_id     : uint64
    timestamp_ns : uint64
    price        : double  (IEEE-754, 8-byte)
    quantity     : uint32
    symbol_id    : uint16
    side         : uint8   (1 = BUY, 2 = SELL)
    order_type   : uint8   (1 = LIMIT, 2 = MARKET, 3 = CANCEL)
"""

from libc.stdint cimport uint8_t, uint16_t, uint32_t, uint64_t
from libc.stdlib cimport malloc, free
from libc.string cimport memset

# ---------------------------------------------------------------------------
# C-level type aliases (documented, not typedef'd, for Cython compatibility)
# ---------------------------------------------------------------------------
#   price_t      → double   (IEEE-754 double, 8 bytes)
#   qty_t        → uint32_t (unsigned 32-bit quantity)
#   order_id_t   → uint64_t (monotonic order identifier)
#   side_t       → uint8_t  (1=BUY / 2=SELL)
#   timestamp_t  → uint64_t (nanoseconds since Unix epoch)

ctypedef double      price_t
ctypedef uint32_t    qty_t
ctypedef uint64_t    order_id_t
ctypedef uint8_t     side_t
ctypedef uint64_t    timestamp_t
ctypedef uint16_t    symbol_id_t

# ---------------------------------------------------------------------------
# Side / OrderType constants (mirror protocol.py IntEnum values)
# ---------------------------------------------------------------------------
cdef uint8_t SIDE_BUY    = 1
cdef uint8_t SIDE_SELL   = 2

cdef uint8_t OTYPE_LIMIT  = 1
cdef uint8_t OTYPE_MARKET = 2
cdef uint8_t OTYPE_CANCEL = 3

# Make constants visible from Python
SIDE_BUY_PY    = SIDE_BUY
SIDE_SELL_PY   = SIDE_SELL
OTYPE_LIMIT_PY = OTYPE_LIMIT

# ---------------------------------------------------------------------------
# C struct: single order entry stored in a price-level linked list
# ---------------------------------------------------------------------------
cdef struct OrderEntry:
    order_id_t  order_id
    timestamp_t timestamp_ns
    price_t     price
    qty_t       quantity
    symbol_id_t symbol_id
    side_t      side
    uint8_t     order_type
    # Intrusive singly-linked list pointer (NULL = last entry in level)
    OrderEntry* next_entry

# ---------------------------------------------------------------------------
# C struct: a single price level (all orders at the same price)
# ---------------------------------------------------------------------------
cdef struct PriceLevel:
    price_t      price
    qty_t        total_qty        # sum of all order quantities at this level
    uint32_t     order_count      # number of live orders
    OrderEntry*  head             # first order (FIFO)
    OrderEntry*  tail             # last order  (FIFO)
    # Doubly-linked list for O(1) price-level navigation
    PriceLevel*  next_level       # next worse price (bids: lower, asks: higher)
    PriceLevel*  prev_level       # next better price

# ---------------------------------------------------------------------------
# C struct: one half of the book (all bids OR all asks)
# ---------------------------------------------------------------------------
cdef struct HalfBook:
    side_t       side             # SIDE_BUY or SIDE_SELL
    PriceLevel*  best             # best price level (highest bid / lowest ask)
    uint32_t     level_count      # number of distinct price levels
    uint64_t     total_orders     # cumulative orders ever added (including cancelled)


# ---------------------------------------------------------------------------
# C-level helpers: price level allocation / deallocation
# ---------------------------------------------------------------------------
cdef PriceLevel* _alloc_price_level(price_t price) noexcept:
    """Allocate and zero-initialise a new PriceLevel on the heap."""
    cdef PriceLevel* lvl = <PriceLevel*>malloc(sizeof(PriceLevel))
    if lvl == NULL:
        return NULL  # OOM — caller must handle
    memset(lvl, 0, sizeof(PriceLevel))
    lvl.price = price
    return lvl


cdef OrderEntry* _alloc_order_entry(
    order_id_t  order_id,
    timestamp_t timestamp_ns,
    price_t     price,
    qty_t       quantity,
    symbol_id_t symbol_id,
    side_t      side,
    uint8_t     order_type,
) noexcept:
    """Allocate and populate a new OrderEntry on the heap."""
    cdef OrderEntry* entry = <OrderEntry*>malloc(sizeof(OrderEntry))
    if entry == NULL:
        return NULL  # OOM
    entry.order_id     = order_id
    entry.timestamp_ns = timestamp_ns
    entry.price        = price
    entry.quantity     = quantity
    entry.symbol_id    = symbol_id
    entry.side         = side
    entry.order_type   = order_type
    entry.next_entry   = NULL
    return entry


cdef void _free_all_levels(PriceLevel* best) noexcept:
    """Walk a half-book from best → worst, freeing every level and its orders."""
    cdef PriceLevel* lvl = best
    cdef PriceLevel* next_lvl
    cdef OrderEntry* entry
    cdef OrderEntry* next_entry

    while lvl != NULL:
        # Free all order entries in this level
        entry = lvl.head
        while entry != NULL:
            next_entry = entry.next_entry
            free(entry)
            entry = next_entry
        next_lvl = lvl.next_level
        free(lvl)
        lvl = next_lvl


# ---------------------------------------------------------------------------
# C-level helper: insert a PriceLevel into the correct position in a HalfBook
# ---------------------------------------------------------------------------
cdef void _insert_level_into_halfbook(HalfBook* book, PriceLevel* new_level) noexcept:
    """
    Insert *new_level* into the doubly-linked level list of *book* so that
    price-priority ordering is maintained:
      - Bids: descending price (best = highest)
      - Asks: ascending price  (best = lowest)
    """
    cdef PriceLevel* cur

    # Empty book — new level is the best (and only) level
    if book.best == NULL:
        book.best = new_level
        new_level.prev_level = NULL
        new_level.next_level = NULL
        book.level_count += 1
        return

    # Check if new level is the new best
    if book.side == SIDE_BUY:
        # Bids: higher price is better
        if new_level.price > book.best.price:
            new_level.next_level = book.best
            new_level.prev_level = NULL
            book.best.prev_level = new_level
            book.best = new_level
            book.level_count += 1
            return
    else:
        # Asks: lower price is better
        if new_level.price < book.best.price:
            new_level.next_level = book.best
            new_level.prev_level = NULL
            book.best.prev_level = new_level
            book.best = new_level
            book.level_count += 1
            return

    # Walk from best towards worst to find insertion point
    cur = book.best
    if book.side == SIDE_BUY:
        # Bids descending: walk until cur.next_level is NULL or has a lower price
        while cur.next_level != NULL and cur.next_level.price > new_level.price:
            cur = cur.next_level
        # Insert new_level after cur
    else:
        # Asks ascending: walk until cur.next_level is NULL or has a higher price
        while cur.next_level != NULL and cur.next_level.price < new_level.price:
            cur = cur.next_level
        # Insert new_level after cur

    new_level.next_level = cur.next_level
    new_level.prev_level = cur
    if cur.next_level != NULL:
        cur.next_level.prev_level = new_level
    cur.next_level = new_level
    book.level_count += 1


# ---------------------------------------------------------------------------
# C-level helper: find or create a PriceLevel for a given price
# ---------------------------------------------------------------------------
cdef PriceLevel* _find_or_create_level(HalfBook* book, price_t price) noexcept:
    """
    Locate the PriceLevel with the given price in *book*.
    If none exists, allocate one and insert it in sorted position.
    Returns NULL on allocation failure.
    """
    cdef PriceLevel* cur = book.best
    while cur != NULL:
        if cur.price == price:
            return cur
        cur = cur.next_level

    # Not found — allocate and insert
    cdef PriceLevel* new_level = _alloc_price_level(price)
    if new_level == NULL:
        return NULL
    _insert_level_into_halfbook(book, new_level)
    return new_level


# ---------------------------------------------------------------------------
# C-level helper: append an OrderEntry to the FIFO tail of a PriceLevel
# ---------------------------------------------------------------------------
cdef void _append_order_to_level(PriceLevel* lvl, OrderEntry* entry) noexcept:
    """Append *entry* at the tail of *lvl* (FIFO / time priority)."""
    if lvl.head == NULL:
        lvl.head = entry
        lvl.tail = entry
    else:
        lvl.tail.next_entry = entry
        lvl.tail = entry
    entry.next_entry = NULL
    lvl.order_count += 1
    lvl.total_qty += entry.quantity


# ---------------------------------------------------------------------------
# C-level helper: remove (unlink) an empty PriceLevel from a HalfBook
# ---------------------------------------------------------------------------
cdef void _remove_level(HalfBook* book, PriceLevel* lvl) noexcept:
    """Unlink *lvl* from *book*'s doubly-linked list and free it."""
    if lvl.prev_level != NULL:
        lvl.prev_level.next_level = lvl.next_level
    else:
        # lvl was the best — promote next
        book.best = lvl.next_level

    if lvl.next_level != NULL:
        lvl.next_level.prev_level = lvl.prev_level

    book.level_count -= 1
    free(lvl)


# ---------------------------------------------------------------------------
# Python-visible wrapper class
# ---------------------------------------------------------------------------
cdef class LimitOrderBook:
    """
    Cython Limit Order Book with Price-Time Priority for a single trading symbol.

    Price priority:
      - Highest BUY price gets priority.
      - Lowest SELL price gets priority.

    Time priority (FIFO):
      - Among orders at the same price, the earlier order gets priority.

    Usage::

        from chronos.matching_engine.order_book import LimitOrderBook
        lob = LimitOrderBook(symbol_id=1001)
        lob.add_order(order_id=1, timestamp_ns=100, price=150.25,
                       quantity=100, side=1, order_type=1)
        print(lob.best_bid)   # 150.25
    """

    # ---- C-level attributes ------------------------------------------------
    cdef HalfBook  _bids           # buy-side half book
    cdef HalfBook  _asks           # sell-side half book
    cdef symbol_id_t _symbol_id

    # ---- Python __init__ ---------------------------------------------------
    def __cinit__(self, symbol_id: int = 0):
        self._symbol_id = <symbol_id_t>symbol_id
        # Zero-initialise both half books
        memset(&self._bids, 0, sizeof(HalfBook))
        memset(&self._asks, 0, sizeof(HalfBook))
        self._bids.side = SIDE_BUY
        self._asks.side = SIDE_SELL

    def __dealloc__(self):
        """Free all heap-allocated PriceLevels and OrderEntries."""
        _free_all_levels(self._bids.best)
        _free_all_levels(self._asks.best)

    # ---- Properties --------------------------------------------------------
    @property
    def symbol_id(self) -> int:
        """The 16-bit symbol identifier this book tracks."""
        return int(self._symbol_id)

    @property
    def best_bid(self):
        """Best (highest) bid price, or None if no bids exist."""
        if self._bids.best == NULL:
            return None
        return float(self._bids.best.price)

    @property
    def best_ask(self):
        """Best (lowest) ask price, or None if no asks exist."""
        if self._asks.best == NULL:
            return None
        return float(self._asks.best.price)

    @property
    def spread(self):
        """Bid-ask spread, or None if either side is empty."""
        if self._bids.best == NULL or self._asks.best == NULL:
            return None
        return float(self._asks.best.price - self._bids.best.price)

    @property
    def bid_level_count(self) -> int:
        """Number of distinct bid price levels currently in the book."""
        return int(self._bids.level_count)

    @property
    def ask_level_count(self) -> int:
        """Number of distinct ask price levels currently in the book."""
        return int(self._asks.level_count)

    @property
    def total_bid_orders(self) -> int:
        """Cumulative number of bid orders ever submitted (including cancelled)."""
        return int(self._bids.total_orders)

    @property
    def total_ask_orders(self) -> int:
        """Cumulative number of ask orders ever submitted (including cancelled)."""
        return int(self._asks.total_orders)

    # ---- Core: add_order with price-time priority --------------------------
    cpdef int add_order(
        self,
        order_id_t  order_id,
        timestamp_t timestamp_ns,
        price_t     price,
        qty_t       quantity,
        side_t      side,
        uint8_t     order_type,
    ):
        """
        Insert a new order into the book with price-time priority.

        The order is placed into the appropriate PriceLevel. If no level
        exists at this price, one is created and inserted in sorted order.
        Within a price level, orders are appended at the tail (FIFO).

        Parameters match the Week 1 binary protocol layout exactly so that
        values unpacked via unpack_order_raw() can be forwarded here without
        any conversion.

        Returns:
            0  — order accepted and inserted
            -1 — invalid side
            -2 — memory allocation failure
        """
        cdef HalfBook* book
        cdef PriceLevel* lvl
        cdef OrderEntry* entry

        if side == SIDE_BUY:
            book = &self._bids
        elif side == SIDE_SELL:
            book = &self._asks
        else:
            return -1

        book.total_orders += 1

        # Allocate the order entry
        entry = _alloc_order_entry(
            order_id, timestamp_ns, price, quantity,
            self._symbol_id, side, order_type,
        )
        if entry == NULL:
            return -2

        # Find or create the price level
        lvl = _find_or_create_level(book, price)
        if lvl == NULL:
            free(entry)
            return -2

        # Append to FIFO tail (time priority)
        _append_order_to_level(lvl, entry)

        return 0

    # ---- Core: cancel_order ------------------------------------------------
    cpdef int cancel_order(self, order_id_t order_id, side_t side):
        """
        Cancel an existing resting order by ID.

        Walks the book to find the order, removes it from its PriceLevel,
        and cleans up empty levels. This is O(n) in the number of resting
        orders on the given side; a hash-map lookup will be added in a
        future commit for O(1) cancellation.

        Returns:
            0  — order found and cancelled
            -1 — invalid side
            -2 — order not found
        """
        cdef HalfBook* book
        cdef PriceLevel* lvl
        cdef PriceLevel* next_lvl
        cdef OrderEntry* entry
        cdef OrderEntry* prev_entry

        if side == SIDE_BUY:
            book = &self._bids
        elif side == SIDE_SELL:
            book = &self._asks
        else:
            return -1

        # Walk all price levels and their order chains
        lvl = book.best
        while lvl != NULL:
            next_lvl = lvl.next_level  # save in case we remove lvl
            prev_entry = NULL
            entry = lvl.head
            while entry != NULL:
                if entry.order_id == order_id:
                    # Unlink entry from the singly-linked order chain
                    if prev_entry == NULL:
                        lvl.head = entry.next_entry
                    else:
                        prev_entry.next_entry = entry.next_entry

                    # Update tail if we removed the last entry
                    if entry.next_entry == NULL:
                        lvl.tail = prev_entry

                    lvl.order_count -= 1
                    lvl.total_qty -= entry.quantity
                    free(entry)

                    # If level is now empty, remove it from the book
                    if lvl.order_count == 0:
                        _remove_level(book, lvl)

                    return 0

                prev_entry = entry
                entry = entry.next_entry

            lvl = next_lvl

        return -2  # not found

    # ---- Observability: get orders at a given price level ------------------
    def get_orders_at_price(self, side: int, price: float) -> list:
        """
        Return a list of (order_id, timestamp_ns, quantity) tuples for all
        resting orders at the given price level, in FIFO order.

        This is a Python-level helper intended for testing and debugging.
        """
        cdef HalfBook* book
        cdef PriceLevel* lvl
        cdef OrderEntry* entry

        if side == SIDE_BUY:
            book = &self._bids
        elif side == SIDE_SELL:
            book = &self._asks
        else:
            return []

        lvl = book.best
        while lvl != NULL:
            if lvl.price == <price_t>price:
                result = []
                entry = lvl.head
                while entry != NULL:
                    result.append((
                        int(entry.order_id),
                        int(entry.timestamp_ns),
                        int(entry.quantity),
                    ))
                    entry = entry.next_entry
                return result
            lvl = lvl.next_level

        return []

    # ---- Observability: list all price levels in priority order ------------
    def get_price_levels(self, side: int) -> list:
        """
        Return a list of (price, total_qty, order_count) tuples for all
        price levels on the given side, in priority order
        (best → worst).

        This is a Python-level helper intended for testing and debugging.
        """
        cdef HalfBook* book
        cdef PriceLevel* lvl

        if side == SIDE_BUY:
            book = &self._bids
        elif side == SIDE_SELL:
            book = &self._asks
        else:
            return []

        result = []
        lvl = book.best
        while lvl != NULL:
            result.append((
                float(lvl.price),
                int(lvl.total_qty),
                int(lvl.order_count),
            ))
            lvl = lvl.next_level
        return result

    # ---- Repr / Str --------------------------------------------------------
    def __repr__(self) -> str:
        bid = self.best_bid
        ask = self.best_ask
        return (
            f"LimitOrderBook("
            f"symbol_id={self._symbol_id}, "
            f"best_bid={bid}, "
            f"best_ask={ask}, "
            f"bid_levels={self._bids.level_count}, "
            f"ask_levels={self._asks.level_count}"
            f")"
        )
