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

from narou_config import GENRE_LABEL, PATTERN1_WEIGHTS
from utils import (
    ANIME_WORKS_CSV,
    ANNICT_WORKS_CSV,
    DAILY_SNAPSHOTS_CSV,
    DOCS_DATA_DIR,
    NORM_PARAMS_JSON,
    NOVELS_CSV,
    TRENDS_CACHE_CSV,
    get_logger,
    load_csv,
)

logger = get_logger(__name__)

# 成長メトリクス計算用定数
GROWTH_PERIODS: list[tuple[int, str]] = [(1, "1d"), (7, "7d"), (30, "30d")]
GROWTH_METRICS_KEYS: list[str] = ["all_hyoka_cnt", "all_point"]

# スコア重みは narou_config.PATTERN1_WEIGHTS を使用（ここではエイリアスとして参照）
DEFAULT_WEIGHTS = PATTERN1_WEIGHTS

# 出力 JSON ファイルパス（GitHub Pages から参照するため docs/data/ に出力）
NOVELS_MERGED_JSON = DOCS_DATA_DIR / "novels_merged.json"
TRENDS_MERGED_JSON = DOCS_DATA_DIR / "trends_merged.json"
SIMILARITY_JSON = DOCS_DATA_DIR / "similarity.json"
SNAPSHOTS_MERGED_JSON = DOCS_DATA_DIR / "snapshots_merged.json"


def get_genre_label(genre_code: str) -> str:
    """ジャンルコードからカテゴリ名を返す。未定義の場合は「その他」を返す。"""
    return GENRE_LABEL.get(str(genre_code), "その他")


def calc_tag_jaccard(tags_a: str, tags_b: str) -> float:
    """タグ文字列の Jaccard 係数を計算する。"""
    set_a = set(str(tags_a).split()) if tags_a and str(tags_a) not in ("nan", "") else set()
    set_b = set(str(tags_b).split()) if tags_b and str(tags_b) not in ("nan", "") else set()
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def calc_rank_score(monthly_rank: int | float | None) -> float:
    """月刊ランクからスコアを計算する。1001以上（ランク外）は 0.0 を返す。"""
    if monthly_rank is None or (isinstance(monthly_rank, float) and math.isnan(monthly_rank)):
        return 0.0
    rank = int(monthly_rank)
    if rank <= 100:
        return 1.0
    if rank <= 300:
        return 0.6
    if rank <= 1000:
        return 0.3
    return 0.0  # 1001以上はランク外


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


# デフォルト正規化パラメータ（norm_params.json が存在しない場合のフォールバック）
DEFAULT_NORM_PARAMS: dict[str, dict[str, float]] = {
    "all_hyoka_cnt_latest":  {"min": 0.0, "max": 30000.0},
    "all_point_latest":      {"min": 0.0, "max": 300000.0},
    "monthly_point_latest":  {"min": 0.0, "max": 10000.0},
    "impression_cnt_latest": {"min": 0.0, "max": 500.0},
}


