"""Tests for funding field parsing from Binance mark / premiumIndex payloads."""

import pytest

from app.core.funding_from_mark import parse_funding_from_payload


def test_parse_websocket_mark_price_update_keys():
    rate, t_ms = parse_funding_from_payload(
        {"e": "markPriceUpdate", "r": "0.00012345", "T": 1744816320000}
    )
    assert rate == pytest.approx(0.00012345)
    assert t_ms == 1744816320000


def test_parse_premium_index_rest_keys():
    rate, t_ms = parse_funding_from_payload(
        {"lastFundingRate": "0.00005", "nextFundingTime": "1744816400000"}
    )
    assert rate == pytest.approx(0.00005)
    assert t_ms == 1744816400000


def test_parse_missing_returns_none():
    assert parse_funding_from_payload({}) == (None, None)
    assert parse_funding_from_payload({"mark_price": 1.0}) == (None, None)


def test_parse_invalid_numbers():
    rate, t_ms = parse_funding_from_payload({"r": "x", "T": "y"})
    assert rate is None
    assert t_ms is None
