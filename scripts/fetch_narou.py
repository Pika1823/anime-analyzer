"""
なろうAPI から月刊ランキング TOP1000 を取得して novels.csv を upsert する。
週次実行（月曜のみ）。
"""
import time
from datetime import date

import pandas as pd
import requests

from utils import (
    ANIME_WORKS_CSV,
    NAROU_API_URL,
    NOVELS_CSV,
    get_logger,
    is_weekly_run_day,
    load_csv,
    save_csv,
)

logger = get_logger(__name__)

# 1リクエストあたりの取得件数上限
NAROU_PAGE_SIZE = 100
# 取得する月刊ランキングの最大件数
NAROU_MAX_COUNT = 1000
# なろうAPI リクエスト時の User-Agent（API 規約上の識別子として送信）
NAROU_USER_AGENT = "anime-analyser/1.0"
# 空レスポンス時のリトライ回数と待機秒数
NAROU_RETRY_COUNT = 3
NAROU_RETRY_WAIT_SEC = 10


def fetch_monthly_top(limit: int = NAROU_MAX_COUNT) -> list[dict]:
    """なろう API から月刊ランキングを取得して返す。

    Args:
        limit: 取得する最大件数。デフォルトは NAROU_MAX_COUNT。

    Returns:
        API レスポンスから取得した小説情報のリスト。
    """
    novels: list[dict] = []
    start = 1

    while len(novels) < limit:
        fetch_count = min(NAROU_PAGE_SIZE, limit - len(novels))
        params = {
            "out": "json",
            "order": "monthlypoint",
            "lim": fetch_count,
            "st": start,
        }
        items = None
        for attempt in range(1, NAROU_RETRY_COUNT + 1):
            try:
                resp = requests.get(
                    NAROU_API_URL,
                    params=params,
                    headers={"User-Agent": NAROU_USER_AGENT},
                    timeout=30,
                )
                resp.raise_for_status()
                if not resp.text.strip():
                    # 空レスポンス: API が一時的に応答しない場合にリトライ
                    logger.warning(
                        "なろうAPI 空レスポンス（ページ %d, 試行 %d/%d）",
                        start, attempt, NAROU_RETRY_COUNT,
                    )
                    if attempt < NAROU_RETRY_COUNT:
                        time.sleep(NAROU_RETRY_WAIT_SEC)
                    continue
                data = resp.json()
                # jsonlite 形式: 先頭要素はメタ情報 {"allcount": N}
                items = data[1:]
                break
            except requests.exceptions.RequestException as e:
                logger.warning("なろうAPI リクエスト失敗（ページ %d, 試行 %d/%d）: %s", start, attempt, NAROU_RETRY_COUNT, e)
                if attempt < NAROU_RETRY_COUNT:
                    time.sleep(NAROU_RETRY_WAIT_SEC)
            except (ValueError, KeyError) as e:
                logger.warning("なろうAPI レスポンス解析失敗（ページ %d）: %s", start, e)
                items = None
                break

        if items is None:
            # 全リトライ失敗
            break
        if not items:
            break

        novels.extend(items)
        start += len(items)
        logger.info("取得済み: %d / %d", len(novels), limit)

    return novels[:limit]


def build_novels_df(raw: list[dict], anime_ncodes: set[str]) -> pd.DataFrame:
    """API レスポンスから novels.csv 用 DataFrame を生成する。

    Args:
        raw: fetch_monthly_top が返す小説情報のリスト。
        anime_ncodes: アニメ化済み作品の ncode セット（大文字）。

    Returns:
        novels.csv のスキーマに合わせた DataFrame。
    """
    today = date.today().isoformat()
    rows = []
    for rank, item in enumerate(raw, start=1):
        ncode = item.get("ncode", "").upper()
        rows.append(
            {
                "ncode": ncode,
                "title": item.get("title", ""),
                "author": item.get("writer", ""),
                "genre": item.get("genre", ""),
                "tags": item.get("keyword", ""),
                "story": item.get("story", ""),
                "is_anime": ncode in anime_ncodes,
                "anime_id": "",
                "monthly_rank_latest": rank,
                "bookmark_count_latest": int(item.get("bookmarkcount") or 0),
                "weekly_unique_latest": int(item.get("weekly_unique") or 0),
                "all_point_latest": int(item.get("all_point") or 0),
                "all_hyoka_cnt_latest": int(item.get("all_hyoka_cnt") or 0),
                "impression_cnt_latest": int(item.get("impressioncnt") or 0),
                "review_cnt_latest": int(item.get("reviewcnt") or 0),
                "episode_count_latest": int(item.get("general_all_no") or 0),
                "updated_at": today,
            }
        )
    return pd.DataFrame(rows)


def upsert_novels(existing: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """ncode をキーに既存データを upsert する。

    - 既存行に一致する ncode があれば新規データで上書きする。
    - 新規データにのみ存在する ncode は追加する。
    - 新規データに含まれない既存行はそのまま保持する。

    Args:
        existing: 既存の novels.csv DataFrame。
        new_df: 今回取得した DataFrame。

    Returns:
        upsert 後の DataFrame（ncode 列をインデックスから戻す）。
    """
    if existing.empty:
        return new_df

    existing_indexed = existing.set_index("ncode")
    new_indexed = new_df.set_index("ncode")

    # 型不一致の列（例: CSV 読み込み時に空文字 → float64 になった anime_id 等）は
    # 両方 object にキャストして update() の TypeError を防ぐ
    for col in existing_indexed.columns.intersection(new_indexed.columns):
        if existing_indexed[col].dtype != new_indexed[col].dtype:
            existing_indexed[col] = existing_indexed[col].astype(object)
            new_indexed[col] = new_indexed[col].astype(object)

    # 既存行を新規データで上書き
    existing_indexed.update(new_indexed)

    # 既存に存在しない新規 ncode を追加
    new_ncodes = new_indexed.index.difference(existing_indexed.index)
    result = pd.concat([existing_indexed, new_indexed.loc[new_ncodes]])

    return result.reset_index()


def main() -> None:
    """エントリポイント: 月曜のみ実行してランキングを取得・保存する。"""
    if not is_weekly_run_day():
        logger.info("今日は週次実行日（月曜）ではないためスキップ")
        return

    logger.info("なろう API から月刊TOP%d を取得開始", NAROU_MAX_COUNT)
    raw = fetch_monthly_top()
    logger.info("取得件数: %d", len(raw))
    if not raw:
        logger.warning("取得件数が0件のため novels.csv の更新をスキップします")
        return

    # アニメ化済み作品の ncode セットを構築
    anime_works = load_csv(ANIME_WORKS_CSV)
    anime_ncodes: set[str] = (
        set(anime_works["ncode"].dropna().str.upper())
        if not anime_works.empty
        else set()
    )

    new_df = build_novels_df(raw, anime_ncodes)
    existing = load_csv(NOVELS_CSV, dtype={"ncode": str})
    merged = upsert_novels(existing, new_df).copy()
    # upsert 後に is_anime を anime_ncodes で再付与（update() による劣化を防ぐ）
    merged["is_anime"] = merged["ncode"].isin(anime_ncodes).astype(bool)
    save_csv(merged, NOVELS_CSV)
    logger.info("novels.csv 更新完了: %d 件", len(merged))


if __name__ == "__main__":
    main()