def calc_norm_score(value: int | float | None, min_val: float, max_val: float) -> float:
    """min-max 正規化でスコアを 0.0〜1.0 の範囲で計算する。

    データセット全体の最小/最大を基準に正規化する。
    max_val <= min_val の場合（全作品が同じ値）は 0.0 を返す。
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    if max_val <= min_val:
        return 0.0
    return min(1.0, max(0.0, (float(value) - min_val) / (max_val - min_val)))


def load_norm_params() -> dict[str, dict[str, float]]:
    """NORM_PARAMS_JSON を読み込む。ファイルが存在しない場合はデフォルト値を返す。

    Returns:
        {列名: {min: float, max: float}} 形式の正規化パラメータ辞書
    """
    if not NORM_PARAMS_JSON.exists():
        logger.info("norm_params.json が存在しません。デフォルトの正規化パラメータを使用します。")
        return dict(DEFAULT_NORM_PARAMS)
    try:
        data = json.loads(NORM_PARAMS_JSON.read_text(encoding="utf-8"))
        params = data.get("params", {})
        # 欠損キーはデフォルト値で補完
        result: dict[str, dict[str, float]] = dict(DEFAULT_NORM_PARAMS)
        for key, val in params.items():
            if isinstance(val, dict) and "min" in val and "max" in val:
                result[key] = {"min": float(val["min"]), "max": float(val["max"])}
        logger.info(
            "norm_params.json 読み込み完了（計算日: %s）",
            data.get("computed_at", "不明"),
        )
        return result
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("norm_params.json の読み込み失敗: %s。デフォルト値を使用します。", e)
        return dict(DEFAULT_NORM_PARAMS)


def calc_eval_score(all_hyoka_cnt: int | float | None) -> float:
    """評価件数スコアを計算する（デフォルト正規化パラメータ使用）。後方互換ラッパー。"""
    p = DEFAULT_NORM_PARAMS["all_hyoka_cnt_latest"]
    return calc_norm_score(all_hyoka_cnt, p["min"], p["max"])


def calc_monthly_point_score(monthly_point: int | float | None) -> float:
    """月間ポイントスコアを計算する（デフォルト正規化パラメータ使用）。後方互換ラッパー。"""
    p = DEFAULT_NORM_PARAMS["monthly_point_latest"]
    return calc_norm_score(monthly_point, p["min"], p["max"])


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
    """スナップショット全体での最高月間ランクを返す（値が小さいほど良い順位）。
    1001以上（ランク外マーカー）は除外して計算する。
    """
    if snapshots.empty or "ncode" not in snapshots.columns:
        return None
    rows = snapshots[
        (snapshots["ncode"] == ncode)
        & snapshots["monthly_rank"].notna()
        & (snapshots["monthly_rank"] < 1001)
    ]
    if rows.empty:
        return None
    return int(rows["monthly_rank"].min())


def calc_growth_metrics(ncode: str, snapshots: pd.DataFrame) -> dict:
    """スナップショットから1日/7日/30日前との差分・増加率を計算する。

    Returns:
        {metric: {period: {delta, rate, base, current}}} 形式の辞書。
        データ不足の場合は delta/rate/base が None になる。
    """
    if snapshots.empty or "ncode" not in snapshots.columns:
        return {}

    novel_snaps = snapshots[snapshots["ncode"] == ncode].copy()
    if novel_snaps.empty:
        return {}

    novel_snaps["date"] = pd.to_datetime(novel_snaps["date"], errors="coerce")
    novel_snaps = novel_snaps.dropna(subset=["date"]).sort_values("date")
    if novel_snaps.empty:
        return {}

    latest_row = novel_snaps.iloc[-1]
    latest_date = latest_row["date"]

    result: dict = {}
    for metric in GROWTH_METRICS_KEYS:
        result[metric] = {}
        current_raw = latest_row.get(metric)
        if current_raw is None or (isinstance(current_raw, float) and math.isnan(current_raw)):
            for _, period_key in GROWTH_PERIODS:
                result[metric][period_key] = {"delta": None, "rate": None, "base": None, "current": None}
            continue

        current_int = int(float(current_raw))

        for days, period_key in GROWTH_PERIODS:
            cutoff = latest_date - pd.Timedelta(days=days)
            past_rows = novel_snaps[novel_snaps["date"] <= cutoff]

            if past_rows.empty:
                result[metric][period_key] = {"delta": None, "rate": None, "base": None, "current": current_int}
                continue

            past_raw = past_rows.iloc[-1].get(metric)
            if past_raw is None or (isinstance(past_raw, float) and math.isnan(past_raw)):
                result[metric][period_key] = {"delta": None, "rate": None, "base": None, "current": current_int}
                continue

            base_int = int(float(past_raw))
            delta = current_int - base_int
            rate = round(delta / base_int * 100, 2) if base_int > 0 else None
            result[metric][period_key] = {
                "delta": delta,
                "rate": rate,
                "base": base_int,
                "current": current_int,
            }

    return result


def calc_view_growth(ncode: str, snapshots: pd.DataFrame) -> float:
    """過去 180 日間の global_point（総合評価ポイント）成長率を計算する。"""
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

    # global_point 列がない場合は旧カラム名 cumulative_view にフォールバック（移行期の互換性）
    point_col = "global_point" if "global_point" in novel_snaps.columns else "cumulative_view"
    oldest = novel_snaps.iloc[0][point_col]
    latest = novel_snaps.iloc[-1][point_col]

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
        DEFAULT_WEIGHTS["genre"]           * genre_score
        + DEFAULT_WEIGHTS["tag"]           * tag_score
        + DEFAULT_WEIGHTS["rank"]          * rank_score
        + DEFAULT_WEIGHTS["bm_view"]       * bm_view_score
        + DEFAULT_WEIGHTS["growth"]        * growth_score
        + DEFAULT_WEIGHTS["eval"]          * eval_score
        + DEFAULT_WEIGHTS["monthly_point"] * monthly_point_score
        + DEFAULT_WEIGHTS["activity"]      * activity_score
    )

    return {
        "anime_id":            anime.get("anime_id", ""),
        "anime_title":         anime.get("anime_title", ""),
        "score":               round(score * 100, 2),  # 0.0〜100.0 スケール
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

    # 正規化パラメータ読み込み（月曜日の fetch_narou.py 実行時に更新される）
    norm_params = load_norm_params()

    # CSV 読み込み
    novels_df = load_csv(NOVELS_CSV)
    anime_df = load_csv(ANIME_WORKS_CSV)
    snapshots_df = load_csv(DAILY_SNAPSHOTS_CSV)
    trends_df = load_csv(TRENDS_CACHE_CSV)
    annict_df = load_csv(ANNICT_WORKS_CSV, dtype={"ncode": str})

    # Annict データを ncode でインデックス化（高速ルックアップ用）
    annict_by_ncode: dict[str, dict] = {}
    if not annict_df.empty:
        for _, ar in annict_df.iterrows():
            ncode_key = str(ar.get("ncode", ""))
            if ncode_key and str(ar.get("is_matched", "")).lower() == "true":
                annict_by_ncode[ncode_key] = ar.to_dict()
    logger.info("Annict データ読み込み: %d 件のマッチ済み作品", len(annict_by_ncode))

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

        # スナップショットから最新 global_point（総合評価ポイント）を取得
        latest_snap = get_latest_snapshot(ncode, snapshots_df)
        global_point_latest: int | None = None
        if latest_snap:
            # global_point 列がない場合は旧カラム名 cumulative_view にフォールバック（移行期の互換性）
            gp_col = "global_point" if "global_point" in latest_snap else "cumulative_view"
            gp = latest_snap.get(gp_col)
            try:
                global_point_latest = int(float(gp)) if gp is not None and not (isinstance(gp, float) and math.isnan(gp)) else None
            except (ValueError, TypeError):
                global_point_latest = None

        # bm_view スコア計算
        bookmark = novel.get("bookmark_count_latest", 0)
        try:
            bookmark_val = float(bookmark) if bookmark is not None else 0.0
        except (ValueError, TypeError):
            bookmark_val = 0.0
        bm_view_score = calc_bm_view_score(bookmark_val, global_point_latest)

        # bm_view_ratio 計算
        if global_point_latest and global_point_latest > 0:
            bm_view_ratio = round(bookmark_val / global_point_latest, 6)
        else:
            bm_view_ratio = None

        # View 成長率計算
        view_growth_6mo = calc_view_growth(ncode, snapshots_df)

        # 成長メトリクス計算（各評価指標の 1日/7日/30日増加量）
        growth_metrics = calc_growth_metrics(ncode, snapshots_df)

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
        eval_score = calc_norm_score(
            all_hyoka_cnt_val,
            norm_params["all_hyoka_cnt_latest"]["min"],
            norm_params["all_hyoka_cnt_latest"]["max"],
        )

        # 過去最高ランク（スナップショットから）
        best_rank_ever = calc_best_rank_ever(ncode, snapshots_df)

        # 月間ポイント・活性スコアを計算
        monthly_point_val = _nan_to_none(novel.get("monthly_point_latest"))
        monthly_point_score = calc_norm_score(
            monthly_point_val,
            norm_params["monthly_point_latest"]["min"],
            norm_params["monthly_point_latest"]["max"],
        )
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

        # Annict 人気度データ（マッチ済みの場合のみ）
        annict_info = annict_by_ncode.get(ncode, {})
        annict_id_val = _nan_to_none(annict_info.get("annict_id")) if annict_info else None
        annict_watchers = _nan_to_none(annict_info.get("watchers_count")) if annict_info else None
        annict_satisfaction = _nan_to_none(annict_info.get("satisfaction_rate")) if annict_info else None
        annict_reviews = _nan_to_none(annict_info.get("reviews_count")) if annict_info else None

        record: dict = {
            "ncode": ncode,
            "title": str(novel.get("title", "")),
            "author": str(novel.get("author", "")),
            "genre": genre_code,
            "genre_label": genre_label,
            "tags": novel_tags,
            "is_anime": is_anime,
            "anime_id": _nan_to_none(novel.get("anime_id")),
            "annict_id": annict_id_val,
            "annict_watchers_count": int(annict_watchers) if annict_watchers is not None else None,
            "annict_satisfaction_rate": float(annict_satisfaction) if annict_satisfaction is not None else None,
            "annict_reviews_count": int(annict_reviews) if annict_reviews is not None else None,
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
            "growth_metrics": growth_metrics,
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
            all_point_snap = _nan_to_none(row.get("all_point"))
            snapshots_by_ncode.setdefault(ncode_val, []).append({
                "date": date_val,
                "monthly_rank": int(rank_val) if rank_val is not None else None,
                "bookmark_count": int(bm_val) if bm_val is not None else None,
                "all_hyoka_cnt": int(float(hyoka_val)) if hyoka_val is not None else None,
                "all_point": int(float(all_point_snap)) if all_point_snap is not None else None,
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
