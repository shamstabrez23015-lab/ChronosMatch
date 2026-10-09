"""ChronosMatch: Terminal Dashboard (Week 2 Basic Curses Structure).

Provides a modular curses-based terminal UI displaying:
- ChronosMatch Header / Title
- Best Bid (Price & Quantity)
- Best Ask (Price & Quantity)
- Bid/Ask Spread (Absolute & Basis Points)
- Orders Processed
- Throughput (Orders per second)
- Latency (Avg, P99, Min, Max in microseconds)

Currently uses placeholder or mock sample values pending live Cython matching-engine
integration.
"""

from dataclasses import dataclass
import datetime
import os
import sys
import time
from typing import Callable, Optional

# Attempt importing curses safely
try:
    import curses
except ImportError:
    curses = None  # type: ignore


@dataclass
class DashboardData:
    """Holds real-time market depth and engine performance metrics.

    Fields default to None (rendered as '--') until populated by the matching
    engine or test harness.
    """

    symbol: str = "BTC-USDT"
    best_bid_price: Optional[float] = None
    best_bid_qty: Optional[float] = None
    best_ask_price: Optional[float] = None
    best_ask_qty: Optional[float] = None
    spread: Optional[float] = None
    spread_bps: Optional[float] = None
    orders_processed: Optional[int] = None
    matched_orders: Optional[int] = None
    canceled_orders: Optional[int] = None
    throughput_ops: Optional[float] = None
    peak_throughput_ops: Optional[float] = None
    latency_avg_us: Optional[float] = None
    latency_p99_us: Optional[float] = None
    latency_min_us: Optional[float] = None
    latency_max_us: Optional[float] = None
    engine_status: str = "STANDBY (PLACEHOLDER)"

    @classmethod
    def create_placeholder(cls, symbol: str = "BTC-USDT") -> "DashboardData":
        """Return an instance with placeholder values ('--')."""
        return cls(
            symbol=symbol,
            best_bid_price=None,
            best_bid_qty=None,
            best_ask_price=None,
            best_ask_qty=None,
            spread=None,
            spread_bps=None,
            orders_processed=None,
            matched_orders=None,
            canceled_orders=None,
            throughput_ops=None,
            peak_throughput_ops=None,
            latency_avg_us=None,
            latency_p99_us=None,
            latency_min_us=None,
            latency_max_us=None,
            engine_status="STANDBY (AWAITING MATCHING ENGINE)",
        )

    @classmethod
    def create_sample(cls, symbol: str = "BTC-USDT") -> "DashboardData":
        """Return an instance with realistic mock/sample values for visual testing."""
        return cls(
            symbol=symbol,
            best_bid_price=64250.50,
            best_bid_qty=12.4500,
            best_ask_price=64251.00,
            best_ask_qty=8.3000,
            spread=0.50,
            spread_bps=0.78,
            orders_processed=125_480,
            matched_orders=94_120,
            canceled_orders=12_300,
            throughput_ops=98_450.0,
            peak_throughput_ops=104_200.0,
            latency_avg_us=18.4,
            latency_p99_us=35.2,
            latency_min_us=12.1,
            latency_max_us=78.6,
            engine_status="RUNNING (MOCK SAMPLE DATA)",
        )


