# compute_similarity.py

"""
アニメ化済み作品との類似度スコアを計算し、JSON ファイルを出力するスクリプト。
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

# scripts/ ディレクトリを sys.path に追加して utils をインポートできるようにする
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    ANIME_WORKS_CSV,
    DAILY_SNAPSHOTS_CSV,
    DOCS_DATA_DIR,
    NOVELS_CSV,
    TRENDS_CACHE_CSV,
    get_logger,
    load_csv,
)

logger = get_logger(__name__)

# なろうジャンルコード → カテゴリ名マッピング
NAROU_GENRE_CATEGORY: dict[str, str] = {
    "101": "ファンタジー",
    "102": "ファンタジー",
    "201": "恋愛",
    "202": "恋愛",
    "301": "SF",
    "302": "SF",
    "303": "SF",
    "304": "SF",
    "307": "SF",
    "401": "文芸",
    "402": "文芸",
    "403": "文芸",
    "404": "文芸",
    "405": "文芸",
    "406": "文芸",
    "407": "文芸",
    "408": "文芸",
    "409": "文芸",
    "410": "文芸",
    "411": "文芸",
    "9999": "ノンジャンル",
}

# Pattern1 スコア計算の重みパラメータ（仮説ベース）
DEFAULT_WEIGHTS: dict[str, float] = {
    "genre":         0.25,
    "tag":           0.20,
    "rank":          0.20,
    "bm_view":       0.15,
    "growth":        0.10,
    "eval":          0.10,
    "monthly_point": 0.0,   # 月間ポイントスコア（データ取得後に調整）
    "activity":      0.0,   # 活性スコア（最終更新日ベース）
}

# 出力 JSON ファイルパス（GitHub Pages から参照するため docs/data/ に出力）
NOVELS_MERGED_JSON = DOCS_DATA_DIR / "novels_merged.json"
TRENDS_MERGED_JSON = DOCS_DATA_DIR / "trends_merged.json"
SIMILARITY_JSON = DOCS_DATA_DIR / "similarity.json"
SNAPSHOTS_MERGED_JSON = DOCS_DATA_DIR / "snapshots_merged.json"


def get_genre_label(genre_code: str) -> str:
    """ジャンルコードからカテゴリ名を返す。未定義の場合は「その他」を返す。"""
    return NAROU_GENRE_CATEGORY.get(str(genre_code), "その他")


def calc_tag_jaccard(tags_a: str, tags_b: str) -> float:
    """タグ文字列の Jaccard 係数を計算する。"""
    set_a = set(str(tags_a).split()) if tags_a and str(tags_a) not in ("nan", "") else set()
    set_b = set(str(tags_b).split()) if tags_b and str(tags_b) not in ("nan", "") else set()
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def calc_rank_score(monthly_rank: int | float | None) -> float:
    """月刊ランクからスコアを計算する。"""
    if monthly_rank is None or (isinstance(monthly_rank, float) and math.isnan(monthly_rank)):
        return 0.0
    rank = int(monthly_rank)
    if rank <= 100:
        return 1.0
    if rank <= 300:
        return 0.6
    return 0.3


def calc_bm_view_score(bookmark: int | float, cumulative_view: int | float | None) -> float:
    """ブックマーク数と累計 View 数からスコアを計算する。"""
    if cumulative_view is None:
        return 0.0
    if isinstance(cumulative_view, float) and math.isnan(cumulative_view):
        return 0.0
    if cumulative_view == 0:
        return 0.0
    ratio = float(bookmark) / float(cumulative_view)
    return min(1.0, ratio / 0.05)


EVAL_SCORE_MAX_CNT: float = 30000.0   # 評価件数スコアの満点閾値
MONTHLY_POINT_MAX: float = 10000.0   # 月間ポイントスコアの満点閾値（要チューニング）

def calc_eval_score(all_hyoka_cnt: int | float | None) -> float:
    """評価件数スコアを計算する（30000件で満点）。"""
    if all_hyoka_cnt is None or (isinstance(all_hyoka_cnt, float) and math.isnan(all_hyoka_cnt)):
        return 0.0
    return min(1.0, float(all_hyoka_cnt) / EVAL_SCORE_MAX_CNT)


def calc_monthly_point_score(monthly_point: int | float | None) -> float:
    """月間ポイントスコアを計算する（MONTHLY_POINT_MAX で満点）。"""
    if monthly_point is None or (isinstance(monthly_point, float) and math.isnan(monthly_point)):
        return 0.0
    return min(1.0, float(monthly_point) / MONTHLY_POINT_MAX)


def calc_activity_score(general_lastup: str | None) -> float:
    """最終掲載日からの経過日数で活性スコアを計算する。
    30日以内=1.0 / 90日=0.7 / 180日=0.4 / 365日=0.1 / 365日超=0.0 / データなし=0.5
    """
    if not general_lastup or str(general_lastup) in ("", "nan"):
        return 0.5
    try:
        lastup_dt = datetime.fromisoformat(str(general_lastup))
        days = (date.today() - lastup_dt.date()).days
        if days <= 30:
            return 1.0
        if days <= 90:
            return 0.7
        if days <= 180:
            return 0.4
        if days <= 365:
            return 0.1
        return 0.0
    except (ValueError, AttributeError):
        return 0.5


def calc_best_rank_ever(ncode: str, snapshots: pd.DataFrame) -> int | None:
    """スナップショット全体での最高月間ランクを返す（値が小さいほど良い順位）。"""
    if snapshots.empty or "ncode" not in snapshots.columns:
        return None
    rows = snapshots[
        (snapshots["ncode"] == ncode) & snapshots["monthly_rank"].notna()
    ]
    if rows.empty:
        return None
    return int(rows["monthly_rank"].min())


def calc_view_growth(ncode: str, snapshots: pd.DataFrame) -> float:
    """過去 180 日間の累計 View 数成長率を計算する。"""
    if snapshots.empty or "ncode" not in snapshots.columns:
        return 0.0

    cutoff = date.today() - timedelta(days=180)
    novel_snaps = snapshots[snapshots["ncode"] == ncode].copy()
    if novel_snaps.empty:
        return 0.0

    # date 列を datetime 型に変換してフィルタリング
    novel_snaps["date"] = pd.to_datetime(novel_snaps["date"], errors="coerce")
    novel_snaps = novel_snaps.dropna(subset=["date"])
    novel_snaps = novel_snaps[novel_snaps["date"].dt.date >= cutoff]
    novel_snaps = novel_snaps.sort_values("date")

    if len(novel_snaps) < 2:
        return 0.0

    oldest = novel_snaps.iloc[0]["cumulative_view"]
    latest = novel_snaps.iloc[-1]["cumulative_view"]

    try:
        oldest_val = float(oldest)
        latest_val = float(latest)
    except (ValueError, TypeError):
        return 0.0

    if oldest_val <= 0:
        return 0.0

    growth = (latest_val - oldest_val) / oldest_val
    return min(1.0, max(0.0, growth))


def get_latest_snapshot(ncode: str, snapshots: pd.DataFrame) -> dict | None:
    """指定 ncode の最新スナップショットを辞書で返す。データがない場合は None を返す。"""
    if snapshots.empty or "ncode" not in snapshots.columns:
        return None

    novel_snaps = snapshots[snapshots["ncode"] == ncode].copy()
    if novel_snaps.empty:
        return None

    novel_snaps["date"] = pd.to_datetime(novel_snaps["date"], errors="coerce")
    novel_snaps = novel_snaps.dropna(subset=["date"])
    if novel_snaps.empty:
        return None

    latest_row = novel_snaps.sort_values("date").iloc[-1]
    return latest_row.to_dict()


def calc_pattern1_score(
    novel_genre_label: str,
    novel_tags: str,
    novel_rank: int | float | None,
    novel_bm_view_score: float,
    novel_growth: float,
    novel_eval_score: float,
    anime: pd.Series,
    novel_monthly_point_score: float = 0.0,
    novel_activity_score: float = 0.5,
) -> dict:
    """Pattern1 スコアを計算する。各コンポーネントスコアと合計スコアを辞書で返す。"""
    genre_score    = 1.0 if novel_genre_label == str(anime.get("genre_manual", "")) else 0.0
    tag_score      = calc_tag_jaccard(novel_tags, str(anime.get("tags_manual", "")))
    rank_score     = calc_rank_score(novel_rank)
    bm_view_score  = novel_bm_view_score
    growth_score   = novel_growth
    eval_score     = novel_eval_score
    monthly_point_score = novel_monthly_point_score
    activity_score = novel_activity_score

    score = (
        DEFAULT_WEIGHTS["genre"]         * genre_score
        + DEFAULT_WEIGHTS["tag"]         * tag_score
        + DEFAULT_WEIGHTS["rank"]        * rank_score
        + DEFAULT_WEIGHTS["bm_view"]     * bm_view_score
        + DEFAULT_WEIGHTS["growth"]      * growth_score
        + DEFAULT_WEIGHTS["eval"]        * eval_score
        + DEFAULT_WEIGHTS["monthly_point"] * monthly_point_score
        + DEFAULT_WEIGHTS["activity"]    * activity_score
    )

    return {
        "anime_id":            anime.get("anime_id", ""),
        "anime_title":         anime.get("anime_title", ""),
        "score":               round(score, 4),
        "genre_score":         round(genre_score, 4),
        "tag_score":           round(tag_score, 4),
        "rank_score":          round(rank_score, 4),
        "bm_view_score":       round(bm_view_score, 4),
        "growth_score":        round(growth_score, 4),
        "eval_score":          round(eval_score, 4),
        "monthly_point_score": round(monthly_point_score, 4),
        "activity_score":      round(activity_score, 4),
    }


def _nan_to_none(value: object) -> object:
    """pandas の NaN を None に変換する。"""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def main() -> None:
    """メイン処理: CSV を読み込み、類似度スコアを計算し、JSON ファイルを出力する。"""
    logger.info("compute_similarity.py 開始")

    # CSV 読み込み
    novels_df = load_csv(NOVELS_CSV)
    anime_df = load_csv(ANIME_WORKS_CSV)
    snapshots_df = load_csv(DAILY_SNAPSHOTS_CSV)
    trends_df = load_csv(TRENDS_CACHE_CSV)

    if novels_df.empty:
        logger.error("novels.csv が空またはファイルが存在しません。処理を中断します。")
        return

    if anime_df.empty:
        logger.error("anime_works.csv が空またはファイルが存在しません。処理を中断します。")
        return

    # なろう原作アニメのみ対象
    narou_anime_df = anime_df[anime_df["source_type"] == "narou"].copy()
    logger.info(f"なろう原作アニメ数: {len(narou_anime_df)}")

    today_str = date.today().isoformat()
    novel_records = []

    for _, novel in novels_df.iterrows():
        ncode = str(novel.get("ncode", ""))
        is_anime = str(novel.get("is_anime", "False")).lower() == "true"

        # スナップショットから最新累計 View 数を取得
        latest_snap = get_latest_snapshot(ncode, snapshots_df)
        cumulative_view_latest: int | None = None
        if latest_snap and "cumulative_view" in latest_snap:
            cv = latest_snap["cumulative_view"]
            try:
                cumulative_view_latest = int(float(cv)) if cv is not None and not (isinstance(cv, float) and math.isnan(cv)) else None
            except (ValueError, TypeError):
                cumulative_view_latest = None

        # bm_view スコア計算
        bookmark = novel.get("bookmark_count_latest", 0)
        try:
            bookmark_val = float(bookmark) if bookmark is not None else 0.0
        except (ValueError, TypeError):
            bookmark_val = 0.0
        bm_view_score = calc_bm_view_score(bookmark_val, cumulative_view_latest)

        # bm_view_ratio 計算
        if cumulative_view_latest and cumulative_view_latest > 0:
            bm_view_ratio = round(bookmark_val / cumulative_view_latest, 6)
        else:
            bm_view_ratio = None

        # View 成長率計算
        view_growth_6mo = calc_view_growth(ncode, snapshots_df)

        genre_code = str(novel.get("genre", ""))
        genre_label = get_genre_label(genre_code)
        novel_tags = str(novel.get("tags", "")) if not (isinstance(novel.get("tags"), float) and math.isnan(novel.get("tags"))) else ""
        monthly_rank = _nan_to_none(novel.get("monthly_rank_latest"))

        # 評価件数スコア計算（スナップショット優先、なければ novels.csv）
        all_hyoka_cnt_from_snap = None
        if latest_snap and "all_hyoka_cnt" in latest_snap:
            ahc = latest_snap.get("all_hyoka_cnt")
            if ahc is not None and not (isinstance(ahc, float) and math.isnan(ahc)):
                try:
                    all_hyoka_cnt_from_snap = int(float(ahc))
                except (ValueError, TypeError):
                    pass
        all_hyoka_cnt_val = all_hyoka_cnt_from_snap if all_hyoka_cnt_from_snap is not None else _nan_to_none(novel.get("all_hyoka_cnt_latest"))
        eval_score = calc_eval_score(all_hyoka_cnt_val)

        # 過去最高ランク（スナップショットから）
        best_rank_ever = calc_best_rank_ever(ncode, snapshots_df)

        # 月間ポイント・活性スコアを計算
        monthly_point_val = _nan_to_none(novel.get("monthly_point_latest"))
        monthly_point_score = calc_monthly_point_score(monthly_point_val)
        general_lastup_val = novel.get("general_lastup", "")
        if isinstance(general_lastup_val, float) and math.isnan(general_lastup_val):
            general_lastup_val = ""
        activity_score_val = calc_activity_score(str(general_lastup_val) if general_lastup_val else "")

        # Pattern1 スコアを計算（アニメ作品の場合は自身の anime_id を除外して比較）
        pattern1_scores: list[dict] = []
        if not narou_anime_df.empty:
            own_anime_id = str(novel.get("anime_id", "")) if is_anime else ""
            candidates = (
                narou_anime_df[narou_anime_df["anime_id"] != own_anime_id]
                if is_anime and own_anime_id
                else narou_anime_df
            )
            for _, anime_row in candidates.iterrows():
                score_dict = calc_pattern1_score(
                    novel_genre_label=genre_label,
                    novel_tags=novel_tags,
                    novel_rank=monthly_rank,
                    novel_bm_view_score=bm_view_score,
                    novel_growth=view_growth_6mo,
                    novel_eval_score=eval_score,
                    anime=anime_row,
                    novel_monthly_point_score=monthly_point_score,
                    novel_activity_score=activity_score_val,
                )
                pattern1_scores.append(score_dict)

            pattern1_scores.sort(key=lambda x: x["score"], reverse=True)

        pattern1_best_score = pattern1_scores[0]["score"] if pattern1_scores else None
        pattern1_best_anime_id = pattern1_scores[0]["anime_id"] if pattern1_scores else None

        record: dict = {
            "ncode": ncode,
            "title": str(novel.get("title", "")),
            "author": str(novel.get("author", "")),
            "genre": genre_code,
            "genre_label": genre_label,
            "tags": novel_tags,
            "is_anime": is_anime,
            "anime_id": _nan_to_none(novel.get("anime_id")),
            "monthly_rank_latest": _nan_to_none(monthly_rank),
            "bookmark_count_latest": _nan_to_none(novel.get("bookmark_count_latest")),
            "weekly_unique_latest": _nan_to_none(novel.get("weekly_unique_latest")),
            "length": _nan_to_none(novel.get("length")),
            "global_point_latest": _nan_to_none(novel.get("global_point_latest")),
            "daily_point_latest": _nan_to_none(novel.get("daily_point_latest")),
            "weekly_point_latest": _nan_to_none(novel.get("weekly_point_latest")),
            "monthly_point_latest": _nan_to_none(novel.get("monthly_point_latest")),
            "all_point_latest": _nan_to_none(novel.get("all_point_latest")),
            "all_hyoka_cnt_latest": _nan_to_none(all_hyoka_cnt_val),
            "impression_cnt_latest": _nan_to_none(novel.get("impression_cnt_latest")),
            "review_cnt_latest": _nan_to_none(novel.get("review_cnt_latest")),
            "episode_count_latest": _nan_to_none(novel.get("episode_count_latest")),
            "general_lastup": str(novel.get("general_lastup", "")) if not (isinstance(novel.get("general_lastup"), float) and math.isnan(novel.get("general_lastup"))) else "",
            "novel_updated_at": str(novel.get("novel_updated_at", "")) if not (isinstance(novel.get("novel_updated_at"), float) and math.isnan(novel.get("novel_updated_at"))) else "",
            "story": str(novel.get("story", "")) if not (isinstance(novel.get("story"), float) and math.isnan(novel.get("story"))) else "",
            "best_rank_ever": best_rank_ever,
            "updated_at": str(novel.get("updated_at", "")),
            "cumulative_view_latest": cumulative_view_latest,
            "bm_view_ratio": bm_view_ratio,
            "view_growth_6mo": round(view_growth_6mo, 4),
            "eval_score": round(eval_score, 4),
            "pattern1_best_score": pattern1_best_score,
            "pattern1_best_anime_id": pattern1_best_anime_id,
            "pattern1_scores": pattern1_scores,
        }
        novel_records.append(record)

    # anime_works レコードを構築
    anime_records = []
    for _, anime_row in anime_df.iterrows():
        anime_records.append({
            "anime_id": str(anime_row.get("anime_id", "")),
            "anime_title": str(anime_row.get("anime_title", "")),
            "source_type": str(anime_row.get("source_type", "")),
            "air_date": _nan_to_none(anime_row.get("air_date")),
            "genre_manual": _nan_to_none(anime_row.get("genre_manual")),
            "tags_manual": _nan_to_none(anime_row.get("tags_manual")),
        })

    # novels_merged.json 出力
    novels_merged = {
        "generated_at": today_str,
        "novels": novel_records,
        "anime_works": anime_records,
    }
    NOVELS_MERGED_JSON.parent.mkdir(parents=True, exist_ok=True)
    NOVELS_MERGED_JSON.write_text(
        json.dumps(novels_merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"novels_merged.json を出力しました: {NOVELS_MERGED_JSON}")

    # trends_merged.json 出力
    trends_novels: dict[str, list] = {}
    trends_anime: dict[str, list] = {}

    if not trends_df.empty and "id_type" in trends_df.columns:
        for _, row in trends_df.iterrows():
            id_type = str(row.get("id_type", ""))
            id_val = str(row.get("id", ""))
            week_start = str(row.get("week_start", ""))
            score = _nan_to_none(row.get("trend_score"))
            status = str(row.get("fetch_status", ""))

            entry = {"week_start": week_start, "score": score, "status": status}
            if id_type == "novel":
                trends_novels.setdefault(id_val, []).append(entry)
            elif id_type == "anime":
                trends_anime.setdefault(id_val, []).append(entry)

    trends_merged = {
        "generated_at": today_str,
        "novels": trends_novels,
        "anime": trends_anime,
    }
    TRENDS_MERGED_JSON.write_text(
        json.dumps(trends_merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"trends_merged.json を出力しました: {TRENDS_MERGED_JSON}")

    # similarity.json 出力（未アニメ化 + アニメ化済み全作品、スコア降順）
    unadapted_with_score = [
        {
            "ncode": r["ncode"],
            "title": r["title"],
            "is_anime": r["is_anime"],
            "monthly_rank_latest": r["monthly_rank_latest"],
            "best_rank_ever": r["best_rank_ever"],
            "eval_score": r["eval_score"],
            "all_hyoka_cnt_latest": r["all_hyoka_cnt_latest"],
            "genre_score": (r["pattern1_scores"][0].get("genre_score", 0) if r["pattern1_scores"] else 0),
            "tag_score": (r["pattern1_scores"][0].get("tag_score", 0) if r["pattern1_scores"] else 0),
            "rank_score": (r["pattern1_scores"][0].get("rank_score", 0) if r["pattern1_scores"] else 0),
            "bm_view_score": (r["pattern1_scores"][0].get("bm_view_score", 0) if r["pattern1_scores"] else 0),
            "growth_score": (r["pattern1_scores"][0].get("growth_score", 0) if r["pattern1_scores"] else 0),
            "pattern1_best_score": r["pattern1_best_score"],
            "pattern1_best_anime_id": r["pattern1_best_anime_id"],
            "pattern1_scores": r["pattern1_scores"],
        }
        for r in novel_records
        if r["pattern1_best_score"] is not None
    ]
    unadapted_with_score.sort(key=lambda x: x["pattern1_best_score"] or 0, reverse=True)

    similarity = {
        "generated_at": today_str,
        "rankings": unadapted_with_score,
    }
    SIMILARITY_JSON.write_text(
        json.dumps(similarity, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"similarity.json を出力しました: {SIMILARITY_JSON}")

    # snapshots_merged.json 出力（ランキング推移グラフ用）
    snapshots_by_ncode: dict[str, list] = {}
    if not snapshots_df.empty and "monthly_rank" in snapshots_df.columns:
        snap_sorted = snapshots_df.sort_values("date")
        for _, row in snap_sorted.iterrows():
            ncode_val = str(row.get("ncode", ""))
            date_val = str(row.get("date", ""))
            rank_val = _nan_to_none(row.get("monthly_rank"))
            bm_val = _nan_to_none(row.get("bookmark_count"))
            if not ncode_val or not date_val:
                continue
            hyoka_val = _nan_to_none(row.get("all_hyoka_cnt"))
            snapshots_by_ncode.setdefault(ncode_val, []).append({
                "date": date_val,
                "monthly_rank": int(rank_val) if rank_val is not None else None,
                "bookmark_count": int(bm_val) if bm_val is not None else None,
                "all_hyoka_cnt": int(float(hyoka_val)) if hyoka_val is not None else None,
            })

    snapshots_merged = {
        "generated_at": today_str,
        "snapshots": snapshots_by_ncode,
    }
    SNAPSHOTS_MERGED_JSON.write_text(
        json.dumps(snapshots_merged, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"snapshots_merged.json を出力しました: {SNAPSHOTS_MERGED_JSON}")

    # サマリーログ
    total = len(novel_records)
    unadapted_count = sum(1 for r in novel_records if not r["is_anime"])
    logger.info(f"処理完了: 総小説数={total}, 未アニメ化={unadapted_count}, ランキング件数={len(unadapted_with_score)}")


if __name__ == "__main__":
    main()
