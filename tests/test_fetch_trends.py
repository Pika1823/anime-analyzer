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
    rows = build_trend_rows("N001", "novel", "転スラ", scores, success=True, week_start="2026-06-15")
    assert len(rows) == 2
    assert all(r["fetch_status"] == "ok" for r in rows)
    assert rows[0]["trend_score"] == 80
    assert rows[1]["trend_score"] == 60


def test_build_trend_rows_on_success_sets_correct_fields():
    scores = {"2026-06-15": 50}
    rows = build_trend_rows("anime_001", "anime", "転スラ", scores, success=True, week_start="2026-06-15")
    assert rows[0]["id"] == "anime_001"
    assert rows[0]["id_type"] == "anime"
    assert rows[0]["keyword_used"] == "転スラ"
    assert rows[0]["region"] == "JP"
    assert rows[0]["week_start"] == "2026-06-15"


def test_build_trend_rows_on_failure_returns_single_skip_row():
    rows = build_trend_rows("N001", "novel", "転スラ", {}, success=False, week_start="2026-06-15")
    assert len(rows) == 1
    assert rows[0]["fetch_status"] == "skip"
    assert rows[0]["trend_score"] is None


def test_build_trend_rows_on_failure_sets_correct_fields():
    rows = build_trend_rows("N001", "novel", "転スラ", {}, success=False, week_start="2026-06-15")
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


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def test_main_calls_rate_limit_sleep_for_each_keyword(monkeypatch):
    """main() が各キーワードのリクエスト後に rate_limit_sleep を呼ぶことを確認する。"""
    import fetch_trends
    from unittest.mock import MagicMock, patch
    import pandas as pd

    # novels: 1作品
    novels_df = pd.DataFrame([{
        "ncode": "N001", "title": "テスト小説"
    }])
    # anime_works: 1作品（title_short と title_full の2キーワード）
    anime_df = pd.DataFrame([{
        "anime_id": "anime_001", "title_short": "略称", "title_full": "正式名称"
    }])

    mock_sleep = MagicMock()
    mock_pytrends = MagicMock()
    mock_pytrends_class = MagicMock(return_value=mock_pytrends)
    # fetch_trend_score を (空 scores, False) を返すようにモック
    mock_fetch = MagicMock(return_value=({}, False))

    monkeypatch.setattr(fetch_trends, "is_weekly_run_day", lambda: True)
    monkeypatch.setattr(fetch_trends, "load_csv", lambda path, dtype=None: (
        novels_df if "novels" in str(path) else
        (anime_df if "anime_works" in str(path) else pd.DataFrame())
    ))
    monkeypatch.setattr(fetch_trends, "save_csv", MagicMock())
    monkeypatch.setattr(fetch_trends, "rate_limit_sleep", mock_sleep)
    monkeypatch.setattr(fetch_trends, "fetch_trend_score", mock_fetch)

    with patch("fetch_trends.TrendReq", mock_pytrends_class):
        fetch_trends.main()

    # novels 1キーワード + anime_works 2キーワード = 計3回
    assert mock_sleep.call_count == 3


def test_main_skips_on_non_weekly_day(monkeypatch):
    """月曜以外は main() が何もせず終了することを確認する。"""
    import fetch_trends
    from unittest.mock import MagicMock

    mock_save = MagicMock()
    monkeypatch.setattr(fetch_trends, "is_weekly_run_day", lambda: False)
    monkeypatch.setattr(fetch_trends, "save_csv", mock_save)

    fetch_trends.main()

    mock_save.assert_not_called()
