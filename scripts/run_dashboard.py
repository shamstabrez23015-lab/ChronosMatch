"""CLI runner for the ChronosMatch Terminal Dashboard (Week 2 Prototype)."""

import argparse
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chronos.dashboard import ChronosDashboard, DashboardData


def main():
    parser = argparse.ArgumentParser(
        description="ChronosMatch Terminal Dashboard - Real-time LOB & Performance Monitor (Week 2 Prototype)"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC-USDT",
        help="Market symbol to display (default: BTC-USDT)",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        default=False,
        help="Launch with sample mock metrics instead of placeholders ('--')",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=10.0,
        help="Refresh rate in frames per second (default: 10.0)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Optional duration in seconds to run before cleanly exiting (default: run until 'q')",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Optional maximum number of frames to render before cleanly exiting",
    )
    args = parser.parse_args()

    # Initialize dashboard data
    if args.sample:
        data = DashboardData.create_sample(symbol=args.symbol)
    else:
        data = DashboardData.create_placeholder(symbol=args.symbol)

    refresh_interval = 1.0 / max(1.0, args.fps)
    dashboard = ChronosDashboard(
        data=data,
        use_sample_data=args.sample,
        refresh_interval=refresh_interval,
    )

    try:
        dashboard.run(
            max_seconds=args.duration,
            max_frames=args.max_frames,
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n[!] Dashboard error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
