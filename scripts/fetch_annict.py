"""
Annict GraphQL API でなろう小説タイトルを検索し、アニメ化判定と人気度データを保存する。
週次実行（月曜のみ）。
"""
from __future__ import annotations

import os
import time
from datetime import date
from difflib import SequenceMatcher

import pandas as pd
import requests

from utils import (
    ANNICT_WORKS_CSV,
    NOVELS_CSV,
    get_logger,
    is_weekly_run_day,
    load_csv,
    save_csv,
)

logger = get_logger(__name__)

# Annict GraphQL エンドポイント
ANNICT_API_URL = "https://api.annict.com/graphql"
# タイトルマッチの閾値（0.0-1.0）: これ以上の類似度をアニメ化済みとみなす
MATCH_THRESHOLD = 0.6
# 1リクエストあたりのスリープ秒数（レート制限対策）
SLEEP_SEC = 1.0
# "未発見" エントリを再検索するまでの日数（アニメ化発表に備えて定期的に再検索する）
REFRESH_DAYS = 30
# 1タイトルあたりの取得候補件数（上位N件から最善マッチを選択する）
SEARCH_FIRST = 5

# タイトル検索 GraphQL クエリ
GRAPHQL_QUERY = """
query SearchWorks($titles: [String!]) {
  searchWorks(
    titles: $titles,
    first: %d,
    orderBy: { field: WATCHERS_COUNT, direction: DESC }
  ) {
    edges {
      node {
        annictId
        title
        titleKana
        watchersCount
        satisfactionRate
        reviewsCount
        episodesCount
        seasonYear
        seasonName
        media
      }
    }
  }
}
""" % SEARCH_FIRST


def calc_title_similarity(title_a: str, title_b: str) -> float:
    """2つのタイトルの文字列類似度を計算する（SequenceMatcher）。"""
    return SequenceMatcher(None, title_a, title_b).ratio()


