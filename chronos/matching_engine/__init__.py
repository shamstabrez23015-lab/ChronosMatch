"""
ChronosMatch Matching Engine (Week 2).

This sub-package contains the Cython-accelerated Limit Order Book and,
eventually, the full price-time-priority matching algorithm.

On first import the compiled extension (.pyd on Windows) is expected to be
present.  If you haven't built it yet, run::

    python setup.py build_ext --inplace

from the project root.
"""

# Attempt a graceful import so that the rest of the project still loads even
# if the Cython extension has not been compiled yet.
try:
    from chronos.matching_engine.order_book import LimitOrderBook  # noqa: F401
    _CYTHON_AVAILABLE = True
except ImportError:
    _CYTHON_AVAILABLE = False
    LimitOrderBook = None  # type: ignore[assignment,misc]

__all__ = ["LimitOrderBook", "_CYTHON_AVAILABLE"]