def _prepare_windows_console() -> None:
    """Ensure Windows console handles point to CONOUT$/CONIN$ if redirected."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        std_input_handle = -10
        std_output_handle = -11

        out_handle = kernel32.GetStdHandle(std_output_handle)
        # FILE_TYPE_CHAR is 0x0002
        if kernel32.GetFileType(out_handle) != 2:
            conout = kernel32.CreateFileW(
                "CONOUT$",
                0x40000000 | 0x80000000,  # GENERIC_READ | GENERIC_WRITE
                0x00000001 | 0x00000002,  # FILE_SHARE_READ | FILE_SHARE_WRITE
                None,
                3,  # OPEN_EXISTING
                0,
                None,
            )
            if conout and conout != -1:
                kernel32.SetStdHandle(std_output_handle, conout)

        in_handle = kernel32.GetStdHandle(std_input_handle)
        if kernel32.GetFileType(in_handle) != 2:
            conin = kernel32.CreateFileW(
                "CONIN$",
                0x40000000 | 0x80000000,
                0x00000001 | 0x00000002,
                None,
                3,
                0,
                None,
            )
            if conin and conin != -1:
                kernel32.SetStdHandle(std_input_handle, conin)
    except Exception:
        pass


class ChronosDashboard:
    """Curses terminal dashboard for ChronosMatch.

    Displays Depth of Market (Best Bid, Best Ask, Spread) alongside engine
    performance metrics (Orders Processed, Throughput, Latency).
    """

    MIN_HEIGHT = 18
    MIN_WIDTH = 76

    def __init__(
        self,
        data: Optional[DashboardData] = None,
        data_provider: Optional[Callable[[], DashboardData]] = None,
        use_sample_data: bool = False,
        refresh_interval: float = 0.1,
    ):
        """Initialize the dashboard.

        Args:
            data: Initial DashboardData snapshot. Defaults to placeholder data.
            data_provider: Optional callable returning a fresh DashboardData on each tick.
            use_sample_data: If True, initialize with mock sample data instead of '--'.
            refresh_interval: Seconds between screen refreshes (default: 0.1s / 10 FPS).
        """
        self.data_provider = data_provider
        self.use_sample_data = use_sample_data
        self.refresh_interval = max(0.01, refresh_interval)

        if data is not None:
            self.data = data
        elif self.use_sample_data:
            self.data = DashboardData.create_sample()
        else:
            self.data = DashboardData.create_placeholder()

        self._color_initialized = False

    def update_data(self, data: DashboardData) -> None:
        """Update metrics data displayed on dashboard."""
        self.data = data

    def _init_colors(self) -> None:
        """Initialize color pairs if supported by terminal."""
        if not curses or not curses.has_colors():
            self._color_initialized = False
            return

        try:
            curses.start_color()
            if hasattr(curses, "use_default_colors"):
                curses.use_default_colors()
                bg = -1
            else:
                bg = curses.COLOR_BLACK

            # Pair 1: Green (Bids)
            curses.init_pair(1, curses.COLOR_GREEN, bg)
            # Pair 2: Red (Asks)
            curses.init_pair(2, curses.COLOR_RED, bg)
            # Pair 3: Yellow (Spread / Warning)
            curses.init_pair(3, curses.COLOR_YELLOW, bg)
            # Pair 4: Cyan (Header / Title / Accents)
            curses.init_pair(4, curses.COLOR_CYAN, bg)
            # Pair 5: Magenta (Latency / Throughput)
            curses.init_pair(5, curses.COLOR_MAGENTA, bg)
            # Pair 6: White / Dim (Borders / Subdued)
            curses.init_pair(6, curses.COLOR_WHITE, bg)
            self._color_initialized = True
        except Exception:
            self._color_initialized = False

    def _attr(self, pair: int, bold: bool = False) -> int:
        """Get attribute with color pair and optional bold flag."""
        attr = 0
        if self._color_initialized and curses:
            try:
                attr |= curses.color_pair(pair)
            except Exception:
                pass
        if bold and curses:
            attr |= curses.A_BOLD
        return attr

    def _safe_addstr(self, stdscr, y: int, x: int, text: str, attr: int = 0) -> None:
        """Add string to screen safely, clipping to window bounds to avoid curses errors."""
        max_y, max_x = stdscr.getmaxyx()
        if y < 0 or y >= max_y or x < 0 or x >= max_x:
            return

        # Clip string to remaining line width
        available = max_x - x
        if available <= 0:
            return

        clipped = text[:available]
        try:
            # Avoid writing to bottom-right corner character which throws curses.error
            if y == max_y - 1 and len(clipped) == available:
                clipped = clipped[:-1]
            if clipped:
                stdscr.addstr(y, x, clipped, attr)
        except Exception:
            pass

    def _draw_box(self, stdscr, y: int, x: int, h: int, w: int, title: str = "") -> None:
        """Draw an ASCII/Unicode box frame with an optional title."""
        border_attr = self._attr(6)
        title_attr = self._attr(4, bold=True)

        # Top border
        top_line = "┌" + "─" * (w - 2) + "┐"
        self._safe_addstr(stdscr, y, x, top_line, border_attr)

        # Optional title embedded in top border
        if title:
            header_str = f"┤ {title} ├"
            self._safe_addstr(stdscr, y, x + 2, header_str, title_attr)

        # Side borders
        for row in range(1, h - 1):
            self._safe_addstr(stdscr, y + row, x, "│", border_attr)
            self._safe_addstr(stdscr, y + row, x + w - 1, "│", border_attr)

        # Bottom border
        bot_line = "└" + "─" * (w - 2) + "┘"
        self._safe_addstr(stdscr, y + h - 1, x, bot_line, border_attr)

    def _render_header(self, stdscr, y: int, x: int, width: int) -> int:
        """Render ChronosMatch Title / Header block."""
        height = 4
        self._draw_box(stdscr, y, x, height, width, title="CHRONOSMATCH :: WEEK 2 PROTOTYPE")

        title = "CHRONOSMATCH HIGH-FREQUENCY MATCHING ENGINE"
        self._safe_addstr(stdscr, y + 1, x + 2, title, self._attr(4, bold=True))

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta_str = f"Symbol: {self.data.symbol}  |  Status: {self.data.engine_status}  |  {now_str}"
        self._safe_addstr(stdscr, y + 2, x + 2, meta_str, self._attr(6))

        return y + height

    def _render_market_depth(self, stdscr, y: int, x: int, width: int) -> int:
        """Render Best Bid, Best Ask, and Bid/Ask Spread sections."""
        height = 6
        self._draw_box(stdscr, y, x, height, width, title="LEVEL 1 MARKET DEPTH (TOP OF BOOK)")

        col_w = (width - 4) // 3
        col1_x = x + 2
        col2_x = col1_x + col_w
        col3_x = col2_x + col_w

        # --- Section 1: Best Bid ---
        self._safe_addstr(stdscr, y + 1, col1_x, "[ BEST BID ]", self._attr(1, bold=True))
        bid_px_str = f"${self.data.best_bid_price:,.2f}" if self.data.best_bid_price is not None else "--"
        bid_qty_str = f"{self.data.best_bid_qty:,.4f}" if self.data.best_bid_qty is not None else "--"
        self._safe_addstr(stdscr, y + 2, col1_x, f"Price : {bid_px_str}", self._attr(1, bold=True))
        self._safe_addstr(stdscr, y + 3, col1_x, f"Size  : {bid_qty_str}", self._attr(6))

        # --- Section 2: Bid/Ask Spread ---
        self._safe_addstr(stdscr, y + 1, col2_x, "[ BID/ASK SPREAD ]", self._attr(3, bold=True))
        spread_str = f"${self.data.spread:,.2f}" if self.data.spread is not None else "--"
        bps_str = f"{self.data.spread_bps:.2f} bps" if self.data.spread_bps is not None else "-- bps"
        self._safe_addstr(stdscr, y + 2, col2_x, f"Spread: {spread_str}", self._attr(3, bold=True))
        self._safe_addstr(stdscr, y + 3, col2_x, f"Basis : {bps_str}", self._attr(6))

        # --- Section 3: Best Ask ---
        self._safe_addstr(stdscr, y + 1, col3_x, "[ BEST ASK ]", self._attr(2, bold=True))
        ask_px_str = f"${self.data.best_ask_price:,.2f}" if self.data.best_ask_price is not None else "--"
        ask_qty_str = f"{self.data.best_ask_qty:,.4f}" if self.data.best_ask_qty is not None else "--"
        self._safe_addstr(stdscr, y + 2, col3_x, f"Price : {ask_px_str}", self._attr(2, bold=True))
        self._safe_addstr(stdscr, y + 3, col3_x, f"Size  : {ask_qty_str}", self._attr(6))

        return y + height

    def _render_engine_metrics(self, stdscr, y: int, x: int, width: int) -> int:
        """Render Orders Processed, Throughput, and Latency sections."""
        height = 7
        self._draw_box(stdscr, y, x, height, width, title="ENGINE & PIPELINE PERFORMANCE")

        col_w = (width - 4) // 3
        col1_x = x + 2
        col2_x = col1_x + col_w
        col3_x = col2_x + col_w

        # --- Section 1: Orders Processed ---
        self._safe_addstr(stdscr, y + 1, col1_x, "[ ORDERS PROCESSED ]", self._attr(4, bold=True))
        tot_str = f"{self.data.orders_processed:,}" if self.data.orders_processed is not None else "--"
        match_str = f"{self.data.matched_orders:,}" if self.data.matched_orders is not None else "--"
        canc_str = f"{self.data.canceled_orders:,}" if self.data.canceled_orders is not None else "--"
        self._safe_addstr(stdscr, y + 2, col1_x, f"Total Ingested : {tot_str}", self._attr(6, bold=True))
        self._safe_addstr(stdscr, y + 3, col1_x, f"Matched Trades : {match_str}", self._attr(6))
        self._safe_addstr(stdscr, y + 4, col1_x, f"Cancellations  : {canc_str}", self._attr(6))

        # --- Section 2: Throughput ---
        self._safe_addstr(stdscr, y + 1, col2_x, "[ THROUGHPUT ]", self._attr(4, bold=True))
        tput_str = f"{self.data.throughput_ops:,.0f} ops/sec" if self.data.throughput_ops is not None else "-- ops/sec"
        peak_str = f"{self.data.peak_throughput_ops:,.0f} ops/sec" if self.data.peak_throughput_ops is not None else "-- ops/sec"
        self._safe_addstr(stdscr, y + 2, col2_x, f"Rate : {tput_str}", self._attr(5, bold=True))
        self._safe_addstr(stdscr, y + 3, col2_x, f"Peak : {peak_str}", self._attr(6))

        # --- Section 3: Latency ---
        self._safe_addstr(stdscr, y + 1, col3_x, "[ LATENCY ]", self._attr(4, bold=True))
        avg_str = f"{self.data.latency_avg_us:.1f} us" if self.data.latency_avg_us is not None else "-- us"
        p99_str = f"{self.data.latency_p99_us:.1f} us" if self.data.latency_p99_us is not None else "-- us"
        min_str = f"{self.data.latency_min_us:.1f}" if self.data.latency_min_us is not None else "--"
        max_str = f"{self.data.latency_max_us:.1f}" if self.data.latency_max_us is not None else "--"
        self._safe_addstr(stdscr, y + 2, col3_x, f"Average : {avg_str}", self._attr(5, bold=True))
        self._safe_addstr(stdscr, y + 3, col3_x, f"P99     : {p99_str}", self._attr(5, bold=True))
        self._safe_addstr(stdscr, y + 4, col3_x, f"Min/Max : {min_str} / {max_str} us", self._attr(6))

        return y + height

    def _render_footer(self, stdscr, y: int, x: int, width: int) -> int:
        """Render Footer / Controls guide."""
        height = 3
        self._draw_box(stdscr, y, x, height, width, title="CONTROLS & STATUS")
        controls = "[q] Quit  |  [m] Toggle Sample Mock Data  |  [r] Reset to Placeholders"
        self._safe_addstr(stdscr, y + 1, x + 2, controls, self._attr(4, bold=True))
        return y + height

    def render(self, stdscr) -> None:
        """Render a single frame of the terminal dashboard."""
        max_y, max_x = stdscr.getmaxyx()

        # Handle terminal too small
        if max_y < self.MIN_HEIGHT or max_x < self.MIN_WIDTH:
            stdscr.clear()
            msg = f"Terminal too small: {max_x}x{max_y}. Minimum required: {self.MIN_WIDTH}x{self.MIN_HEIGHT}"
            self._safe_addstr(stdscr, 1, 2, msg, self._attr(3, bold=True))
            self._safe_addstr(stdscr, 2, 2, "Please enlarge your terminal window (or press 'q' to quit).", self._attr(6))
            stdscr.refresh()
            return

        stdscr.erase()

        # Determine dashboard width (capped at 86 columns for sleek alignment or scales to width - 2)
        target_width = min(88, max_x - 2)
        start_x = max(0, (max_x - target_width) // 2)

        cur_y = 0
        cur_y = self._render_header(stdscr, cur_y, start_x, target_width)
        cur_y = self._render_market_depth(stdscr, cur_y, start_x, target_width)
        cur_y = self._render_engine_metrics(stdscr, cur_y, start_x, target_width)
        self._render_footer(stdscr, cur_y, start_x, target_width)

        stdscr.refresh()

    def _main_loop(self, stdscr, max_seconds: Optional[float] = None, max_frames: Optional[int] = None) -> None:
        """Internal curses event loop."""
        try:
            curses.curs_set(0)
        except Exception:
            pass

        self._init_colors()
        timeout_ms = int(self.refresh_interval * 1000)
        stdscr.timeout(timeout_ms)

        start_time = time.perf_counter()
        frames_rendered = 0

        while True:
            # Check maximum duration if specified (useful for automated testing)
            if max_seconds is not None and (time.perf_counter() - start_time) >= max_seconds:
                break
            if max_frames is not None and frames_rendered >= max_frames:
                break

            # Poll data provider if hooked
            if self.data_provider is not None:
                try:
                    self.data = self.data_provider()
                except Exception:
                    pass

            # Render dashboard frame
            self.render(stdscr)
            frames_rendered += 1

            # Non-blocking input check
            try:
                ch = stdscr.getch()
            except Exception:
                ch = -1

            if ch in (ord("q"), ord("Q"), 27, 3):  # 'q', 'Q', ESC, Ctrl+C
                break
            elif ch in (ord("m"), ord("M")):
                # Toggle between mock sample data and placeholder
                self.use_sample_data = not self.use_sample_data
                if self.use_sample_data:
                    self.data = DashboardData.create_sample(symbol=self.data.symbol)
                else:
                    self.data = DashboardData.create_placeholder(symbol=self.data.symbol)
            elif ch in (ord("r"), ord("R")):
                # Reset to placeholders
                self.use_sample_data = False
                self.data = DashboardData.create_placeholder(symbol=self.data.symbol)
            elif ch == curses.KEY_RESIZE if curses else -2:
                stdscr.clear()

    def run(self, max_seconds: Optional[float] = None, max_frames: Optional[int] = None) -> None:
        """Launch the curses dashboard.

        Args:
            max_seconds: Optional duration in seconds before exiting automatically.
            max_frames: Optional maximum number of frames to render before exiting.
        """
        if curses is None:
            raise RuntimeError("The curses module is required to run the terminal dashboard.")

        _prepare_windows_console()
        curses.wrapper(self._main_loop, max_seconds, max_frames)
