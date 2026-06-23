from __future__ import annotations

import logging
import os
import random
import time
from datetime import date
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
DOCS_DATA_DIR = ROOT_DIR / "docs" / "data"

NOVELS_CSV = DATA_DIR / "novels.csv"
ANIME_WORKS_CSV = DATA_DIR / "anime_works.csv"
DAILY_SNAPSHOTS_CSV = DATA_DIR / "daily_snapshots.csv"
TRENDS_CACHE_CSV = DATA_DIR / "trends_cache.csv"
ANNICT_WORKS_CSV = DATA_DIR / "annict_works.csv"

NAROU_API_URL = "https://api.syosetu.com/novelapi/api/"

RATE_LIMIT_SLEEP_MIN = 30
RATE_LIMIT_SLEEP_MAX = 60


def get_logger(name: str) -> logging.Logger:
    """標準ロガーを生成して返す。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(name)


def rate_limit_sleep() -> None:
    """PyTrends のレート制限回避のためランダムスリープする。"""
    duration = random.uniform(RATE_LIMIT_SLEEP_MIN, RATE_LIMIT_SLEEP_MAX)
    time.sleep(duration)


def is_weekly_run_day(weekday: int = 0) -> bool:
    """今日が指定曜日（デフォルト: 月曜=0）かどうかを返す。
    環境変数 FORCE_RUN=true が設定されている場合は曜日にかかわらず True を返す。
    """
    if os.environ.get("FORCE_RUN", "").lower() == "true":
        return True
    return date.today().weekday() == weekday


def load_csv(path: Path, dtype: dict | None = None) -> pd.DataFrame:
    """CSV を読み込む。ファイルが存在しない場合は空の DataFrame を返す。"""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=dtype)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    """DataFrame を CSV に保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
