"""
Week 2 Step 1 — verify that the Cython order_book extension compiles and
imports correctly, and that the basic LimitOrderBook scaffold behaves as
specified.

Run with::

    pytest tests/test_order_book.py -v

or stand-alone::

    python tests/test_order_book.py
"""

import pytest


# ---------------------------------------------------------------------------
# Guard: skip the whole module gracefully if the .pyd is not compiled yet
# ---------------------------------------------------------------------------
order_book = pytest.importorskip(
    "chronos.matching_engine.order_book",
    reason=(
        "Cython extension not compiled. "
        "Run: python setup.py build_ext --inplace"
    ),
)
LimitOrderBook = order_book.LimitOrderBook


# ---------------------------------------------------------------------------
# Import / sanity
# ---------------------------------------------------------------------------
class TestImport:
    def test_module_importable(self):
        """The compiled .pyd must be importable without errors."""
        import chronos.matching_engine.order_book as m
        assert m is not None

    def test_class_present(self):
        assert LimitOrderBook is not None

    def test_constants_present(self):
        """Side / order-type constants must be exported from the module."""
        assert order_book.SIDE_BUY_PY == 1
        assert order_book.SIDE_SELL_PY == 2
        assert order_book.OTYPE_LIMIT_PY == 1

    def test_cython_available_flag(self):
        from chronos.matching_engine import _CYTHON_AVAILABLE
        assert _CYTHON_AVAILABLE is True


# ---------------------------------------------------------------------------
# LimitOrderBook construction
# ---------------------------------------------------------------------------
class TestLOBConstruction:
    def test_default_symbol_id(self):
        lob = LimitOrderBook()
        assert lob.symbol_id == 0

    def test_custom_symbol_id(self):
        lob = LimitOrderBook(symbol_id=1001)
        assert lob.symbol_id == 1001

    def test_empty_book_best_bid_none(self):
        lob = LimitOrderBook(symbol_id=1002)
        assert lob.best_bid is None

    def test_empty_book_best_ask_none(self):
        lob = LimitOrderBook(symbol_id=1002)
        assert lob.best_ask is None

    def test_empty_book_spread_none(self):
        lob = LimitOrderBook(symbol_id=1002)
        assert lob.spread is None

    def test_empty_book_level_counts(self):
        lob = LimitOrderBook(symbol_id=1003)
        assert lob.bid_level_count == 0
        assert lob.ask_level_count == 0

    def test_empty_book_order_counts(self):
        lob = LimitOrderBook(symbol_id=1003)
        assert lob.total_bid_orders == 0
        assert lob.total_ask_orders == 0


# ---------------------------------------------------------------------------
# add_order stub — validates argument passing and return codes
# ---------------------------------------------------------------------------
class TestAddOrderStub:
    """
    The matching algorithm is not yet implemented, but add_order() must:
      - Accept typed parameters that match the Week 1 protocol layout
      - Return 0 for valid sides
      - Return -1 for invalid sides
      - Increment the total_xxx_orders counter
    """

    def test_add_bid_returns_zero(self):
        lob = LimitOrderBook(symbol_id=1001)
        rc = lob.add_order(
            order_id=1,
            timestamp_ns=1_000_000_000,
            price=150.25,
            quantity=100,
            side=1,        # SIDE_BUY
            order_type=1,  # OTYPE_LIMIT
        )
        assert rc == 0

    def test_add_ask_returns_zero(self):
        lob = LimitOrderBook(symbol_id=1001)
        rc = lob.add_order(
            order_id=2,
            timestamp_ns=1_000_000_001,
            price=150.50,
            quantity=200,
            side=2,        # SIDE_SELL
            order_type=1,
        )
        assert rc == 0

    def test_invalid_side_returns_minus_one(self):
        lob = LimitOrderBook(symbol_id=1001)
        rc = lob.add_order(
            order_id=3,
            timestamp_ns=0,
            price=100.0,
            quantity=10,
            side=99,       # invalid
            order_type=1,
        )
        assert rc == -1

    def test_bid_order_counter_increments(self):
        lob = LimitOrderBook(symbol_id=1001)
        lob.add_order(1, 0, 100.0, 10, 1, 1)
        lob.add_order(2, 1, 100.0, 20, 1, 1)
        assert lob.total_bid_orders == 2

    def test_ask_order_counter_increments(self):
        lob = LimitOrderBook(symbol_id=1001)
        lob.add_order(1, 0, 101.0, 5, 2, 1)
        assert lob.total_ask_orders == 1

    def test_mixed_orders_counters_independent(self):
        lob = LimitOrderBook(symbol_id=1001)
        for i in range(3):
            lob.add_order(i, i, 100.0 + i, 10, 1, 1)   # bids
        for i in range(5):
            lob.add_order(100 + i, i, 101.0 + i, 5, 2, 1)  # asks
        assert lob.total_bid_orders == 3
        assert lob.total_ask_orders == 5


# ---------------------------------------------------------------------------
# cancel_order stub
# ---------------------------------------------------------------------------
class TestCancelOrderStub:
    def test_cancel_bid_returns_zero(self):
        lob = LimitOrderBook(symbol_id=1001)
        rc = lob.cancel_order(order_id=42, side=1)
        assert rc == 0

    def test_cancel_ask_returns_zero(self):
        lob = LimitOrderBook(symbol_id=1001)
        rc = lob.cancel_order(order_id=43, side=2)
        assert rc == 0

    def test_cancel_invalid_side_returns_minus_one(self):
        lob = LimitOrderBook(symbol_id=1001)
        rc = lob.cancel_order(order_id=44, side=99)
        assert rc == -1


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------
class TestRepr:
    def test_repr_contains_symbol_id(self):
        lob = LimitOrderBook(symbol_id=1007)
        assert "1007" in repr(lob)

    def test_repr_contains_none_for_empty_book(self):
        lob = LimitOrderBook(symbol_id=1007)
        assert "None" in repr(lob)


# ---------------------------------------------------------------------------
# Allow running as a standalone script for quick sanity check
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== ChronosMatch Week 2 — Cython LOB smoke test ===")
    import sys

    try:
        lob = LimitOrderBook(symbol_id=1001)
        print(f"  Created: {lob!r}")
        rc = lob.add_order(1, 1_000_000_000, 150.25, 100, 1, 1)
        print(f"  add_order (BUY)  → rc={rc}, total_bid_orders={lob.total_bid_orders}")
        rc = lob.add_order(2, 1_000_000_001, 150.50, 200, 2, 1)
        print(f"  add_order (SELL) → rc={rc}, total_ask_orders={lob.total_ask_orders}")
        rc = lob.cancel_order(1, 1)
        print(f"  cancel_order     → rc={rc}")
        print("  constants: SIDE_BUY_PY =", order_book.SIDE_BUY_PY,
              "  SIDE_SELL_PY =", order_book.SIDE_SELL_PY)
        print("\nAll smoke tests PASSED ✓")
        sys.exit(0)
    except Exception as exc:
        print(f"\nFAILED: {exc}")
        sys.exit(1)
