# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: nonecheck=False
"""
ChronosMatch Limit Order Book — Cython Extension (Week 2, Step 1).

Defines C-level types for all order-book primitives and basic bid/ask
book structures.  The matching algorithm is intentionally NOT implemented
here; this module only sets up the scaffolding that Week 2 will build on.

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
# Python-visible wrapper class
# ---------------------------------------------------------------------------
cdef class LimitOrderBook:
    """
    Cython Limit Order Book scaffold for a single trading symbol.

    Week 2 Step 1 — structural skeleton only.
    Provides:
      - Typed bid/ask HalfBook structs (C-level)
      - Symbol ID tracking
      - Convenience Python properties (best_bid, best_ask, spread)
      - add_order() / cancel_order() stubs that accept typed parameters
        but do NOT yet implement price-time-priority matching

    Usage::

        from chronos.matching_engine.order_book import LimitOrderBook
        lob = LimitOrderBook(symbol_id=1001)
        print(lob.symbol_id)   # 1001
        print(lob.best_bid)    # None (empty book)
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
        # Week 2 Step 2 will walk price levels and free OrderEntry nodes.
        # For now, no heap allocations exist so nothing to free.
        pass

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

    # ---- Stubs (matching algorithm NOT yet implemented) --------------------
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
        [STUB] Accept a new order into the book.

        Parameters match the Week 1 binary protocol layout exactly so that
        values unpacked via unpack_order_raw() can be forwarded here without
        any conversion.

        Returns:
            0  — order accepted (not yet matched or queued, scaffold only)
            -1 — invalid side
        """
        if side == SIDE_BUY:
            self._bids.total_orders += 1
        elif side == SIDE_SELL:
            self._asks.total_orders += 1
        else:
            return -1
        # TODO (Week 2 Step 2): allocate OrderEntry, insert into correct
        #   PriceLevel, run price-time-priority matching.
        return 0

    cpdef int cancel_order(self, order_id_t order_id, side_t side):
        """
        [STUB] Cancel an existing resting order by ID.

        Returns:
            0  — cancellation accepted (scaffold only)
            -1 — invalid side
        """
        if side not in (SIDE_BUY, SIDE_SELL):
            return -1
        # TODO (Week 2 Step 2): look up order in O(1) hash map, remove from
        #   PriceLevel, free OrderEntry, clean up empty price levels.
        return 0

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
