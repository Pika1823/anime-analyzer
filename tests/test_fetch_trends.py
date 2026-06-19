"""
fetch_trends.py のユニットテスト。
PyTrends の呼び出しと rate_limit_sleep はすべてモックする。
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fetch_trends import build_trend_rows, fetch_trend_score, get_week_start


# ---------------------------------------------------------------------------
# get_week_start
# ---------------------------------------------------------------------------

def test_get_week_start_on_monday():
    # 2026-06-15 は月曜日 → そのまま返す
    assert get_week_start(date(2026, 6, 15)) == "2026-06-15"


def test_get_week_start_on_wednesday_returns_monday():
    # 2026-06-17 は水曜日 → 属する週の月曜は 2026-06-15
    assert get_week_start(date(2026, 6, 17)) == "2026-06-15"


def test_get_week_start_on_sunday_returns_monday():
    # 2026-06-21 は日曜日 → 属する週の月曜は 2026-06-15
    assert get_week_start(date(2026, 6, 21)) == "2026-06-15"


# ---------------------------------------------------------------------------
# build_trend_rows
# ---------------------------------------------------------------------------

def test_build_trend_rows_on_success_returns_one_row_per_week():
    scores = {"2026-06-15": 80, "2026-06-22": 60}
    rows = build_trend_rows("N001", "novel", "転スラ", scores, success=True)
    assert len(rows) == 2
    assert all(r["fetch_status"] == "ok" for r in rows)
    assert rows[0]["trend_score"] == 80
    assert rows[1]["trend_score"] == 60


def test_build_trend_rows_on_success_sets_correct_fields():
    scores = {"2026-06-15": 50}
    rows = build_trend_rows("anime_001", "anime", "転スラ", scores, success=True)
    assert rows[0]["id"] == "anime_001"
    assert rows[0]["id_type"] == "anime"
    assert rows[0]["keyword_used"] == "転スラ"
    assert rows[0]["region"] == "JP"
    assert rows[0]["week_start"] == "2026-06-15"


def test_build_trend_rows_on_failure_returns_single_skip_row():
    rows = build_trend_rows("N001", "novel", "転スラ", {}, success=False)
    assert len(rows) == 1
    assert rows[0]["fetch_status"] == "skip"
    assert rows[0]["trend_score"] is None


def test_build_trend_rows_on_failure_sets_correct_fields():
    rows = build_trend_rows("N001", "novel", "転スラ", {}, success=False)
    assert rows[0]["id"] == "N001"
    assert rows[0]["keyword_used"] == "転スラ"
    assert rows[0]["region"] == "JP"


# ---------------------------------------------------------------------------
# fetch_trend_score
# ---------------------------------------------------------------------------

def test_fetch_trend_score_returns_scores_on_success():
    """interest_over_time() が正常なデータを返した場合、スコアと True を返す。"""
    mock_pytrends = MagicMock()
    # キーワード列と日付インデックスを持つ DataFrame を作成
    df = pd.DataFrame(
        {"転スラ": [80, 60], "isPartial": [False, False]},
        index=pd.to_datetime(["2026-06-15", "2026-06-22"]),
    )
    mock_pytrends.interest_over_time.return_value = df

    scores, success = fetch_trend_score(mock_pytrends, "転スラ")

    assert success is True
    assert scores == {"2026-06-15": 80, "2026-06-22": 60}
    mock_pytrends.build_payload.assert_called_once_with(
        ["転スラ"], cat=0, timeframe="today 3-m", geo="JP"
    )


def test_fetch_trend_score_returns_false_on_empty_df():
    """interest_over_time() が空 DataFrame を返した場合、False を返す。"""
    mock_pytrends = MagicMock()
    mock_pytrends.interest_over_time.return_value = pd.DataFrame()

    scores, success = fetch_trend_score(mock_pytrends, "存在しないキーワード")

    assert success is False
    assert scores == {}


def test_fetch_trend_score_returns_false_on_exception():
    """API 呼び出しが例外を起こした場合、例外を伝播せず False を返す。"""
    mock_pytrends = MagicMock()
    mock_pytrends.interest_over_time.side_effect = Exception("接続エラー")

    scores, success = fetch_trend_score(mock_pytrends, "転スラ")

    assert success is False
    assert scores == {}


def test_fetch_trend_score_returns_false_when_keyword_not_in_df():
    """返却 DataFrame にキーワード列がない場合、False を返す。"""
    mock_pytrends = MagicMock()
    df = pd.DataFrame(
        {"別キーワード": [80]},
        index=pd.to_datetime(["2026-06-15"]),
    )
    mock_pytrends.interest_over_time.return_value = df

    scores, success = fetch_trend_score(mock_pytrends, "転スラ")

    assert success is False
    assert scores == {}
