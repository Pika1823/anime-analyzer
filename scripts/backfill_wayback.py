"""
Wayback Machine CDX API でなろうランキングページのアーカイブを取得し、
daily_snapshots.csv に過去のランキング順位データを補完する。
初回のみ手動実行。
"""
import argparse
import re
import time
from datetime import date, timedelta

import pandas as pd
import requests

from utils import DAILY_SNAPSHOTS_CSV, get_logger, load_csv, save_csv

try:
    from bs4 import BeautifulSoup as _BS4
    _HAS_BS4 = True
except ImportError:  # noqa: BLE001
    _HAS_BS4 = False

logger = get_logger(__name__)

CDX_API_URL = "http://web.archive.org/cdx/search/cdx"
NAROU_RANKING_URL = "https://yomou.syosetu.com/rank/list/type/monthly_total/"
# アーカイブ取得後のスリープ秒数（Wayback Machine のレート制限対策）
WAYBACK_SLEEP_SEC = 3


def list_archive_urls(start: date, end: date) -> list[dict]:
    """Wayback Machine CDX API でアーカイブ URL 一覧を取得する。"""
    params = {
        "url": NAROU_RANKING_URL,
        "output": "json",
        "fl": "timestamp,original",
        "from": start.strftime("%Y%m%d"),
        "to": end.strftime("%Y%m%d"),
        "collapse": "timestamp:8",  # 1日1件に絞る
        "limit": 500,
    }
    resp = requests.get(CDX_API_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if len(data) <= 1:
        # ヘッダー行のみ（該当なし）
        return []
    # 先頭行はヘッダー ["timestamp", "original"]
    return [{"timestamp": row[0], "original": row[1]} for row in data[1:]]


def fetch_archive_html(timestamp: str) -> str | None:
    """Wayback Machine からアーカイブ HTML を取得する。"""
    url = f"http://web.archive.org/web/{timestamp}/{NAROU_RANKING_URL}"
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("アーカイブ取得失敗 timestamp=%s: %s", timestamp, e)
        return None


def _extract_ncode_hrefs_bs4(html: str) -> list[str]:
    """BeautifulSoup を使って rank_h 要素内の /novel/NCODE/ href を抽出する。"""
    soup = _BS4(html, "lxml")
    hrefs: list[str] = []
    items = soup.select("div.rank_h") or soup.select("li.rank_h")
    for item in items:
        link = item.select_one("a[href*='/novel/']")
        if link:
            hrefs.append(link.get("href", ""))
    return hrefs


def _extract_ncode_hrefs_regex(html: str) -> list[str]:
    """bs4 が使えない場合の正規表現フォールバック実装。"""
    # rank_h ブロック内の /novel/NCODE/ パターンを抽出する
    # 例: <div class="rank_h"><a href="/novel/N1234AB/">...
    block_pattern = re.compile(
        r'class=["\']rank_h["\'][^>]*>.*?</(?:div|li)>', re.DOTALL
    )
    href_pattern = re.compile(r'href=["\'](/novel/[A-Za-z0-9]+/)["\']')
    hrefs: list[str] = []
    for block in block_pattern.finditer(html):
        m = href_pattern.search(block.group())
        if m:
            hrefs.append(m.group(1))
    return hrefs


def parse_ranking_html(html: str, snapshot_date: str) -> list[dict]:
    """なろうランキング HTML をパースしてランキングデータを抽出する。"""
    if _HAS_BS4:
        hrefs = _extract_ncode_hrefs_bs4(html)
    else:
        # bs4 未インストール環境（テスト環境等）では正規表現で代替
        hrefs = _extract_ncode_hrefs_regex(html)

    rows: list[dict] = []
    for rank, href in enumerate(hrefs, start=1):
        match = re.search(r"/novel/([A-Za-z0-9]+)/", href)
        if not match:
            continue
        ncode = match.group(1).upper()
        rows.append({
            "date": snapshot_date,
            "ncode": ncode,
            "cumulative_view": None,
            "daily_view": None,
            "bookmark_count": None,
            "monthly_rank": rank,
            "weekly_rank": None,
        })
    return rows


def main() -> None:
    """コマンドライン引数を解析して Wayback Machine からデータを補完する。"""
    parser = argparse.ArgumentParser(
        description="Wayback Machine から過去のなろうランキングデータを補完する"
    )
    default_start = (date.today() - timedelta(days=365 * 3)).isoformat()
    default_end = date.today().isoformat()
    parser.add_argument("--start", default=default_start, help="取得開始日 (YYYY-MM-DD)")
    parser.add_argument("--end", default=default_end, help="取得終了日 (YYYY-MM-DD)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    logger.info("Wayback Machine アーカイブ一覧取得: %s 〜 %s", start, end)
    archives = list_archive_urls(start, end)
    logger.info("対象アーカイブ件数: %d", len(archives))

    snapshots = load_csv(DAILY_SNAPSHOTS_CSV, dtype={"ncode": str})
    existing_keys: set[tuple[str, str]] = set()
    if not snapshots.empty:
        existing_keys = set(zip(snapshots["date"], snapshots["ncode"]))

    new_rows: list[dict] = []
    for archive in archives:
        timestamp = archive["timestamp"]
        # タイムスタンプ (YYYYMMDDHHmmss) から日付文字列を生成
        snapshot_date = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"

        html = fetch_archive_html(timestamp)
        if html is None:
            continue

        for row in parse_ranking_html(html, snapshot_date):
            key = (row["date"], row["ncode"])
            if key in existing_keys:
                # 同日・同 ncode は重複スキップ（冪等）
                continue
            new_rows.append(row)
            existing_keys.add(key)

        time.sleep(WAYBACK_SLEEP_SEC)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        result = (
            pd.concat([snapshots, new_df], ignore_index=True)
            if not snapshots.empty
            else new_df
        )
        save_csv(result, DAILY_SNAPSHOTS_CSV)
        logger.info("daily_snapshots.csv に %d 件追記", len(new_rows))
    else:
        logger.info("新規追記なし")


if __name__ == "__main__":
    main()
