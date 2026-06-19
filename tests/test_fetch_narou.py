"""
fetch_narou.py のユニットテスト。
外部 API 呼び出しはすべてモックする。
"""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fetch_narou import build_novels_df, fetch_monthly_top, upsert_novels


# ---------------------------------------------------------------------------
# build_novels_df
# ---------------------------------------------------------------------------

def test_build_novels_df_sets_basic_fields():
    raw = [
        {
            "ncode": "N1234AB",
            "title": "テスト小説",
            "writer": "著者A",
            "genre": 2,
            "keyword": "異世界 転生",
            "bookmarkcount": 1000,
            "allcount": 50000,
        },
    ]
    df = build_novels_df(raw, anime_ncodes=set())
    assert df.iloc[0]["ncode"] == "N1234AB"
    assert df.iloc[0]["title"] == "テスト小説"
    assert df.iloc[0]["author"] == "著者A"
    assert df.iloc[0]["monthly_rank_latest"] == 1
    assert df.iloc[0]["bookmark_count_latest"] == 1000


def test_build_novels_df_sets_is_anime_false_by_default():
    raw = [
        {
            "ncode": "N1234AB",
            "title": "作品",
            "writer": "著者",
            "genre": 2,
            "keyword": "",
            "bookmarkcount": 0,
            "allcount": 0,
        }
    ]
    df = build_novels_df(raw, anime_ncodes=set())
    assert df.iloc[0]["is_anime"] == False  # noqa: E712 (np.bool_ との比較のため == を使用)


def test_build_novels_df_sets_is_anime_true_when_in_anime_ncodes():
    raw = [
        {
            "ncode": "N1234AB",
            "title": "転スラ",
            "writer": "著者",
            "genre": 2,
            "keyword": "",
            "bookmarkcount": 0,
            "allcount": 0,
        }
    ]
    df = build_novels_df(raw, anime_ncodes={"N1234AB"})
    assert df.iloc[0]["is_anime"] == True  # noqa: E712 (np.bool_ との比較のため == を使用)


def test_build_novels_df_ncode_uppercased():
    raw = [
        {
            "ncode": "n1234ab",
            "title": "作品",
            "writer": "著者",
            "genre": 2,
            "keyword": "",
            "bookmarkcount": 0,
            "allcount": 0,
        }
    ]
    df = build_novels_df(raw, anime_ncodes=set())
    assert df.iloc[0]["ncode"] == "N1234AB"


def test_build_novels_df_assigns_rank_by_position():
    raw = [
        {
            "ncode": "N001",
            "title": "1位",
            "writer": "A",
            "genre": 2,
            "keyword": "",
            "bookmarkcount": 0,
            "allcount": 0,
        },
        {
            "ncode": "N002",
            "title": "2位",
            "writer": "B",
            "genre": 2,
            "keyword": "",
            "bookmarkcount": 0,
            "allcount": 0,
        },
    ]
    df = build_novels_df(raw, anime_ncodes=set())
    assert df.iloc[0]["monthly_rank_latest"] == 1
    assert df.iloc[1]["monthly_rank_latest"] == 2


def test_build_novels_df_sets_tags_from_keyword():
    raw = [
        {
            "ncode": "N001",
            "title": "作品",
            "writer": "著者",
            "genre": 2,
            "keyword": "ファンタジー 魔法",
            "bookmarkcount": 0,
            "allcount": 0,
        }
    ]
    df = build_novels_df(raw, anime_ncodes=set())
    assert df.iloc[0]["tags"] == "ファンタジー 魔法"


# ---------------------------------------------------------------------------
# upsert_novels
# ---------------------------------------------------------------------------

def test_upsert_novels_returns_new_df_when_existing_is_empty():
    new_df = pd.DataFrame(
        [{"ncode": "N001", "title": "A", "updated_at": "2026-01-01"}]
    )
    result = upsert_novels(pd.DataFrame(), new_df)
    assert len(result) == 1
    assert result.iloc[0]["ncode"] == "N001"


