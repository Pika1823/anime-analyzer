"""
なろうAPI から月刊ランキング TOP1000 を取得して novels.csv を upsert する。
週次実行（月曜のみ）。
"""
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
            "out": "jsonlite",
            "order": "monthlypoint",
            "lim": fetch_count,
            "st": start,
        }
        resp = requests.get(NAROU_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # jsonlite 形式: 先頭要素はメタ情報 {"allcount": N}
        items = data[1:]
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
                "is_anime": ncode in anime_ncodes,
                "anime_id": "",
                "monthly_rank_latest": rank,
                "bookmark_count_latest": item.get("bookmarkcount", 0),
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

    # アニメ化済み作品の ncode セットを構築
    anime_works = load_csv(ANIME_WORKS_CSV)
    anime_ncodes: set[str] = (
        set(anime_works["ncode"].dropna().str.upper())
        if not anime_works.empty
        else set()
    )

    new_df = build_novels_df(raw, anime_ncodes)
    existing = load_csv(NOVELS_CSV, dtype={"ncode": str})
    merged = upsert_novels(existing, new_df)
    save_csv(merged, NOVELS_CSV)
    logger.info("novels.csv 更新完了: %d 件", len(merged))


if __name__ == "__main__":
    main()