def search_works(title: str, token: str) -> list[dict]:
    """Annict GraphQL API でタイトルを検索し、候補作品リストを返す。

    Args:
        title: 検索するなろう小説タイトル
        token: Annict アクセストークン

    Returns:
        マッチ候補の作品リスト（最大 SEARCH_FIRST 件）
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": GRAPHQL_QUERY,
        "variables": {"titles": [title]},
    }
    try:
        resp = requests.post(ANNICT_API_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            logger.warning("Annict API エラー（タイトル: %s）: %s", title, data["errors"])
            return []
        edges = data.get("data", {}).get("searchWorks", {}).get("edges", [])
        return [e["node"] for e in edges if e and "node" in e]
    except requests.exceptions.RequestException as e:
        logger.warning("Annict API リクエスト失敗（タイトル: %s）: %s", title, e)
        return []
    except (ValueError, KeyError) as e:
        logger.warning("Annict API レスポンス解析失敗（タイトル: %s）: %s", title, e)
        return []


def find_best_match(query_title: str, candidates: list[dict]) -> tuple[dict | None, float]:
    """候補リストから最も類似度の高い作品を返す。

    Args:
        query_title: 検索したなろうタイトル
        candidates: search_works が返した作品リスト

    Returns:
        (最もマッチした作品 or None, 類似度スコア 0.0-1.0)
    """
    best: dict | None = None
    best_score = 0.0
    for candidate in candidates:
        score = calc_title_similarity(query_title, candidate.get("title", ""))
        if score > best_score:
            best_score = score
            best = candidate
    return best, best_score


def build_annict_row(ncode: str, novel_title: str, match: dict | None, score: float) -> dict:
    """Annict 検索結果から annict_works.csv 用の1行を生成する。

    Args:
        ncode: なろう ncode
        novel_title: なろう小説タイトル
        match: マッチした Annict Work（なければ None）
        score: タイトル類似度スコア

    Returns:
        annict_works.csv の1行分の辞書
    """
    today = date.today().isoformat()
    base = {
        "ncode": ncode,
        "narou_title": novel_title,
        "match_score": round(score, 4),
        "is_matched": False,
        "annict_id": None,
        "annict_title": None,
        "watchers_count": None,
        "satisfaction_rate": None,
        "reviews_count": None,
        "episodes_count": None,
        "season_year": None,
        "season_name": None,
        "media": None,
        "fetched_at": today,
    }
    if match is None or score < MATCH_THRESHOLD:
        return base

    base.update({
        "is_matched": True,
        "annict_id": match.get("annictId"),
        "annict_title": match.get("title"),
        "watchers_count": match.get("watchersCount"),
        "satisfaction_rate": match.get("satisfactionRate"),
        "reviews_count": match.get("reviewsCount"),
        "episodes_count": match.get("episodesCount"),
        "season_year": match.get("seasonYear"),
        "season_name": str(match.get("seasonName") or "").lower() or None,
        "media": str(match.get("media") or "").upper() or None,
    })
    return base


def _should_skip(row: pd.Series, today: date) -> bool:
    """annict_works.csv の既存行を再検索不要と判断するかどうかを返す。

    マッチ済みの行は常にスキップ。未発見の行は REFRESH_DAYS 日経過後に再検索する。
    """
    is_matched = str(row.get("is_matched", "")).lower() == "true"
    if is_matched:
        return True
    fetched_raw = row.get("fetched_at")
    if pd.isna(fetched_raw):
        return False
    try:
        fetched_date = pd.to_datetime(fetched_raw).date()
        return (today - fetched_date).days < REFRESH_DAYS
    except (ValueError, TypeError):
        return False


def fetch_annict_data(novels_df: pd.DataFrame, token: str, existing: pd.DataFrame) -> pd.DataFrame:
    """novels.csv の各作品を Annict で検索し、結果を DataFrame で返す。

    Args:
        novels_df: novels.csv の DataFrame
        token: Annict アクセストークン
        existing: 既存の annict_works.csv DataFrame（空でも可）

    Returns:
        新規検索結果の DataFrame（スキップ対象は含まない）
    """
    today = date.today()
    skip_ncodes: set[str] = set()
    if not existing.empty:
        for _, row in existing.iterrows():
            if _should_skip(row, today):
                skip_ncodes.add(str(row["ncode"]))

    new_rows: list[dict] = []
    total = len(novels_df)
    searched = 0
    for i, (_, novel_row) in enumerate(novels_df.iterrows()):
        ncode = str(novel_row.get("ncode", ""))
        title = str(novel_row.get("title", ""))
        if not ncode or not title or title == "nan":
            continue
        if ncode in skip_ncodes:
            continue

        logger.info("[%d/%d] Annict 検索: %s (%s)", i + 1, total, title, ncode)
        candidates = search_works(title, token)
        best, score = find_best_match(title, candidates)
        row = build_annict_row(ncode, title, best, score)
        new_rows.append(row)
        searched += 1

        if row["is_matched"]:
            logger.info("  → マッチ: %s (スコア: %.3f)", row["annict_title"], score)

        time.sleep(SLEEP_SEC)

    logger.info("検索完了: %d 件中 %d 件を新規検索", total, searched)
    return pd.DataFrame(new_rows) if new_rows else pd.DataFrame()


def upsert_annict_works(existing: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """ncode をキーに annict_works.csv を upsert する。

    Args:
        existing: 既存の annict_works.csv DataFrame
        new_df: 今回の検索結果 DataFrame

    Returns:
        upsert 後の DataFrame
    """
    if new_df.empty:
        return existing
    if existing.empty:
        return new_df

    existing_idx = existing.set_index("ncode")
    new_idx = new_df.set_index("ncode")

    # 型不一致による update() エラーを防ぐ
    for col in existing_idx.columns.intersection(new_idx.columns):
        if existing_idx[col].dtype != new_idx[col].dtype:
            existing_idx[col] = existing_idx[col].astype(object)
            new_idx[col] = new_idx[col].astype(object)

    existing_idx.update(new_idx)
    new_only = new_idx.index.difference(existing_idx.index)
    return pd.concat([existing_idx, new_idx.loc[new_only]]).reset_index()


def update_novels_is_anime(novels_df: pd.DataFrame, annict_df: pd.DataFrame) -> pd.DataFrame:
    """annict_works.csv のマッチ結果を使って novels.csv の is_anime を更新する。

    is_anime を True に設定するのみ（False への変更は行わない）。

    Args:
        novels_df: novels.csv の DataFrame
        annict_df: annict_works.csv の全 DataFrame

    Returns:
        is_anime を更新した novels DataFrame
    """
    if annict_df.empty:
        return novels_df

    # "True" / True 両方を処理する
    matched_ncodes: set[str] = set(
        annict_df[annict_df["is_matched"].astype(str).str.lower() == "true"]["ncode"]
        .dropna()
        .astype(str)
    )
    if not matched_ncodes:
        return novels_df

    novels_df = novels_df.copy()
    before = novels_df["is_anime"].astype(str).str.lower().eq("true").sum()
    novels_df["is_anime"] = novels_df.apply(
        lambda r: True if str(r["ncode"]) in matched_ncodes else r["is_anime"],
        axis=1,
    )
    after = novels_df["is_anime"].astype(str).str.lower().eq("true").sum()
    logger.info(
        "is_anime 更新: %d 件 → %d 件（Annict マッチで %d 件追加）",
        before, after, after - before,
    )
    return novels_df


def main() -> None:
    """エントリポイント: 週次（月曜）実行。"""
    if not is_weekly_run_day():
        logger.info("今日は週次実行日（月曜）ではないためスキップ")
        return

    token = os.environ.get("ANNICT_API_KEY", "")
    if not token:
        logger.error("ANNICT_API_KEY が設定されていません。スクリプトを終了します。")
        return

    novels_df = load_csv(NOVELS_CSV, dtype={"ncode": str})
    if novels_df.empty:
        logger.warning("novels.csv が空または存在しません。スキップします。")
        return

    existing = load_csv(ANNICT_WORKS_CSV, dtype={"ncode": str})
    logger.info("Annict 検索開始: 対象 %d 件", len(novels_df))

    new_df = fetch_annict_data(novels_df, token, existing)

    merged = upsert_annict_works(existing, new_df)
    if not new_df.empty:
        save_csv(merged, ANNICT_WORKS_CSV)
        logger.info("annict_works.csv 保存完了: %d 件", len(merged))
    else:
        logger.info("新規検索なし。annict_works.csv の更新をスキップ。")

    # novels.csv の is_anime を Annict マッチ結果で更新
    if not merged.empty:
        novels_df = update_novels_is_anime(novels_df, merged)
        save_csv(novels_df, NOVELS_CSV)
        logger.info("novels.csv is_anime 更新完了")


if __name__ == "__main__":
    main()
