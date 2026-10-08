"""
Commit 2 — Price-Time Priority tests.

Verify that:
  1. Bid price priority: highest price is best_bid.
  2. Ask price priority: lowest price is best_ask.
  3. FIFO / time priority: at the same price, earlier orders come first.
  4. Level management: empty levels are cleaned up after cancellation.
  5. Mixed scenarios: interleaved inserts and cancels maintain ordering.

Run with::

    pytest tests/test_price_time_priority.py -v
"""

import pytest

# ---------------------------------------------------------------------------
# Guard: skip the whole module if the .pyd is not compiled yet
# ---------------------------------------------------------------------------
order_book = pytest.importorskip(
    "chronos.matching_engine.order_book",
    reason=(
        "Cython extension not compiled. "
        "Run: python build_ext.py"
    ),
)
LimitOrderBook = order_book.LimitOrderBook

SIDE_BUY  = order_book.SIDE_BUY_PY    # 1
SIDE_SELL = order_book.SIDE_SELL_PY    # 2
OTYPE_LIMIT = order_book.OTYPE_LIMIT_PY  # 1


# ===================================================================
# Price Priority — BUY side (highest price = best)
# ===================================================================
class TestBidPricePriority:
    """Highest bid price must become best_bid."""

    def test_single_bid(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 150.00, 10, SIDE_BUY, OTYPE_LIMIT)
        assert lob.best_bid == 150.00

    def test_higher_price_becomes_best(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 150.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 151.00, 10, SIDE_BUY, OTYPE_LIMIT)
        assert lob.best_bid == 151.00

    def test_lower_price_does_not_displace_best(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 151.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 149.00, 10, SIDE_BUY, OTYPE_LIMIT)
        assert lob.best_bid == 151.00

    def test_three_levels_sorted_descending(self):
        """Inserting bids at 100, 102, 101 should yield levels [102, 101, 100]."""
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 102.00, 20, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(3, 300, 101.00, 15, SIDE_BUY, OTYPE_LIMIT)

        levels = lob.get_price_levels(SIDE_BUY)
        assert len(levels) == 3
        assert levels[0][0] == 102.00  # best
        assert levels[1][0] == 101.00
        assert levels[2][0] == 100.00  # worst

    def test_bid_level_count(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 101.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(3, 300, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)  # same price
        assert lob.bid_level_count == 2


# ===================================================================
# Price Priority — SELL side (lowest price = best)
# ===================================================================
class TestAskPricePriority:
    """Lowest ask price must become best_ask."""

    def test_single_ask(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 150.00, 10, SIDE_SELL, OTYPE_LIMIT)
        assert lob.best_ask == 150.00

    def test_lower_price_becomes_best(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 150.00, 10, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(2, 200, 149.00, 10, SIDE_SELL, OTYPE_LIMIT)
        assert lob.best_ask == 149.00

    def test_higher_price_does_not_displace_best(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 149.00, 10, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(2, 200, 151.00, 10, SIDE_SELL, OTYPE_LIMIT)
        assert lob.best_ask == 149.00

    def test_three_levels_sorted_ascending(self):
        """Inserting asks at 103, 101, 102 should yield levels [101, 102, 103]."""
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 103.00, 10, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(2, 200, 101.00, 20, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(3, 300, 102.00, 15, SIDE_SELL, OTYPE_LIMIT)

        levels = lob.get_price_levels(SIDE_SELL)
        assert len(levels) == 3
        assert levels[0][0] == 101.00  # best
        assert levels[1][0] == 102.00
        assert levels[2][0] == 103.00  # worst

    def test_ask_level_count(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 100.00, 10, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(2, 200, 101.00, 10, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(3, 300, 100.00, 10, SIDE_SELL, OTYPE_LIMIT)
        assert lob.ask_level_count == 2


# ===================================================================
# FIFO / Time Priority within the same price
# ===================================================================
class TestTimePriority:
    """Orders at the same price must be in FIFO (arrival) order."""

    def test_bid_fifo_order(self):
        """Three bids at 100.00 — earliest order_id should be at the head."""
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(10, 1000, 100.00, 5, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(11, 2000, 100.00, 7, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(12, 3000, 100.00, 3, SIDE_BUY, OTYPE_LIMIT)

        orders = lob.get_orders_at_price(SIDE_BUY, 100.00)
        assert len(orders) == 3
        # Orders should be in insertion (FIFO) order
        assert orders[0][0] == 10  # order_id
        assert orders[1][0] == 11
        assert orders[2][0] == 12

    def test_ask_fifo_order(self):
        """Three asks at 200.00 — earliest should be at the head."""
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(20, 500, 200.00, 10, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(21, 600, 200.00, 20, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(22, 700, 200.00, 30, SIDE_SELL, OTYPE_LIMIT)

        orders = lob.get_orders_at_price(SIDE_SELL, 200.00)
        assert len(orders) == 3
        assert orders[0][0] == 20
        assert orders[1][0] == 21
        assert orders[2][0] == 22

    def test_fifo_preserved_after_earlier_cancel(self):
        """Cancel the head order; remaining orders stay in FIFO order."""
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(30, 100, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(31, 200, 100.00, 20, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(32, 300, 100.00, 30, SIDE_BUY, OTYPE_LIMIT)

        rc = lob.cancel_order(30, SIDE_BUY)
        assert rc == 0

        orders = lob.get_orders_at_price(SIDE_BUY, 100.00)
        assert len(orders) == 2
        assert orders[0][0] == 31
        assert orders[1][0] == 32

    def test_fifo_preserved_after_middle_cancel(self):
        """Cancel a middle order; head and tail remain in FIFO order."""
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(40, 100, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(41, 200, 100.00, 20, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(42, 300, 100.00, 30, SIDE_BUY, OTYPE_LIMIT)

        rc = lob.cancel_order(41, SIDE_BUY)
        assert rc == 0

        orders = lob.get_orders_at_price(SIDE_BUY, 100.00)
        assert len(orders) == 2
        assert orders[0][0] == 40
        assert orders[1][0] == 42

    def test_level_quantity_tracks_fifo_orders(self):
        """total_qty at a price level should sum all resting order quantities."""
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(50, 100, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(51, 200, 100.00, 20, SIDE_BUY, OTYPE_LIMIT)

        levels = lob.get_price_levels(SIDE_BUY)
        assert levels[0] == (100.00, 30, 2)  # (price, total_qty, order_count)


# ===================================================================
# Cancel order behaviour
# ===================================================================
class TestCancelOrder:
    """Cancellation must remove orders and clean up empty levels."""

    def test_cancel_nonexistent_returns_minus_two(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)
        rc = lob.cancel_order(999, SIDE_BUY)
        assert rc == -2

    def test_cancel_invalid_side_returns_minus_one(self):
        lob = LimitOrderBook(symbol_id=1)
        rc = lob.cancel_order(1, 99)
        assert rc == -1

    def test_cancel_only_order_empties_side(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.cancel_order(1, SIDE_BUY)
        assert lob.best_bid is None
        assert lob.bid_level_count == 0

    def test_cancel_best_promotes_next(self):
        """Cancel the best bid → next-best should become best_bid."""
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 102.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 101.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(3, 300, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)

        lob.cancel_order(1, SIDE_BUY)
        assert lob.best_bid == 101.00
        assert lob.bid_level_count == 2

    def test_cancel_worst_preserves_best(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 102.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)

        lob.cancel_order(2, SIDE_BUY)
        assert lob.best_bid == 102.00
        assert lob.bid_level_count == 1


# ===================================================================
# Spread and combined book
# ===================================================================
class TestSpread:
    """Spread calculation must reflect current best bid/ask."""

    def test_spread_updates_after_insert(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 99.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 101.00, 10, SIDE_SELL, OTYPE_LIMIT)
        assert lob.spread == pytest.approx(2.00)

    def test_spread_narrows(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 99.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 101.00, 10, SIDE_SELL, OTYPE_LIMIT)
        # Tighter bid
        lob.add_order(3, 300, 100.50, 5, SIDE_BUY, OTYPE_LIMIT)
        assert lob.spread == pytest.approx(0.50)

    def test_spread_none_when_one_side_empty(self):
        lob = LimitOrderBook(symbol_id=1)
        lob.add_order(1, 100, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)
        assert lob.spread is None


# ===================================================================
# Combined price-priority + time-priority scenario
# ===================================================================
class TestCombinedPriceTimePriority:
    """
    End-to-end test: multiple price levels with multiple orders each.
    Verifies that price priority orders the levels, and within each
    level the FIFO queue is maintained.
    """

    def test_full_bid_book_ordering(self):
        lob = LimitOrderBook(symbol_id=42)

        # Build a 3-level bid book with 2 orders each
        # Level 102.00
        lob.add_order(1, 100, 102.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 102.00, 15, SIDE_BUY, OTYPE_LIMIT)
        # Level 101.00
        lob.add_order(3, 300, 101.00, 20, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(4, 400, 101.00, 25, SIDE_BUY, OTYPE_LIMIT)
        # Level 100.00
        lob.add_order(5, 500, 100.00, 30, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(6, 600, 100.00, 35, SIDE_BUY, OTYPE_LIMIT)

        # Price priority: 102 > 101 > 100
        levels = lob.get_price_levels(SIDE_BUY)
        assert [lvl[0] for lvl in levels] == [102.00, 101.00, 100.00]

        # FIFO at 102.00
        orders_102 = lob.get_orders_at_price(SIDE_BUY, 102.00)
        assert [o[0] for o in orders_102] == [1, 2]

        # FIFO at 101.00
        orders_101 = lob.get_orders_at_price(SIDE_BUY, 101.00)
        assert [o[0] for o in orders_101] == [3, 4]

        # FIFO at 100.00
        orders_100 = lob.get_orders_at_price(SIDE_BUY, 100.00)
        assert [o[0] for o in orders_100] == [5, 6]

    def test_full_ask_book_ordering(self):
        lob = LimitOrderBook(symbol_id=42)

        # Build a 3-level ask book with 2 orders each
        # Level 98.00
        lob.add_order(10, 100, 98.00, 10, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(11, 200, 98.00, 15, SIDE_SELL, OTYPE_LIMIT)
        # Level 99.00
        lob.add_order(12, 300, 99.00, 20, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(13, 400, 99.00, 25, SIDE_SELL, OTYPE_LIMIT)
        # Level 100.00
        lob.add_order(14, 500, 100.00, 30, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(15, 600, 100.00, 35, SIDE_SELL, OTYPE_LIMIT)

        # Price priority: 98 < 99 < 100
        levels = lob.get_price_levels(SIDE_SELL)
        assert [lvl[0] for lvl in levels] == [98.00, 99.00, 100.00]

        # FIFO at 98.00
        orders_98 = lob.get_orders_at_price(SIDE_SELL, 98.00)
        assert [o[0] for o in orders_98] == [10, 11]

    def test_interleaved_inserts_maintain_ordering(self):
        """Insert orders at alternating prices — book must stay sorted."""
        lob = LimitOrderBook(symbol_id=1)
        # Interleave: 100, 102, 101, 103, 99
        lob.add_order(1, 100, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 102.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(3, 300, 101.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(4, 400, 103.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(5, 500,  99.00, 10, SIDE_BUY, OTYPE_LIMIT)

        levels = lob.get_price_levels(SIDE_BUY)
        prices = [lvl[0] for lvl in levels]
        assert prices == [103.00, 102.00, 101.00, 100.00, 99.00]


# ===================================================================
# Standalone runner
# ===================================================================
if __name__ == "__main__":
    print("=== ChronosMatch Commit 2 — Price-Time Priority smoke test ===")
    import sys

    try:
        lob = LimitOrderBook(symbol_id=1)

        # Build a small book
        lob.add_order(1, 100, 100.00, 10, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(2, 200, 101.00, 20, SIDE_BUY, OTYPE_LIMIT)
        lob.add_order(3, 300, 100.00, 15, SIDE_BUY, OTYPE_LIMIT)  # same level as 1
        lob.add_order(4, 400, 102.00, 5, SIDE_SELL, OTYPE_LIMIT)
        lob.add_order(5, 500, 103.00, 10, SIDE_SELL, OTYPE_LIMIT)

        print(f"  Book: {lob!r}")
        print(f"  best_bid={lob.best_bid}, best_ask={lob.best_ask}, spread={lob.spread}")
        print(f"  Bid levels: {lob.get_price_levels(SIDE_BUY)}")
        print(f"  Ask levels: {lob.get_price_levels(SIDE_SELL)}")
        print(f"  FIFO @ 100.00 bid: {lob.get_orders_at_price(SIDE_BUY, 100.00)}")

        # Cancel head of FIFO at 100.00
        lob.cancel_order(1, SIDE_BUY)
        print(f"  After cancel order 1 — FIFO @ 100.00: "
              f"{lob.get_orders_at_price(SIDE_BUY, 100.00)}")

        print("\nAll smoke tests PASSED ✓")
        sys.exit(0)
    except Exception as exc:
        print(f"\nFAILED: {exc}")
        sys.exit(1)
