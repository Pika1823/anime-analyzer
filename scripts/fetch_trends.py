"""
novels.csv と anime_works.csv の全対象について PyTrends で検索トレンドを取得し、
trends_cache.csv に追記する。
週次実行（月曜のみ）。
novels は title を1キーワード、anime_works は title_short と title_full の2キーワードで取得する。
"""
from datetime import date, timedelta

import pandas as pd
from pytrends.request import TrendReq

from utils import (
    ANIME_WORKS_CSV,
    NOVELS_CSV,
    TRENDS_CACHE_CSV,
    get_logger,
    is_weekly_run_day,
    load_csv,
    rate_limit_sleep,
    save_csv,
)

logger = get_logger(__name__)

# 対象地域: 日本
REGION = "JP"
# 取得期間: 直近3ヶ月
TIMEFRAME = "today 3-m"
# この回数連続でエラーが発生したら残りの取得を打ち切る
MAX_CONSECUTIVE_ERRORS = 3


def get_week_start(d: date) -> str:
    """指定日が属する週の月曜日の日付文字列を返す。"""
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def fetch_trend_score(
    pytrends: TrendReq, keyword: str
) -> tuple[dict[str, int], bool]:
    """
    1キーワードのトレンドスコアを取得する。
    失敗しても例外を伝播させず、(空dict, False) を返す。

    Returns:
        (week_start → trend_score の dict, 成功フラグ)
    """
    try:
        pytrends.build_payload([keyword], cat=0, timeframe=TIMEFRAME, geo=REGION)
        df = pytrends.interest_over_time()
        if df.empty or keyword not in df.columns:
            return {}, False
        result = {
            row_date.date().isoformat(): int(score)
            for row_date, score in df[keyword].items()
        }
        return result, True
    except Exception as e:
        logger.warning("キーワード '%s' のトレンド取得失敗: %s", keyword, e)
        return {}, False


def build_trend_rows(
    id_: str,
    id_type: str,
    keyword: str,
    scores: dict[str, int],
    success: bool,
    week_start: str,
) -> list[dict]:
    """
    trends_cache.csv 用の行リストを生成する。
    失敗時は fetch_status='skip' の1行を返す。
    成功時はスコアの週ごとに1行ずつ返す。
    """
    if not success:
        return [{
            "week_start": week_start,
            "id": id_,
            "id_type": id_type,
            "keyword_used": keyword,
            "trend_score": None,
            "fetch_status": "skip",
            "region": REGION,
        }]
    return [{
        "week_start": ws,
        "id": id_,
        "id_type": id_type,
        "keyword_used": keyword,
        "trend_score": score,
        "fetch_status": "ok",
        "region": REGION,
    } for ws, score in scores.items()]


def main() -> None:
    """メイン処理: 週次（月曜のみ）で PyTrends を呼び出し trends_cache.csv に追記する。"""
    if not is_weekly_run_day():
        logger.info("今日は週次実行日（月曜）ではないためスキップ")
        return

    # proxies={} を明示してシステムプロキシをバイパスする（ローカルプロキシが Google をブロックする環境対策）
    pytrends = TrendReq(hl="ja-JP", tz=540, requests_args={"proxies": {}})
    cache = load_csv(TRENDS_CACHE_CSV, dtype={"id": str})

    # 既存キーを (week_start, id, keyword_used) のセットとして保持し重複スキップに使用
    existing_keys: set[tuple[str, str, str]] = set()
    if not cache.empty:
        existing_keys = set(
            zip(cache["week_start"], cache["id"], cache["keyword_used"])
        )

    novels = load_csv(NOVELS_CSV, dtype={"ncode": str})
    anime_works = load_csv(ANIME_WORKS_CSV)
    new_rows: list[dict] = []
    week_start = get_week_start(date.today())

    # 連続エラーが MAX_CONSECUTIVE_ERRORS 回に達したら残り全件をスキップする
    consecutive_errors = 0
    give_up = False

    # novels: title を1キーワードとして使用
    for _, row in novels.iterrows():
        if give_up:
            break
        ncode = str(row["ncode"])
        keyword = str(row["title"])
        if (week_start, ncode, keyword) in existing_keys:
            logger.debug("スキップ（既存）: ncode=%s keyword=%s", ncode, keyword)
            continue
        scores, success = fetch_trend_score(pytrends, keyword)
        if success:
            consecutive_errors = 0
        else:
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.warning(
                    "連続 %d 回エラーのため残りの Trends 取得をスキップします", MAX_CONSECUTIVE_ERRORS
                )
                give_up = True
        new_rows.extend(build_trend_rows(ncode, "novel", keyword, scores, success, week_start=week_start))
        if not give_up:
            rate_limit_sleep()

    # anime_works: title_short と title_full の2キーワードを順番に取得
    for _, row in anime_works.iterrows():
        if give_up:
            break
        anime_id = str(row["anime_id"])
        for keyword in [row.get("title_short", ""), row.get("title_full", "")]:
            if give_up:
                break
            # NaN や空文字はスキップ
            if not keyword or pd.isna(keyword):
                continue
            keyword = str(keyword)
            if (week_start, anime_id, keyword) in existing_keys:
                logger.debug("スキップ（既存）: anime_id=%s keyword=%s", anime_id, keyword)
                continue
            scores, success = fetch_trend_score(pytrends, keyword)
            if success:
                consecutive_errors = 0
            else:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.warning(
                        "連続 %d 回エラーのため残りの Trends 取得をスキップします", MAX_CONSECUTIVE_ERRORS
                    )
                    give_up = True
            new_rows.extend(
                build_trend_rows(anime_id, "anime", keyword, scores, success, week_start=week_start)
            )
            if not give_up:
                rate_limit_sleep()

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        result = (
            pd.concat([cache, new_df], ignore_index=True)
            if not cache.empty
            else new_df
        )
        save_csv(result, TRENDS_CACHE_CSV)
        logger.info("trends_cache.csv に %d 件追記", len(new_rows))
    else:
        logger.info("新規追記なし")


if __name__ == "__main__":
    main()
