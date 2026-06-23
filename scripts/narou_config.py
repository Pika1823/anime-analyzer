"""
なろうAPI・データスキーマ関連の設定を一元管理するファイル。
APIフィールド名・ジャンルコード・CSVカラム名・スコアの重みはすべてここで定義する。
各スクリプトはこのファイルからインポートすること。
"""
from __future__ import annotations

# ============================================================
# なろうAPI ジャンルコード定義
# ============================================================

# サブジャンルコード → ラベルマッピング（なろうAPI の genre フィールド値）
GENRE_LABEL: dict[str, str] = {
    # 恋愛
    "101": "異世界恋愛",
    "102": "現実世界恋愛",
    # ファンタジー
    "201": "ハイファンタジー",
    "202": "ローファンタジー",
    # 文芸
    "301": "純文学",
    "302": "ヒューマンドラマ",
    "303": "歴史",
    "304": "推理",
    "305": "ホラー",
    "306": "アクション",
    "307": "コメディ",
    # SF
    "401": "VRゲーム",
    "402": "宇宙SF",
    "403": "空想科学",
    "404": "パニック",
    # その他
    "9901": "童話",
    "9902": "詩",
    "9903": "エッセイ",
    "9904": "リプレイ",
    "9905": "その他",
    "9999": "ノンジャンル",
}

# 親ジャンルコード → ラベルマッピング（なろうAPI の biggenre フィールド値）
BIGGENRE_LABEL: dict[str, str] = {
    "1": "恋愛",
    "2": "ファンタジー",
    "3": "文芸",
    "4": "SF",
    "98": "その他",
    "99": "ノンジャンル",
}

# ============================================================
# novels.csv カラム定義
# ============================================================

# APIフィールド名 → CSVカラム名 のマッピング
# スクリプト内で別途計算・設定するカラム（is_anime, anime_id, monthly_rank_latest, updated_at）はここに含まない
NOVELS_API_MAP: dict[str, str] = {
    "ncode":           "ncode",
    "title":           "title",
    "writer":          "author",              # API: writer → CSV: author
    "biggenre":        "biggenre",
    "genre":           "genre",
    "keyword":         "tags",                # API: keyword → CSV: tags
    "story":           "story",
    "fav_novel_cnt":   "bookmark_count_latest",
    "weekly_unique":   "weekly_unique_latest",
    "length":          "length",
    "global_point":    "global_point_latest",
    "daily_point":     "daily_point_latest",
    "weekly_point":    "weekly_point_latest",
    "monthly_point":   "monthly_point_latest",
    "all_point":       "all_point_latest",
    "all_hyoka_cnt":   "all_hyoka_cnt_latest",
    "impression_cnt":  "impression_cnt_latest",
    "review_cnt":      "review_cnt_latest",
    "general_all_no":  "episode_count_latest",
    "general_lastup":  "general_lastup",
    "novelupdated_at": "novel_updated_at",
    "istensei":        "is_isekai_tensei",    # 転生要素フラグ (0/1)
    "istenni":         "is_isekai_tenni",     # 転移要素フラグ (0/1)
    "end":             "is_completed",        # 完結フラグ (0=連載中, 1=完結)
}

# ============================================================
# daily_snapshots.csv カラム定義
# ============================================================

# APIフィールド名 → CSVカラム名 のマッピング
# * なろうAPIに累計View数フィールドは存在しない。
#   global_point（総合評価ポイント）をスナップショット追跡の主指標として使用する。
SNAPSHOTS_API_MAP: dict[str, str] = {
    "global_point":   "global_point",    # 総合評価ポイント（旧カラム名: cumulative_view）
    "fav_novel_cnt":  "bookmark_count",
    "weekly_unique":  "weekly_unique",
    "all_point":      "all_point",
    "all_hyoka_cnt":  "all_hyoka_cnt",
    "general_all_no": "episode_count",
}

# ============================================================
# Pattern1 スコア計算の重みパラメータ（仮説ベース。10〜20タイトルで照合しながら調整）
# ============================================================

PATTERN1_WEIGHTS: dict[str, float] = {
    "genre":         0.22,
    "tag":           0.18,
    "rank":          0.17,
    "bm_view":       0.13,
    "growth":        0.08,
    "eval":          0.07,
    "monthly_point": 0.10,
    "activity":      0.05,
}
