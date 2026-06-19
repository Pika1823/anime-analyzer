"""
fetch_snapshots.py のユニットテスト。
外部 API 呼び出しはすべてモックする。
"""
from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from fetch_snapshots import calc_daily_view, fetch_novel_snapshot


# ── calc_daily_view のテスト ──────────────────────────────────────────────────

def test_calc_daily_view_returns_none_when_no_previous_data():
    """前日データが存在しない場合は None を返す。"""
    result = calc_daily_view("N001", 1000, pd.DataFrame(), date(2026, 6, 19))
    assert result is None


def test_calc_daily_view_returns_diff_from_yesterday():
    """前日の累計 view との差分を返す。"""
    snapshots = pd.DataFrame([{
        "ncode": "N001",
        "date": "2026-06-18",
        "cumulative_view": 800,
    }])
    result = calc_daily_view("N001", 1000, snapshots, date(2026, 6, 19))
    assert result == 200


def test_calc_daily_view_returns_none_when_ncode_not_found():
    """対象 ncode のデータが存在しない場合は None を返す。"""
    snapshots = pd.DataFrame([{
        "ncode": "N002",
        "date": "2026-06-18",
        "cumulative_view": 800,
    }])
    result = calc_daily_view("N001", 1000, snapshots, date(2026, 6, 19))
    assert result is None


def test_calc_daily_view_returns_none_when_prev_cumulative_is_nan():
    """前日の cumulative_view が NaN の場合は None を返す。"""
    snapshots = pd.DataFrame([{
        "ncode": "N001",
        "date": "2026-06-18",
        "cumulative_view": np.nan,
    }])
    result = calc_daily_view("N001", 1000, snapshots, date(2026, 6, 19))
    assert result is None


def test_calc_daily_view_returns_zero_when_no_change():
    """前日と累計 view が同じ場合は 0 を返す。"""
    snapshots = pd.DataFrame([{
        "ncode": "N001",
        "date": "2026-06-18",
        "cumulative_view": 1000,
    }])
    result = calc_daily_view("N001", 1000, snapshots, date(2026, 6, 19))
    assert result == 0


def test_calc_daily_view_handles_missing_allcount():
    """allcount が None の場合はスキップされることを確認する。"""
    # fetch_novel_snapshot が allcount なしの dict を返す場合
    # main() 側でスキップされる（calc_daily_view には到達しない）
    # このケースは main() のテストで確認するが、
    # calc_daily_view に None を渡しても壊れないことを確認する
    result = calc_daily_view("N001", None, pd.DataFrame(), date(2026, 6, 19))
    assert result is None


# ── fetch_novel_snapshot のテスト ─────────────────────────────────────────────

def test_fetch_novel_snapshot_returns_dict_on_success():
    """正常レスポンス時に作品データの dict を返す。"""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"allcount": 1},
        {"ncode": "N001", "allcount": 5000, "bookmarkcount": 100},
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("fetch_snapshots.requests.get", return_value=mock_response):
        result = fetch_novel_snapshot("N001")

    assert result is not None
    assert result["allcount"] == 5000
    assert result["bookmarkcount"] == 100


def test_fetch_novel_snapshot_returns_none_on_empty_response():
    """API レスポンスが空（作品なし）の場合は None を返す。"""
    mock_response = MagicMock()
    mock_response.json.return_value = [{"allcount": 0}]
    mock_response.raise_for_status = MagicMock()

    with patch("fetch_snapshots.requests.get", return_value=mock_response):
        result = fetch_novel_snapshot("N001")

    assert result is None


def test_fetch_novel_snapshot_returns_none_on_request_error():
    """通信エラー時に None を返す。"""
    with patch("fetch_snapshots.requests.get", side_effect=Exception("接続エラー")):
        result = fetch_novel_snapshot("N001")

    assert result is None
