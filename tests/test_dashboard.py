"""Tests for the ChronosMatch Terminal Dashboard (Week 2 Prototype)."""

import pytest
from chronos.dashboard import ChronosDashboard, DashboardData


def test_dashboard_data_placeholder_defaults():
    """Verify placeholder data returns None for all metric fields."""
    data = DashboardData.create_placeholder(symbol="ETH-USDT")
    assert data.symbol == "ETH-USDT"
    assert data.best_bid_price is None
    assert data.best_bid_qty is None
    assert data.best_ask_price is None
    assert data.best_ask_qty is None
    assert data.spread is None
    assert data.orders_processed is None
    assert data.throughput_ops is None
    assert data.latency_avg_us is None
    assert "STANDBY" in data.engine_status


def test_dashboard_data_sample_values():
    """Verify sample mock data populates realistic metrics."""
    data = DashboardData.create_sample(symbol="BTC-USDT")
    assert data.symbol == "BTC-USDT"
    assert data.best_bid_price == 64250.50
    assert data.best_ask_price == 64251.00
    assert data.spread == 0.50
    assert data.orders_processed > 0
    assert data.throughput_ops > 0
    assert data.latency_avg_us > 0
    assert "RUNNING" in data.engine_status


def test_dashboard_initialization():
    """Verify ChronosDashboard initializes with both default and custom data."""
    # Default (placeholder)
    dash1 = ChronosDashboard()
    assert dash1.data.best_bid_price is None
    assert dash1.use_sample_data is False

    # Sample mock data
    dash2 = ChronosDashboard(use_sample_data=True)
    assert dash2.data.best_bid_price is not None
    assert dash2.use_sample_data is True

    # Custom update
    new_data = DashboardData(
        symbol="SOL-USDT",
        best_bid_price=145.20,
        best_ask_price=145.25,
        spread=0.05,
    )
    dash1.update_data(new_data)
    assert dash1.data.symbol == "SOL-USDT"
    assert dash1.data.best_bid_price == 145.20


def test_dashboard_lifecycle_clean_exit():
    """Verify dashboard opens and terminates cleanly after specified duration or frames."""
    dash = ChronosDashboard(use_sample_data=True, refresh_interval=0.05)
    # Run for 2 frames
    dash.run(max_frames=2)
