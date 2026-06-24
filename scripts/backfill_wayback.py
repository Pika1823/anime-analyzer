"""
Wayback Machine CDX API でなろうランキングページのアーカイブを取得し、
daily_snapshots.csv に過去のランキング順位データを補完する。
初回のみ手動実行。
"""
from __future__ import annotations

import argparse
import re
import time
from datetime import date, datetime, timedelta

import pandas as pd
import requests
from bs4 import BeautifulSoup

from utils import DAILY_SNAPSHOTS_CSV, get_logger, load_csv, save_csv

logger = get_logger(__name__)

CDX_API_URL = "https://web.archive.org/cdx/search/cdx"
NAROU_RANKING_URL = "https://yomou.syosetu.com/rank/list/type/monthly_total/"
# アーカイブ取得後のスリープ秒数（Wayback Machine のレート制限対策）
WAYBACK_SLEEP_SEC = 5
# リトライ設定（503/429 等の一時エラー用）
FETCH_RETRY_MAX = 5
FETCH_RETRY_SLEEP_BASE = 30  # CDX API 用の初期待機秒数（503 多発のため長めに設定）
HTML_RETRY_SLEEP_BASE = 10   # アーカイブ HTML 取得用の初期待機秒数
# 一時エラーとみなすHTTPステータスコード（リトライ対象）
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _request_with_retry(
    url: str,
    params: dict | None = None,
    sleep_base: int = FETCH_RETRY_SLEEP_BASE,
    max_retry: int = FETCH_RETRY_MAX,
    label: str = "",
) -> requests.Response | None:
    """HTTP GET を実行し、一時エラー時は指数バックオフでリトライする。
    最大リトライ回数を超えた場合は None を返す（致命エラーにしない）。
    """
    for attempt in range(max_retry):
        try:
            resp = requests.get(url, params=params, timeout=60)
            if resp.status_code in RETRYABLE_STATUS:
                wait = sleep_base * (2 ** attempt)
                logger.warning(
                    "%s HTTP %d (試行 %d/%d)、%d 秒後リトライ",
                    label or url[:60], resp.status_code, attempt + 1, max_retry, wait,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.SSLError as e:
            wait = sleep_base * (2 ** attempt)
            if attempt < max_retry - 1:
                logger.warning(
                    "%s SSL エラー (試行 %d/%d)、%d 秒後リトライ: %s",
                    label or url[:60], attempt + 1, max_retry, wait, e,
                )
                time.sleep(wait)
            else:
                logger.warning("%s SSL エラー（リトライ上限）: %s", label or url[:60], e)
                return None
        except requests.exceptions.RequestException as e:
            logger.warning("%s リクエストエラー: %s", label or url[:60], e)
            return None
    logger.warning("%s リトライ上限到達、スキップ", label or url[:60])
    return None


def list_archive_urls(start: date, end: date) -> list[dict]:
    """Wayback Machine CDX API でアーカイブ URL 一覧を取得する。
    503 等の一時エラーはリトライし、失敗した場合は空リストを返す。
    """
    results: list[dict] = []
    params: dict = {
        "url": NAROU_RANKING_URL,
        "output": "json",
        "fl": "timestamp,original",
        "from": start.strftime("%Y%m%d"),
        "to": end.strftime("%Y%m%d"),
        "collapse": "timestamp:8",  # 1日1件に絞る
        "limit": 500,
    }
    while True:
        resp = _request_with_retry(
            CDX_API_URL,
            params=params,
            sleep_base=FETCH_RETRY_SLEEP_BASE,
            label="CDX API",
        )
        if resp is None:
            logger.warning("CDX API の取得に失敗しました。部分的な結果 %d 件で続行します", len(results))
            break
        try:
            data = resp.json()
        except ValueError:
            logger.warning("CDX API レスポンスが JSON でありません、終了します")
            break
        if not isinstance(data, list) or len(data) <= 1:
            break
        # 先頭行はヘッダー ["timestamp", "original"]（または resumeKey 行）
        rows = data[1:]
        if not rows:
            break
        # 通常のデータ行を追加
        results.extend(
            {"timestamp": row[0], "original": row[1]}
            for row in rows
            if len(row) >= 2
        )
        # 取得件数が limit 未満なら最終ページ
        if len(rows) < params["limit"]:
            break
        # 最終タイムスタンプの1秒後から次ページを取得（from は inclusive のため重複回避）
        last_ts = rows[-1][0]
        try:
            last_dt = datetime.strptime(last_ts, "%Y%m%d%H%M%S")
            last_dt = last_dt + timedelta(seconds=1)
            params = dict(params)
            params["from"] = last_dt.strftime("%Y%m%d%H%M%S")
        except ValueError:
            logger.warning("タイムスタンプのパース失敗: %s、ページネーションを終了", last_ts)
            break
        time.sleep(2)  # ページ間のレート制限対策
    logger.info("アーカイブ一覧取得完了: %d 件", len(results))
    return results


def fetch_archive_html(timestamp: str) -> str | None:
    """Wayback Machine からアーカイブ HTML を取得する。503/SSL エラー時は指数バックオフでリトライ。"""
    url = f"https://web.archive.org/web/{timestamp}/{NAROU_RANKING_URL}"
    resp = _request_with_retry(
        url,
        sleep_base=HTML_RETRY_SLEEP_BASE,
        label=f"アーカイブ timestamp={timestamp}",
    )
    if resp is None:
        return None
    return resp.text


def parse_ranking_html(html: str, snapshot_date: str) -> list[dict]:
    """なろうランキング HTML をパースしてランキングデータを抽出する。

    Wayback Machine はリンクを自プロキシ URL でラップするため、
    ncode.syosetu.com/NCODE/ 形式と /novel/NCODE/ 形式の両方に対応する。
    """
    soup = BeautifulSoup(html, "lxml")
    items = soup.select("div.rank_h") or soup.select("li.rank_h")
    hrefs: list[str] = []
    for item in items:
        # Wayback Machine ではプロキシ URL に ncode.syosetu.com が含まれる
        link = item.select_one("a[href*='ncode.syosetu.com']") or item.select_one("a[href*='/novel/']")
        if link:
            hrefs.append(link.get("href", ""))

    rows: list[dict] = []
    for rank, href in enumerate(hrefs, start=1):
        # ncode.syosetu.com/NCODE/ 形式（Wayback Machine ラップ済み URL）
        match = re.search(r"ncode\.syosetu\.com/([A-Za-z0-9]+)/", href)
        # /novel/NCODE/ 形式（ローカルテスト等）
        if not match:
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
