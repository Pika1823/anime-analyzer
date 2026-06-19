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


def test_parse_ranking_html_handles_wayback_machine_url():
    """Wayback Machine のプロキシ URL（ncode.syosetu.com 形式）でも ncode を抽出できる。"""
    html = """<html><body>
    <div class="rank_h">
      <a href="https://web.archive.org/web/20220711/https://ncode.syosetu.com/n4995hm/">タイトル1</a>
    </div>
    <div class="rank_h">
      <a href="https://web.archive.org/web/20220711/https://ncode.syosetu.com/n0753hr/">タイトル2</a>
    </div>
    </body></html>"""
    rows = parse_ranking_html(html, "2022-07-11")
    assert len(rows) == 2
    assert rows[0]["ncode"] == "N4995HM"
    assert rows[1]["ncode"] == "N0753HR"
    assert rows[0]["monthly_rank"] == 1
    assert rows[1]["monthly_rank"] == 2


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


def test_fetch_archive_html_retries_on_ssl_error_then_succeeds():
    """SSL エラー後に成功した場合、HTML が返ることを確認する。"""
    import requests as req

    mock_success = MagicMock()
    mock_success.text = "<html>成功</html>"
    mock_success.raise_for_status = MagicMock()

    side_effects = [req.exceptions.SSLError("SSL エラー"), mock_success]

    with patch("backfill_wayback.requests.get", side_effect=side_effects), \
         patch("backfill_wayback.time.sleep") as mock_sleep:
        result = fetch_archive_html("20240101120000")

    assert result == "<html>成功</html>"
    mock_sleep.assert_called_once()


def test_fetch_archive_html_returns_none_after_max_ssl_retries():
    """SSL エラーが FETCH_RETRY_MAX 回続いた場合に None を返すことを確認する。"""
    import requests as req
    import backfill_wayback

    ssl_error = req.exceptions.SSLError("SSL EOF")

    with patch("backfill_wayback.requests.get", side_effect=ssl_error), \
         patch("backfill_wayback.time.sleep") as mock_sleep:
        result = fetch_archive_html("20240101120000")

    assert result is None
    # FETCH_RETRY_MAX-1 回スリープして最後の試行で終了
    assert mock_sleep.call_count == backfill_wayback.FETCH_RETRY_MAX - 1


# ---------------------------------------------------------------------------
# list_archive_urls — ページネーション
# ---------------------------------------------------------------------------


def test_list_archive_urls_combines_multiple_pages():
    """複数ページのレスポンスを結合することを確認する（limit 件ちょうど返された場合に2回目のリクエストを送る）。"""
    from datetime import date

    # ページ1: 500件ちょうど（ヘッダー + 500行）→ 次ページへ
    # 2020-01-01 から1日ずつ増やして有効なタイムスタンプを生成する
    from datetime import date as _date, timedelta as _td
    base = _date(2020, 1, 1)
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json.return_value = (
        [["timestamp", "original"]]
        + [[(base + _td(days=i)).strftime("%Y%m%d") + "120000", "https://yomou.syosetu.com/"] for i in range(500)]
    )
    # ページ2: 1件（limit 未満）→ 終了
    page2 = MagicMock()
    page2.raise_for_status = MagicMock()
    page2.json.return_value = [
        ["timestamp", "original"],
        ["20241231120000", "https://yomou.syosetu.com/"],
    ]

    mock_get = MagicMock(side_effect=[page1, page2])

    with patch("backfill_wayback.requests.get", mock_get):
        result = list_archive_urls(date(2024, 1, 1), date(2024, 12, 31))

    # 2回リクエストが送られること
    assert mock_get.call_count == 2
    # 合計 501 件（500 + 1）
    assert len(result) == 501
