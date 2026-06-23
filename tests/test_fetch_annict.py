# test_fetch_annict.py

"""
fetch_annict.py のユニットテスト。
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fetch_annict import (
    MATCH_THRESHOLD,
    REFRESH_DAYS,
    build_annict_row,
    calc_title_similarity,
    fetch_annict_data,
    find_best_match,
    update_novels_is_anime,
    upsert_annict_works,
    _should_skip,
)


# --- calc_title_similarity ---

def test_calc_title_similarity_exact_match():
    """完全一致のタイトルは 1.0 を返す。"""
    assert calc_title_similarity("転生したらスライムだった件", "転生したらスライムだった件") == 1.0


def test_calc_title_similarity_no_match():
    """全く異なるタイトルは 0.0 に近い値を返す。"""
    score = calc_title_similarity("ABCDE", "12345")
    assert score < 0.2


def test_calc_title_similarity_partial():
    """部分一致の場合は 0.0 より大きく 1.0 未満の値を返す。"""
    score = calc_title_similarity("転生したらスライムだった件", "転スラ")
    assert 0.0 < score < 1.0


# --- find_best_match ---

def test_find_best_match_empty_candidates():
    """候補が空の場合は (None, 0.0) を返す。"""
    result, score = find_best_match("転生したらスライムだった件", [])
    assert result is None
    assert score == 0.0


def test_find_best_match_single_candidate():
    """単一候補が返ってきた場合にその候補とスコアを返す。"""
    candidates = [{"annictId": 1, "title": "転生したらスライムだった件", "watchersCount": 5000}]
    result, score = find_best_match("転生したらスライムだった件", candidates)
    assert result is not None
    assert result["annictId"] == 1
    assert score == 1.0


def test_find_best_match_selects_best():
    """複数候補のうち類似度が最も高いものを選択する。"""
    candidates = [
        {"annictId": 1, "title": "転スラ", "watchersCount": 5000},
        {"annictId": 2, "title": "転生したらスライムだった件", "watchersCount": 3000},
    ]
    result, score = find_best_match("転生したらスライムだった件", candidates)
    assert result is not None
    assert result["annictId"] == 2
    assert score == 1.0


# --- build_annict_row ---

def test_build_annict_row_matched():
    """マッチスコアが閾値以上の場合に is_matched=True で行を生成する。"""
    match = {
        "annictId": 123,
        "title": "転生したらスライムだった件",
        "titleKana": "てんせいしたらすらいむだったけん",
        "watchersCount": 8000,
        "satisfactionRate": 88.5,
        "reviewsCount": 120,
        "episodesCount": 24,
        "seasonYear": 2018,
        "seasonName": "AUTUMN",
        "media": "TV",
    }
    row = build_annict_row("N6316BN", "転生したらスライムだった件", match, 1.0)
    assert row["is_matched"] is True
    assert row["annict_id"] == 123
    assert row["watchers_count"] == 8000
    assert row["satisfaction_rate"] == 88.5
    assert row["reviews_count"] == 120
    assert row["season_name"] == "autumn"
    assert row["media"] == "TV"
    assert row["ncode"] == "N6316BN"


def test_build_annict_row_below_threshold():
    """マッチスコアが閾値未満の場合は is_matched=False で行を生成する。"""
    match = {"annictId": 999, "title": "全く別のアニメ", "watchersCount": 100}
    row = build_annict_row("N0001AA", "転生したらスライムだった件", match, 0.1)
    assert row["is_matched"] is False
    assert row["annict_id"] is None
    assert row["watchers_count"] is None


def test_build_annict_row_no_match():
    """候補なし（match=None）の場合は is_matched=False を返す。"""
    row = build_annict_row("N0001AA", "テスト作品", None, 0.0)
    assert row["is_matched"] is False
    assert row["annict_id"] is None


# --- _should_skip ---

def test_should_skip_matched_always_skips():
    """マッチ済みエントリは常にスキップする。"""
    row = pd.Series({
        "ncode": "N001",
        "is_matched": True,
        "fetched_at": (date.today() - timedelta(days=100)).isoformat(),
    })
    assert _should_skip(row, date.today()) is True


def test_should_skip_unmatched_recent():
    """未発見でも REFRESH_DAYS 以内はスキップする。"""
    row = pd.Series({
        "ncode": "N001",
        "is_matched": False,
        "fetched_at": (date.today() - timedelta(days=REFRESH_DAYS - 1)).isoformat(),
    })
    assert _should_skip(row, date.today()) is True


def test_should_skip_unmatched_expired():
    """未発見で REFRESH_DAYS 以上経過したエントリはスキップしない（再検索する）。"""
    row = pd.Series({
        "ncode": "N001",
        "is_matched": False,
        "fetched_at": (date.today() - timedelta(days=REFRESH_DAYS + 1)).isoformat(),
    })
    assert _should_skip(row, date.today()) is False


# --- update_novels_is_anime ---

def test_update_novels_is_anime_sets_true():
    """Annict マッチ済み ncode の is_anime を True に更新する。"""
    novels = pd.DataFrame([
        {"ncode": "N001", "is_anime": False},
        {"ncode": "N002", "is_anime": False},
        {"ncode": "N003", "is_anime": False},
    ])
    annict = pd.DataFrame([
        {"ncode": "N001", "is_matched": True},
        {"ncode": "N002", "is_matched": False},
    ])
    result = update_novels_is_anime(novels, annict)
    assert bool(result.loc[result["ncode"] == "N001", "is_anime"].iloc[0]) is True
    assert bool(result.loc[result["ncode"] == "N002", "is_anime"].iloc[0]) is False
    assert bool(result.loc[result["ncode"] == "N003", "is_anime"].iloc[0]) is False


def test_update_novels_is_anime_does_not_unset_true():
    """既存の is_anime=True は Annict 未マッチでも False にしない。"""
    novels = pd.DataFrame([
        {"ncode": "N001", "is_anime": True},
    ])
    annict = pd.DataFrame([
        {"ncode": "N001", "is_matched": False},
    ])
    result = update_novels_is_anime(novels, annict)
    assert str(result.loc[result["ncode"] == "N001", "is_anime"].iloc[0]).lower() == "true"


def test_update_novels_is_anime_empty_annict():
    """annict_df が空の場合は novels_df をそのまま返す。"""
    novels = pd.DataFrame([{"ncode": "N001", "is_anime": False}])
    result = update_novels_is_anime(novels, pd.DataFrame())
    assert result.equals(novels)


# --- upsert_annict_works ---

def test_upsert_annict_works_new_entry():
    """既存データに存在しない ncode は追加される。"""
    existing = pd.DataFrame([{"ncode": "N001", "annict_id": 10, "is_matched": True}])
    new = pd.DataFrame([{"ncode": "N002", "annict_id": None, "is_matched": False}])
    result = upsert_annict_works(existing, new)
    assert len(result) == 2
    assert "N002" in result["ncode"].values


def test_upsert_annict_works_updates_existing():
    """既存の ncode は新規データで上書きされる。"""
    existing = pd.DataFrame([{"ncode": "N001", "is_matched": False, "watchers_count": None}])
    new = pd.DataFrame([{"ncode": "N001", "is_matched": True, "watchers_count": 5000}])
    result = upsert_annict_works(existing, new)
    assert len(result) == 1
    updated_row = result[result["ncode"] == "N001"].iloc[0]
    assert str(updated_row["is_matched"]).lower() == "true"


def test_upsert_annict_works_empty_existing():
    """既存データが空の場合は新規データをそのまま返す。"""
    new = pd.DataFrame([{"ncode": "N001", "is_matched": True}])
    result = upsert_annict_works(pd.DataFrame(), new)
    assert len(result) == 1


# --- fetch_annict_data（モック） ---

def _make_novels_df(ncodes_titles: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame([{"ncode": nc, "title": t} for nc, t in ncodes_titles])


@patch("fetch_annict.search_works")
@patch("fetch_annict.time.sleep")
def test_fetch_annict_data_match_found(mock_sleep, mock_search):
    """search_works がヒットした場合、is_matched=True の行を返す。"""
    mock_search.return_value = [
        {
            "annictId": 999,
            "title": "転生したらスライムだった件",
            "watchersCount": 8000,
            "satisfactionRate": 88.0,
            "reviewsCount": 100,
            "episodesCount": 24,
            "seasonYear": 2018,
            "seasonName": "AUTUMN",
            "media": "TV",
        }
    ]
    novels = _make_novels_df([("N6316BN", "転生したらスライムだった件")])
    result = fetch_annict_data(novels, "dummy_token", pd.DataFrame())
    assert len(result) == 1
    assert bool(result.iloc[0]["is_matched"]) is True
    assert result.iloc[0]["annict_id"] == 999
    mock_sleep.assert_called_once()


@patch("fetch_annict.search_works")
@patch("fetch_annict.time.sleep")
def test_fetch_annict_data_no_match(mock_sleep, mock_search):
    """search_works が空を返した場合、is_matched=False の行を返す。"""
    mock_search.return_value = []
    novels = _make_novels_df([("N0001AA", "全く架空の小説タイトル")])
    result = fetch_annict_data(novels, "dummy_token", pd.DataFrame())
    assert len(result) == 1
    assert bool(result.iloc[0]["is_matched"]) is False


@patch("fetch_annict.search_works")
@patch("fetch_annict.time.sleep")
def test_fetch_annict_data_skips_cached(mock_sleep, mock_search):
    """キャッシュ済み（REFRESH_DAYS 以内）の ncode は検索をスキップする。"""
    existing = pd.DataFrame([{
        "ncode": "N6316BN",
        "is_matched": True,
        "fetched_at": date.today().isoformat(),
    }])
    novels = _make_novels_df([("N6316BN", "転生したらスライムだった件")])
    result = fetch_annict_data(novels, "dummy_token", existing)
    assert len(result) == 0
    mock_search.assert_not_called()
