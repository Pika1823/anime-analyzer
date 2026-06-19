"""
novels.csv の全 ncode を対象に日次スナップショットを取得して daily_snapshots.csv に追記する。
毎日実行。
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests

from utils import (
    DAILY_SNAPSHOTS_CSV,
    NAROU_API_URL,
    NOVELS_CSV,
    get_logger,
    load_csv,
    save_csv,
)

logger = get_logger(__name__)


def fetch_novel_snapshot(ncode: str) -> dict | None:
    """なろう API で特定作品のスナップショットを取得する。"""
    params = {
        "out": "json",
        "ncode": ncode,
        "lim": 1,
    }
    try:
        resp = requests.get(NAROU_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # 先頭はメタ情報なので2番目の要素を取得
        if len(data) < 2:
            return None
        return data[1]
    except Exception as e:
        logger.warning("ncode=%s のスナップショット取得失敗: %s", ncode, e)
        return None


def calc_daily_view(
    ncode: str,
    cumulative_view: int,
    snapshots: pd.DataFrame,
    today: date,
) -> int | None:
    """
    前日の累計 view と現在の累計 view の差分を計算して日次 view を返す。

    前日データが存在しない場合、または前日の cumulative_view が NaN の場合は None を返す。
    """
    if snapshots.empty:
        return None

    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    # 対象 ncode かつ前日のレコードを絞り込む
    mask = (snapshots["ncode"] == ncode) & (snapshots["date"] == yesterday_str)
    prev_rows = snapshots[mask]

    if prev_rows.empty:
        return None

    prev_cumulative = prev_rows.iloc[-1]["cumulative_view"]

    # NaN チェック
    try:
        if pd.isna(prev_cumulative):
            return None
    except (TypeError, ValueError):
        return None

    result = int(cumulative_view) - int(prev_cumulative)
    # 累計 view の減少（データ補正等）による負値を 0 にクランプする
    return max(result, 0)


def main() -> None:
    """novels.csv の全 ncode を対象に日次スナップショットを取得して追記する。"""
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    novels = load_csv(NOVELS_CSV, dtype={"ncode": str})
    if novels.empty:
        logger.warning("novels.csv が空またはファイルが存在しません")
        return

    snapshots = load_csv(DAILY_SNAPSHOTS_CSV, dtype={"ncode": str})
    new_rows: list[dict] = []

    for _, row in novels.iterrows():
        ncode = str(row["ncode"])

        # 同日・同 ncode が既存ならスキップ（冪等）
        if not snapshots.empty:
            already_exists = (
                (snapshots["ncode"] == ncode) & (snapshots["date"] == today_str)
            ).any()
            if already_exists:
                logger.debug("ncode=%s の本日分は取得済みのためスキップ", ncode)
                continue

        detail = fetch_novel_snapshot(ncode)
        if detail is None:
            continue

        # out=json では累積View数が取得できないため global_point を代替指標として使用
        cumulative_view = detail.get("global_point")
        if cumulative_view is None:
            logger.warning("ncode=%s: global_point フィールドが存在しないためスキップ", ncode)
            continue

        daily_view = calc_daily_view(ncode, cumulative_view, snapshots, today)

        new_rows.append({
            "date": today_str,
            "ncode": ncode,
            "cumulative_view": cumulative_view,
            "daily_view": daily_view,
            "bookmark_count": detail.get("bookmarkcount", 0),
            "monthly_rank": row.get("monthly_rank_latest"),
            "weekly_rank": None,
            "weekly_unique": detail.get("weekly_unique"),
            "all_point": detail.get("all_point"),
            "all_hyoka_cnt": detail.get("all_hyoka_cnt"),
            "episode_count": detail.get("general_all_no"),
        })

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
