"""
なろうAPI から月刊ランキング TOP1000 を取得して novels.csv を upsert する。
週次実行（月曜のみ）。
"""
import json
import os
import time
from datetime import date, datetime
from difflib import SequenceMatcher

import pandas as pd
import requests

from narou_config import NOVELS_API_MAP  # noqa: F401（APIフィールド名の参照用）
from utils import (
    ANIME_WORKS_CSV,
    NAROU_API_URL,
    NORM_PARAMS_JSON,
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
# 作品タイプフィルター（環境変数 NAROU_NOVEL_TYPE で上書き可能）
# 空文字=すべて / "t"=短編 / "r"=連載中 / "er"=完結済連載 / "re"=すべての連載 / "ter"=短編+完結済
NAROU_NOVEL_TYPE: str = os.environ.get("NAROU_NOVEL_TYPE", "")

# anime_works.csv の ncode 未設定エントリに対してタイトルマッチで ncode を特定する際の類似度閾値
ANIME_TITLE_MATCH_THRESHOLD = 0.7

# 正規化パラメータ（min/max）を計算する novels.csv の列名一覧
NORM_METRICS: list[str] = [
    "all_hyoka_cnt_latest",
    "all_point_latest",
    "monthly_point_latest",
    "impression_cnt_latest",
]


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
        if NAROU_NOVEL_TYPE:
            params["type"] = NAROU_NOVEL_TYPE
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


def _unix_to_iso(ts) -> str:
    """Unix タイムスタンプを ISO 8601 文字列に変換する。0 や None は空文字を返す。"""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts)).isoformat()
    except (ValueError, OSError):
        return ""


def compute_and_save_norm_params(novels_df: pd.DataFrame) -> None:
    """novels.csv の各指標の min/max を計算して norm_params.json に保存する。

    compute_similarity.py がこのファイルを読み込み、データセット全体に対する
    min-max 正規化スコアを算出するために使用する。

    Args:
        novels_df: novels.csv の DataFrame
    """
    logger.info("正規化パラメータの計算開始")
    params: dict[str, dict[str, float]] = {}
    for col in NORM_METRICS:
        if col not in novels_df.columns:
            params[col] = {"min": 0.0, "max": 1.0}
            logger.warning("正規化対象列が見つかりません（フォールバック使用）: %s", col)
            continue
        valid = pd.to_numeric(novels_df[col], errors="coerce").dropna()
        if valid.empty:
            params[col] = {"min": 0.0, "max": 1.0}
            continue
        min_val = float(valid.min())
        max_val = float(valid.max())
        # min == max の場合はゼロ除算を防ぐため max を +1.0 する
        params[col] = {"min": min_val, "max": max_val if max_val > min_val else min_val + 1.0}
        logger.info("  %s: min=%.1f, max=%.1f", col, min_val, max_val)

    result = {
        "computed_at": date.today().isoformat(),
        "params": params,
    }
    NORM_PARAMS_JSON.parent.mkdir(parents=True, exist_ok=True)
    NORM_PARAMS_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("norm_params.json 保存完了: %s", NORM_PARAMS_JSON)


def find_anime_ncodes_by_title(anime_works: pd.DataFrame, novels_df: pd.DataFrame) -> set[str]:
    """anime_works.csv の source_type=narou で ncode 未設定の作品をタイトルマッチで novels.csv から検索する。

    ncode が登録済みの作品は既に anime_ncodes に含まれるためスキップ。
    類似度が ANIME_TITLE_MATCH_THRESHOLD 以上のものを is_anime=True 対象として返す。

    Args:
        anime_works: anime_works.csv の DataFrame
        novels_df: novels.csv の DataFrame

    Returns:
        タイトルマッチで特定したアニメ化済み作品の ncode セット
    """
    if anime_works.empty or novels_df.empty:
        return set()

    # ncode なしの narou 原作アニメタイトルリストを構築
    no_ncode_mask = (
        anime_works["source_type"].str.lower() == "narou"
    ) & (
        anime_works["ncode"].isna() | (anime_works["ncode"].str.strip() == "")
    )
    anime_titles = anime_works.loc[no_ncode_mask, "anime_title"].dropna().tolist()

    if not anime_titles:
        return set()

    novel_titles = novels_df["title"].tolist()
    novel_ncodes = novels_df["ncode"].tolist()
    matched_ncodes: set[str] = set()

    for anime_title in anime_titles:
        best_ncode: str | None = None
        best_score = 0.0
        for novel_title, novel_ncode in zip(novel_titles, novel_ncodes):
            score = SequenceMatcher(None, str(anime_title), str(novel_title)).ratio()
            if score > best_score:
                best_score = score
                best_ncode = str(novel_ncode)
        if best_score >= ANIME_TITLE_MATCH_THRESHOLD and best_ncode:
            matched_ncodes.add(best_ncode)
            logger.info(
                "タイトルマッチ（ncode補完）: '%s' → ncode=%s (スコア=%.3f)",
                anime_title, best_ncode, best_score,
            )

    logger.info("タイトルマッチによる追加アニメ化作品: %d 件", len(matched_ncodes))
    return matched_ncodes


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
                "biggenre": item.get("biggenre", ""),
                "genre": item.get("genre", ""),
                "tags": item.get("keyword", ""),
                "story": item.get("story", ""),
                "is_anime": ncode in anime_ncodes,
                "anime_id": "",
                "monthly_rank_latest": rank,
                "bookmark_count_latest": int(item.get("fav_novel_cnt") or 0),
                "weekly_unique_latest": int(item.get("weekly_unique") or 0),
                "length": int(item.get("length") or 0),
                "global_point_latest": int(item.get("global_point") or 0),
                "daily_point_latest": int(item.get("daily_point") or 0),
                "weekly_point_latest": int(item.get("weekly_point") or 0),
                "monthly_point_latest": int(item.get("monthly_point") or 0),
                "all_point_latest": int(item.get("all_point") or 0),
                "all_hyoka_cnt_latest": int(item.get("all_hyoka_cnt") or 0),
                "impression_cnt_latest": int(item.get("impression_cnt") or 0),
                "review_cnt_latest": int(item.get("review_cnt") or 0),
                "episode_count_latest": int(item.get("general_all_no") or 0),
                "is_isekai_tensei": int(item.get("istensei") or 0),
                "is_isekai_tenni": int(item.get("istenni") or 0),
                "is_completed": int(item.get("end") or 0),
                "general_lastup": _unix_to_iso(item.get("general_lastup")),
                "novel_updated_at": _unix_to_iso(item.get("novelupdated_at")),
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

    # upsert 後に is_anime を再付与（update() による劣化を防ぐ）
    # ncode 未設定の narou 原作アニメをタイトルマッチで補完して合算する
    title_matched_ncodes = find_anime_ncodes_by_title(anime_works, merged)
    all_anime_ncodes = anime_ncodes | title_matched_ncodes
    merged["is_anime"] = merged["ncode"].isin(all_anime_ncodes).astype(bool)
    # 今週のランキングに含まれていない作品の月刊順位をランク外（None）にリセット
    new_ncodes_set = set(new_df["ncode"])
    merged.loc[~merged["ncode"].isin(new_ncodes_set), "monthly_rank_latest"] = None
    save_csv(merged, NOVELS_CSV)
    logger.info("novels.csv 更新完了: %d 件", len(merged))

    # 正規化パラメータを計算・保存（compute_similarity.py が参照する）
    compute_and_save_norm_params(merged)


if __name__ == "__main__":
    main()
