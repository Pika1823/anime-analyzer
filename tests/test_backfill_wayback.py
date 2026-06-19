"""
backfill_wayback.py のユニットテスト。
外部 HTTP 呼び出しはすべてモックする。
"""
from unittest.mock import MagicMock, patch

import pytest

from backfill_wayback import (
    fetch_archive_html,
    list_archive_urls,
    parse_ranking_html,
)

# なろうランキングページの簡略化されたサンプル HTML
SAMPLE_HTML_WITH_RANKS = """
<html><body>
<div class="rank_h"><a href="/novel/N1234AB/">転生小説タイトル</a></div>
<div class="rank_h"><a href="/novel/N5678CD/">異世界小説タイトル</a></div>
<div class="rank_h"><a href="/novel/N9999ZZ/">三番目の小説</a></div>
</body></html>
"""

SAMPLE_HTML_NO_RANKS = "<html><body><p>データなし</p></body></html>"


# ---------------------------------------------------------------------------
# parse_ranking_html
# ---------------------------------------------------------------------------


def test_parse_ranking_html_extracts_ncodes():
    """rank_h 要素から ncode を正しく抽出する。"""
    rows = parse_ranking_html(SAMPLE_HTML_WITH_RANKS, "2024-01-15")
    ncodes = [r["ncode"] for r in rows]
    assert "N1234AB" in ncodes
    assert "N5678CD" in ncodes
    assert "N9999ZZ" in ncodes


def test_parse_ranking_html_sets_monthly_rank_in_order():
    """monthly_rank が 1 始まりで順番に付与される。"""
    rows = parse_ranking_html(SAMPLE_HTML_WITH_RANKS, "2024-01-15")
    assert rows[0]["monthly_rank"] == 1
    assert rows[1]["monthly_rank"] == 2
    assert rows[2]["monthly_rank"] == 3


def test_parse_ranking_html_sets_date():
    """date フィールドに snapshot_date が設定される。"""
    rows = parse_ranking_html(SAMPLE_HTML_WITH_RANKS, "2024-01-15")
    assert all(r["date"] == "2024-01-15" for r in rows)


def test_parse_ranking_html_sets_view_fields_to_none():
    """取得不可能なフィールドは None になる。"""
    rows = parse_ranking_html(SAMPLE_HTML_WITH_RANKS, "2024-01-15")
    assert all(r["cumulative_view"] is None for r in rows)
    assert all(r["daily_view"] is None for r in rows)
    assert all(r["bookmark_count"] is None for r in rows)
    assert all(r["weekly_rank"] is None for r in rows)


def test_parse_ranking_html_returns_empty_list_when_no_items():
    """rank_h 要素が存在しない場合は空リストを返す。"""
    rows = parse_ranking_html(SAMPLE_HTML_NO_RANKS, "2024-01-15")
    assert rows == []


def test_parse_ranking_html_uppercases_ncode():
    """ncode は大文字に正規化される。"""
    html = '<html><body><div class="rank_h"><a href="/novel/n1234ab/">タイトル</a></div></body></html>'
    rows = parse_ranking_html(html, "2024-01-15")
    assert rows[0]["ncode"] == "N1234AB"


# ---------------------------------------------------------------------------
# list_archive_urls
# ---------------------------------------------------------------------------


def test_list_archive_urls_returns_parsed_entries():
    """CDX API のレスポンスを正しくパースすることを確認する。"""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        ["timestamp", "original"],
        ["20240101120000", "https://yomou.syosetu.com/..."],
        ["20240201120000", "https://yomou.syosetu.com/..."],
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("backfill_wayback.requests.get", return_value=mock_response):
        from datetime import date
        result = list_archive_urls(date(2024, 1, 1), date(2024, 3, 1))

    assert len(result) == 2
    assert result[0]["timestamp"] == "20240101120000"
    assert result[1]["timestamp"] == "20240201120000"


def test_list_archive_urls_returns_empty_on_empty_response():
    """CDX API が空リストを返した場合に空リストが返ることを確認する。"""
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    with patch("backfill_wayback.requests.get", return_value=mock_response):
        from datetime import date
        result = list_archive_urls(date(2024, 1, 1), date(2024, 3, 1))

    assert result == []


# ---------------------------------------------------------------------------
# fetch_archive_html
# ---------------------------------------------------------------------------


def test_fetch_archive_html_returns_html_on_success():
    """アーカイブ HTML の取得が成功した場合に文字列が返ることを確認する。"""
    mock_response = MagicMock()
    mock_response.text = "<html><body>テスト</body></html>"
    mock_response.raise_for_status = MagicMock()

    with patch("backfill_wayback.requests.get", return_value=mock_response):
        result = fetch_archive_html("20240101120000")

    assert result == "<html><body>テスト</body></html>"


def test_fetch_archive_html_returns_none_on_error():
    """HTTP エラー時に None が返ることを確認する。"""
    import requests as req

    with patch("backfill_wayback.requests.get", side_effect=req.exceptions.RequestException("接続失敗")):
        result = fetch_archive_html("20240101120000")

    assert result is None