def test_upsert_novels_updates_existing_row():
    existing = pd.DataFrame(
        [{"ncode": "N001", "title": "旧タイトル", "updated_at": "2026-01-01"}]
    )
    new_df = pd.DataFrame(
        [{"ncode": "N001", "title": "新タイトル", "updated_at": "2026-06-01"}]
    )
    result = upsert_novels(existing, new_df)
    assert len(result) == 1
    assert result.iloc[0]["title"] == "新タイトル"
    assert result.iloc[0]["updated_at"] == "2026-06-01"


def test_upsert_novels_adds_new_row_not_in_existing():
    existing = pd.DataFrame(
        [{"ncode": "N001", "title": "A", "updated_at": "2026-06-01"}]
    )
    new_df = pd.DataFrame(
        [
            {"ncode": "N001", "title": "A", "updated_at": "2026-06-01"},
            {"ncode": "N002", "title": "B", "updated_at": "2026-06-01"},
        ]
    )
    result = upsert_novels(existing, new_df)
    assert len(result) == 2
    assert set(result["ncode"]) == {"N001", "N002"}


def test_upsert_novels_keeps_existing_row_not_in_new():
    """新規データに含まれない既存行は保持される。"""
    existing = pd.DataFrame(
        [
            {"ncode": "N001", "title": "A", "updated_at": "2026-01-01"},
            {"ncode": "N003", "title": "C", "updated_at": "2026-01-01"},
        ]
    )
    new_df = pd.DataFrame(
        [{"ncode": "N001", "title": "A更新", "updated_at": "2026-06-01"}]
    )
    result = upsert_novels(existing, new_df)
    assert len(result) == 2
    assert set(result["ncode"]) == {"N001", "N003"}


# ---------------------------------------------------------------------------
# fetch_monthly_top（requests.get をモック）
# ---------------------------------------------------------------------------

def _make_mock_response(items: list[dict]) -> MagicMock:
    """requests.get が返すレスポンスのモックを生成する。"""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    # jsonlite 形式: 先頭要素はメタ情報
    mock_resp.json.return_value = [{"allcount": len(items)}] + items
    return mock_resp


def test_fetch_monthly_top_returns_items():
    """取得件数が limit 以下の場合に正しくリストを返す。"""
    items = [
        {"ncode": f"N{i:04d}", "title": f"作品{i}", "writer": "著者"}
        for i in range(5)
    ]
    with patch("fetch_narou.requests.get", return_value=_make_mock_response(items)):
        result = fetch_monthly_top(limit=5)
    assert len(result) == 5
    assert result[0]["ncode"] == "N0000"


def test_fetch_monthly_top_stops_when_empty_response():
    """API が空リストを返した場合にループが終了する。"""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    # メタ情報のみ（アイテムなし）
    mock_resp.json.return_value = [{"allcount": 0}]

    with patch("fetch_narou.requests.get", return_value=mock_resp):
        result = fetch_monthly_top(limit=100)
    assert result == []


def test_fetch_monthly_top_paginates_correctly():
    """PAGE_SIZE より多い件数を要求した場合に複数回リクエストする。"""
    # 1ページ目: 3件、2ページ目: 2件
    page1 = [
        {"ncode": f"N{i:04d}", "title": f"作品{i}"} for i in range(3)
    ]
    page2 = [
        {"ncode": f"N{i:04d}", "title": f"作品{i}"} for i in range(3, 5)
    ]

    responses = [_make_mock_response(page1), _make_mock_response(page2)]
    with patch("fetch_narou.requests.get", side_effect=responses) as mock_get:
        # PAGE_SIZE を 3 に差し替えてページネーションを強制
        with patch("fetch_narou.NAROU_PAGE_SIZE", 3):
            result = fetch_monthly_top(limit=5)

    assert len(result) == 5
    assert mock_get.call_count == 2
