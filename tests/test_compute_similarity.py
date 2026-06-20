# test_compute_similarity.py

"""
compute_similarity.py のユニットテスト。
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

# scripts/ ディレクトリを sys.path に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from compute_similarity import (
    calc_bm_view_score,
    calc_best_rank_ever,
    calc_eval_score,
    calc_pattern1_score,
    calc_rank_score,
    calc_tag_jaccard,
    get_genre_label,
)


# --- get_genre_label ---

def test_get_genre_label_known_code():
    """ジャンルコード "101" は "ファンタジー" を返す。"""
    assert get_genre_label("101") == "ファンタジー"


def test_get_genre_label_unknown_code():
    """未定義のジャンルコードは "その他" を返す。"""
    assert get_genre_label("999") == "その他"


# --- calc_tag_jaccard ---

def test_calc_tag_jaccard_empty_both():
    """両方空の場合は 0.0 を返す。"""
    assert calc_tag_jaccard("", "") == 0.0


def test_calc_tag_jaccard_overlap():
    """"転生 異世界" と "転生 魔法" の Jaccard は 1/3 ≈ 0.333。"""
    result = calc_tag_jaccard("転生 異世界", "転生 魔法")
    assert abs(result - 1 / 3) < 1e-9


def test_calc_tag_jaccard_no_overlap():
    """共通タグなしの場合は 0.0 を返す。"""
    assert calc_tag_jaccard("転生", "魔法") == 0.0


# --- calc_rank_score ---

def test_calc_rank_score_top100():
    """ランク 50 は 1.0 を返す。"""
    assert calc_rank_score(50) == 1.0


def test_calc_rank_score_mid_tier():
    """ランク 200 は 0.6 を返す。"""
    assert calc_rank_score(200) == 0.6


def test_calc_rank_score_lower_tier():
    """ランク 500 は 0.3 を返す。"""
    assert calc_rank_score(500) == 0.3


def test_calc_rank_score_none():
    """ランク None は 0.0 を返す。"""
    assert calc_rank_score(None) == 0.0


# --- calc_eval_score ---

def test_calc_eval_score_zero():
    """評価件数 0 は 0.0 を返す。"""
    assert calc_eval_score(0) == 0.0


def test_calc_eval_score_half():
    """評価件数 15000 は 0.5 を返す（30000件で満点）。"""
    assert calc_eval_score(15000) == 0.5


def test_calc_eval_score_max():
    """評価件数 30000 以上は 1.0 を返す。"""
    assert calc_eval_score(30000) == 1.0
    assert calc_eval_score(50000) == 1.0


def test_calc_eval_score_none():
    """評価件数 None は 0.0 を返す。"""
    assert calc_eval_score(None) == 0.0


# --- calc_best_rank_ever ---

def test_calc_best_rank_ever_returns_min():
    """スナップショットの最高ランク（最小値）を返す。"""
    snaps = pd.DataFrame([
        {"ncode": "N001", "monthly_rank": 50},
        {"ncode": "N001", "monthly_rank": 8},
        {"ncode": "N001", "monthly_rank": 25},
    ])
    assert calc_best_rank_ever("N001", snaps) == 8


def test_calc_best_rank_ever_empty_snapshots():
    """スナップショットが空の場合は None を返す。"""
    assert calc_best_rank_ever("N001", pd.DataFrame()) is None


def test_calc_best_rank_ever_ncode_not_found():
    """該当 ncode がない場合は None を返す。"""
    snaps = pd.DataFrame([{"ncode": "N999", "monthly_rank": 10}])
    assert calc_best_rank_ever("N001", snaps) is None


# --- calc_bm_view_score ---

def test_calc_bm_view_score_normal():
    """bookmark=5000, view=100000 → ratio=0.05 → score=1.0。"""
    assert calc_bm_view_score(5000, 100000) == 1.0


def test_calc_bm_view_score_no_view():
    """cumulative_view=None の場合は 0.0 を返す。"""
    assert calc_bm_view_score(5000, None) == 0.0


# --- calc_pattern1_score ---

def _make_anime_series(genre: str = "ファンタジー", tags: str = "転生 異世界") -> pd.Series:
    """テスト用アニメ Series を生成する。"""
    return pd.Series({
        "anime_id": "slime_001",
        "anime_title": "転生したらスライムだった件",
        "genre_manual": genre,
        "tags_manual": tags,
    })


def test_calc_pattern1_score_returns_dict():
    """戻り値が必要なキーをすべて含む辞書であることを確認する。"""
    anime = _make_anime_series()
    result = calc_pattern1_score(
        novel_genre_label="ファンタジー",
        novel_tags="転生 異世界",
        novel_rank=50,
        novel_bm_view_score=0.5,
        novel_growth=0.1,
        novel_eval_score=0.5,
        anime=anime,
    )
    expected_keys = {"anime_id", "anime_title", "score", "genre_score", "tag_score", "rank_score", "bm_view_score", "growth_score", "eval_score"}
    assert expected_keys == set(result.keys())


def test_calc_pattern1_score_genre_match_increases_score():
    """ジャンル一致の場合、スコアに 0.25（genre 重み）が加算される。"""
    anime = _make_anime_series(genre="ファンタジー", tags="")
    match_result = calc_pattern1_score(
        novel_genre_label="ファンタジー",
        novel_tags="",
        novel_rank=None,
        novel_bm_view_score=0.0,
        novel_growth=0.0,
        novel_eval_score=0.0,
        anime=anime,
    )
    nomatch_result = calc_pattern1_score(
        novel_genre_label="恋愛",
        novel_tags="",
        novel_rank=None,
        novel_bm_view_score=0.0,
        novel_growth=0.0,
        novel_eval_score=0.0,
        anime=anime,
    )
    assert abs(match_result["score"] - nomatch_result["score"] - 0.25) < 1e-9


# --- main 統合テスト ---

def _write_csv(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_main_generates_json_files(tmp_path, monkeypatch):
    """DOCS_DATA_DIR を tmp_path に差し替えて main() が 3 つの JSON を生成することを確認する。"""
    import compute_similarity

    monkeypatch.setattr(compute_similarity, "DOCS_DATA_DIR", tmp_path)
    monkeypatch.setattr(compute_similarity, "NOVELS_MERGED_JSON", tmp_path / "novels_merged.json")
    monkeypatch.setattr(compute_similarity, "TRENDS_MERGED_JSON", tmp_path / "trends_merged.json")
    monkeypatch.setattr(compute_similarity, "SIMILARITY_JSON", tmp_path / "similarity.json")

    novels_path = tmp_path / "novels.csv"
    anime_path = tmp_path / "anime_works.csv"
    _write_csv(novels_path, (
        "ncode,title,author,genre,tags,is_anime,anime_id,monthly_rank_latest,bookmark_count_latest,weekly_unique_latest,all_point_latest,all_hyoka_cnt_latest,episode_count_latest,updated_at\n"
        "N0001AA,テスト小説1,著者A,101,転生 異世界,False,,50,1000,5000,2000,300,100,2026-06-01\n"
        "N0002AB,テスト小説2,著者B,101,転生 異世界,True,slime_001,10,5000,10000,5000,800,200,2026-06-01\n"
    ))
    _write_csv(anime_path, (
        "anime_id,anime_title,title_short,title_full,ncode,source_type,air_date,season,studio,genre_manual,tags_manual\n"
        "slime_001,転スラ,転スラ,転生したらスライムだった件,N0002AB,narou,2018-10-02,2018Q4,8-bit,ファンタジー,転生 スライム\n"
    ))

    monkeypatch.setattr(compute_similarity, "NOVELS_CSV", novels_path)
    monkeypatch.setattr(compute_similarity, "ANIME_WORKS_CSV", anime_path)
    monkeypatch.setattr(compute_similarity, "DAILY_SNAPSHOTS_CSV", tmp_path / "daily_snapshots.csv")
    monkeypatch.setattr(compute_similarity, "TRENDS_CACHE_CSV", tmp_path / "trends_cache.csv")

    compute_similarity.main()

    assert (tmp_path / "novels_merged.json").exists()
    assert (tmp_path / "trends_merged.json").exists()
    assert (tmp_path / "similarity.json").exists()

    # novels_merged.json の基本構造を確認
    data = json.loads((tmp_path / "novels_merged.json").read_text(encoding="utf-8"))
    assert "generated_at" in data
    assert len(data["novels"]) == 2
    assert len(data["anime_works"]) == 1

    # similarity.json にはスコアが含まれることを確認
    sim = json.loads((tmp_path / "similarity.json").read_text(encoding="utf-8"))
    assert len(sim["rankings"]) == 1
    assert sim["rankings"][0]["ncode"] == "N0001AA"


def test_main_handles_missing_snapshots(tmp_path, monkeypatch):
    """daily_snapshots.csv が存在しなくてもクラッシュしないことを確認する。"""
    import compute_similarity

    monkeypatch.setattr(compute_similarity, "DOCS_DATA_DIR", tmp_path)
    monkeypatch.setattr(compute_similarity, "NOVELS_MERGED_JSON", tmp_path / "novels_merged.json")
    monkeypatch.setattr(compute_similarity, "TRENDS_MERGED_JSON", tmp_path / "trends_merged.json")
    monkeypatch.setattr(compute_similarity, "SIMILARITY_JSON", tmp_path / "similarity.json")

    novels_path = tmp_path / "novels.csv"
    anime_path = tmp_path / "anime_works.csv"
    _write_csv(novels_path, (
        "ncode,title,author,genre,tags,is_anime,anime_id,monthly_rank_latest,bookmark_count_latest,weekly_unique_latest,all_point_latest,all_hyoka_cnt_latest,episode_count_latest,updated_at\n"
        "N0001AA,テスト小説1,著者A,101,転生 異世界,False,,50,1000,5000,2000,300,100,2026-06-01\n"
    ))
    _write_csv(anime_path, (
        "anime_id,anime_title,title_short,title_full,ncode,source_type,air_date,season,studio,genre_manual,tags_manual\n"
        "slime_001,転スラ,転スラ,転生したらスライムだった件,N0002AB,narou,2018-10-02,2018Q4,8-bit,ファンタジー,転生 スライム\n"
    ))

    monkeypatch.setattr(compute_similarity, "NOVELS_CSV", novels_path)
    monkeypatch.setattr(compute_similarity, "ANIME_WORKS_CSV", anime_path)
    # daily_snapshots.csv は存在しないパスを指定（load_csv が空 DataFrame を返す）
    monkeypatch.setattr(compute_similarity, "DAILY_SNAPSHOTS_CSV", tmp_path / "daily_snapshots.csv")
    monkeypatch.setattr(compute_similarity, "TRENDS_CACHE_CSV", tmp_path / "trends_cache.csv")

    # クラッシュしないことだけを確認
    compute_similarity.main()

    assert (tmp_path / "novels_merged.json").exists()
    assert (tmp_path / "similarity.json").exists()
