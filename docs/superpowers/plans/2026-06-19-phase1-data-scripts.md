# フェーズ1 データ基盤スクリプト 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** なろう小説アニメ化分析ツールのデータ収集スクリプト群（4本）と共通ユーティリティを TDD で実装し、`python scripts/xxx.py` で単体実行できる状態にする。

**Architecture:** 各スクリプトは独立して実行可能で、共通処理は `scripts/utils.py` に集約する。CSVファイルへの読み書きはすべて utils.py 経由で行い、各スクリプトはビジネスロジックのみを持つ。テストは `tests/` に配置し、pytest で実行する。

**Tech Stack:** Python 3.11、pandas 2.0+、requests 2.31+、pytrends 4.9+、beautifulsoup4 4.12+、lxml 4.9+、pytest

## Global Constraints

- Python 3.11 以上を使用すること
- コードのコメントとエラーログは日本語で記述すること
- ハードコーディングは避け、定数は utils.py に集約すること
- 各スクリプトは `python scripts/xxx.py` で単体実行できること
- 失敗時はスクリプトを止めず `fetch_status=skip` で記録して継続すること（特に fetch_trends.py）
- すべてのファイルパスは `DATA_DIR` 定数を通じて参照すること
- 主キー `(week_start, id, keyword_used)` で trends_cache.csv の重複チェックを行うこと

---

### Task 1: プロジェクトセットアップ（requirements.txt + anime_works.csv + テスト基盤）

**Files:**
- Create: `scripts/requirements.txt`
- Create: `data/anime_works.csv`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: `tests/conftest.py` に `scripts/` を sys.path に追加する `conftest` — 全テストファイルが `from utils import ...` 等で scripts 配下をインポートできる

- [ ] **Step 1: requirements.txt を作成する**

```
# scripts/requirements.txt
requests>=2.31.0
pandas>=2.0.0
pytrends>=4.9.2
beautifulsoup4>=4.12.0
lxml>=4.9.0
pytest>=7.4.0
```

- [ ] **Step 2: anime_works.csv を作成する**

ファイルパス: `data/anime_works.csv`

```csv
anime_id,anime_title,title_short,title_full,ncode,source_type,air_date,season,studio,genre_manual,tags_manual
slime_001,転生したらスライムだった件,転スラ,転生したらスライムだった件,N6316BN,narou,2018-10-02,2018Q4,8-bit,ファンタジー,転生 スライム 異世界 無双
rezero_001,Re:ゼロから始める異世界生活,リゼロ,Re:ゼロから始める異世界生活,N2267BE,narou,2016-04-04,2016Q2,WHITE FOX,ファンタジー,異世界 ループ 転生 死に戻り
mushoku_001,無職転生 〜異世界行ったら本気だす〜,無職転生,無職転生 〜異世界行ったら本気だす〜,N9669BK,narou,2021-01-11,2021Q1,スタジオバインド,ファンタジー,転生 異世界 魔法 成長
overlord_001,オーバーロード,オバロ,オーバーロード,N9468BK,narou,2015-07-07,2015Q3,マドハウス,ファンタジー,転生 ゲーム 骸骨 異世界
honzuki_001,本好きの下剋上,本好き,本好きの下剋上〜司書になるためには手段を選んでいられません〜,N4830BU,narou,2019-10-02,2019Q4,亜細亜堂,ファンタジー,転生 書物 成り上がり
kage_001,陰の実力者になりたくて！,陰実,陰の実力者になりたくて！,N0525HT,narou,2023-01-05,2023Q1,Nexus,ファンタジー,チート 異世界 主人公最強
kumo_001,蜘蛛ですが、何か？,蜘蛛,蜘蛛ですが、何か？,N7973BK,narou,2021-01-08,2021Q1,ミルパンセ,ファンタジー,転生 クモ 異世界 成長
hitoribocchi_001,ひとりぼっちの異世界攻略,ひとりぼっち,ひとりぼっちの異世界攻略,,narou,,,,,異世界 攻略
spyfamily_001,SPY×FAMILY,スパイファミリー,SPY×FAMILY,,other,2022-04-09,2022Q2,WIT STUDIO / CloverWorks,アクション,スパイ ファミリー コメディ
shingeki_001,進撃の巨人,進撃,進撃の巨人,,other,2013-04-07,2013Q2,WIT STUDIO,アクション,巨人 ダーク ファンタジー
chainsaw_001,チェンソーマン,チェンソーマン,チェンソーマン,,other,2022-10-11,2022Q4,MAPPA,アクション,デビルハンター ダーク
jujutsu_001,呪術廻戦,呪術,呪術廻戦,,other,2020-10-03,2020Q4,MAPPA,アクション,呪術 バトル
kimetsu_001,鬼滅の刃,鬼滅,鬼滅の刃,,other,2019-04-06,2019Q2,ufotable,アクション,鬼 剣士 大正
```

> **注意**: `source_type=narou` の ncode は概算値です。`fetch_narou.py` 初回実行後に正確な ncode を確認して修正してください。`ひとりぼっちの異世界攻略` の ncode は未確認のため空欄にしています。

- [ ] **Step 3: テスト基盤ファイルを作成する**

`tests/__init__.py`:
```python
```

`tests/conftest.py`:
```python
import sys
from pathlib import Path

# テストから scripts/ 配下のモジュールをインポートできるようにする
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
```

- [ ] **Step 4: pip install で動作確認する**

```bash
pip install -r scripts/requirements.txt
```

期待出力: `Successfully installed ...` （エラーなく完了）

- [ ] **Step 5: コミット**

```bash
git add scripts/requirements.txt data/anime_works.csv tests/__init__.py tests/conftest.py
git commit -m "feat: プロジェクトセットアップ（requirements.txt・anime_works.csv初期データ・テスト基盤）"
```

---

### Task 2: utils.py（共通ユーティリティ）

**Files:**
- Create: `scripts/utils.py`
- Create: `tests/test_utils.py`

**Interfaces:**
- Produces:
  - `DATA_DIR: Path` — data/ ディレクトリへの絶対パス
  - `NOVELS_CSV: Path`, `ANIME_WORKS_CSV: Path`, `DAILY_SNAPSHOTS_CSV: Path`, `TRENDS_CACHE_CSV: Path`
  - `NAROU_API_URL: str`
  - `get_logger(name: str) -> logging.Logger`
  - `rate_limit_sleep() -> None` — 30〜60秒ランダムスリープ
  - `is_weekly_run_day(weekday: int = 0) -> bool`
  - `load_csv(path: Path, dtype: dict | None = None) -> pd.DataFrame`
  - `save_csv(df: pd.DataFrame, path: Path) -> None`

- [ ] **Step 1: テストを書く**

`tests/test_utils.py`:
```python
from pathlib import Path
from datetime import date
from unittest.mock import patch
import pandas as pd
import pytest
from utils import get_logger, is_weekly_run_day, load_csv, save_csv


def test_get_logger_returns_named_logger():
    logger = get_logger("test_module")
    assert logger.name == "test_module"


def test_is_weekly_run_day_returns_true_on_monday():
    # date.today() が月曜（weekday=0）を返すようにモック
    with patch("utils.date") as mock_date:
        mock_date.today.return_value.weekday.return_value = 0
        assert is_weekly_run_day() is True


def test_is_weekly_run_day_returns_false_on_wednesday():
    with patch("utils.date") as mock_date:
        mock_date.today.return_value.weekday.return_value = 2
        assert is_weekly_run_day() is False


def test_is_weekly_run_day_custom_weekday():
    with patch("utils.date") as mock_date:
        mock_date.today.return_value.weekday.return_value = 3  # 木曜
        assert is_weekly_run_day(weekday=3) is True
        assert is_weekly_run_day(weekday=0) is False


def test_load_csv_returns_empty_df_when_file_missing(tmp_path):
    result = load_csv(tmp_path / "missing.csv")
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_save_and_load_csv_roundtrip(tmp_path):
    df = pd.DataFrame({"ncode": ["N001", "N002"], "title": ["A", "B"]})
    path = tmp_path / "test.csv"
    save_csv(df, path)
    loaded = load_csv(path)
    pd.testing.assert_frame_equal(df, loaded)


def test_save_csv_creates_parent_directory(tmp_path):
    df = pd.DataFrame({"a": [1]})
    path = tmp_path / "subdir" / "nested.csv"
    save_csv(df, path)
    assert path.exists()
```

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
pytest tests/test_utils.py -v
```

期待出力: `ModuleNotFoundError: No module named 'utils'` または `FAILED`

- [ ] **Step 3: utils.py を実装する**

`scripts/utils.py`:
```python
import logging
import random
import time
from datetime import date
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"

NOVELS_CSV = DATA_DIR / "novels.csv"
ANIME_WORKS_CSV = DATA_DIR / "anime_works.csv"
DAILY_SNAPSHOTS_CSV = DATA_DIR / "daily_snapshots.csv"
TRENDS_CACHE_CSV = DATA_DIR / "trends_cache.csv"

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
    """今日が指定曜日（デフォルト: 月曜=0）かどうかを返す。"""
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
```

- [ ] **Step 4: テストを実行して全て通ることを確認する**

```bash
pytest tests/test_utils.py -v
```

期待出力: `7 passed`

- [ ] **Step 5: コミット**

```bash
git add scripts/utils.py tests/test_utils.py
git commit -m "feat: utils.py — 共通ユーティリティ（ロガー・CSV読み書き・週次チェック・スリープ）"
```

---

### Task 3: fetch_narou.py（週次・なろうAPI → novels.csv upsert）

**Files:**
- Create: `scripts/fetch_narou.py`
- Create: `tests/test_fetch_narou.py`

**Interfaces:**
- Consumes: `utils.ANIME_WORKS_CSV`, `utils.NOVELS_CSV`, `utils.NAROU_API_URL`, `utils.get_logger`, `utils.is_weekly_run_day`, `utils.load_csv`, `utils.save_csv`
- Produces:
  - `fetch_monthly_top(limit: int = 1000) -> list[dict]`
  - `build_novels_df(raw: list[dict], anime_ncodes: set[str]) -> pd.DataFrame`
  - `upsert_novels(existing: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame`

- [ ] **Step 1: テストを書く**

`tests/test_fetch_narou.py`:
```python
import pandas as pd
import pytest
from fetch_narou import build_novels_df, upsert_novels


def test_build_novels_df_sets_basic_fields():
    raw = [
        {"ncode": "N1234AB", "title": "テスト小説", "writer": "著者A",
         "genre": 2, "keyword": "異世界 転生", "bookmarkcount": 1000, "allcount": 50000},
    ]
    df = build_novels_df(raw, anime_ncodes=set())
    assert df.iloc[0]["ncode"] == "N1234AB"
    assert df.iloc[0]["title"] == "テスト小説"
    assert df.iloc[0]["author"] == "著者A"
    assert df.iloc[0]["monthly_rank_latest"] == 1
    assert df.iloc[0]["bookmark_count_latest"] == 1000


def test_build_novels_df_sets_is_anime_false_by_default():
    raw = [{"ncode": "N1234AB", "title": "作品", "writer": "著者",
            "genre": 2, "keyword": "", "bookmarkcount": 0, "allcount": 0}]
    df = build_novels_df(raw, anime_ncodes=set())
    assert df.iloc[0]["is_anime"] is False


def test_build_novels_df_sets_is_anime_true_when_in_anime_ncodes():
    raw = [{"ncode": "N1234AB", "title": "転スラ", "writer": "著者",
            "genre": 2, "keyword": "", "bookmarkcount": 0, "allcount": 0}]
    df = build_novels_df(raw, anime_ncodes={"N1234AB"})
    assert df.iloc[0]["is_anime"] is True


def test_build_novels_df_ncode_uppercased():
    raw = [{"ncode": "n1234ab", "title": "作品", "writer": "著者",
            "genre": 2, "keyword": "", "bookmarkcount": 0, "allcount": 0}]
    df = build_novels_df(raw, anime_ncodes=set())
    assert df.iloc[0]["ncode"] == "N1234AB"


def test_build_novels_df_assigns_rank_by_position():
    raw = [
        {"ncode": "N001", "title": "1位", "writer": "A", "genre": 2,
         "keyword": "", "bookmarkcount": 0, "allcount": 0},
        {"ncode": "N002", "title": "2位", "writer": "B", "genre": 2,
         "keyword": "", "bookmarkcount": 0, "allcount": 0},
    ]
    df = build_novels_df(raw, anime_ncodes=set())
    assert df.iloc[0]["monthly_rank_latest"] == 1
    assert df.iloc[1]["monthly_rank_latest"] == 2


def test_upsert_novels_returns_new_df_when_existing_is_empty():
    new_df = pd.DataFrame([{"ncode": "N001", "title": "A", "updated_at": "2026-01-01"}])
    result = upsert_novels(pd.DataFrame(), new_df)
    assert len(result) == 1
    assert result.iloc[0]["ncode"] == "N001"


def test_upsert_novels_updates_existing_row():
    existing = pd.DataFrame([{"ncode": "N001", "title": "旧タイトル", "updated_at": "2026-01-01"}])
    new_df = pd.DataFrame([{"ncode": "N001", "title": "新タイトル", "updated_at": "2026-06-01"}])
    result = upsert_novels(existing, new_df)
    assert len(result) == 1
    assert result.iloc[0]["title"] == "新タイトル"


def test_upsert_novels_adds_new_ncode():
    existing = pd.DataFrame([{"ncode": "N001", "title": "A", "updated_at": "2026-01-01"}])
    new_df = pd.DataFrame([
        {"ncode": "N001", "title": "A updated", "updated_at": "2026-06-01"},
        {"ncode": "N002", "title": "B", "updated_at": "2026-06-01"},
    ])
    result = upsert_novels(existing, new_df)
    assert len(result) == 2
    assert set(result["ncode"]) == {"N001", "N002"}
```

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
pytest tests/test_fetch_narou.py -v
```

期待出力: `ImportError` または `FAILED`

- [ ] **Step 3: fetch_narou.py を実装する**

`scripts/fetch_narou.py`:
```python
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

NAROU_PAGE_SIZE = 100
NAROU_MAX_COUNT = 1000


def fetch_monthly_top(limit: int = NAROU_MAX_COUNT) -> list[dict]:
    """なろう API から月刊ランキングを取得して返す。"""
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
    """API レスポンスから novels.csv 用 DataFrame を生成する。"""
    today = date.today().isoformat()
    rows = []
    for rank, item in enumerate(raw, start=1):
        ncode = item.get("ncode", "").upper()
        rows.append({
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
        })
    return pd.DataFrame(rows)


def upsert_novels(existing: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """ncode をキーに既存データに upsert する。"""
    if existing.empty:
        return new_df
    existing_indexed = existing.set_index("ncode")
    new_indexed = new_df.set_index("ncode")
    # 既存行を新規データで上書き
    existing_indexed.update(new_indexed)
    # 新規 ncode のみ追加
    new_ncodes = new_indexed.index.difference(existing_indexed.index)
    result = pd.concat([existing_indexed, new_indexed.loc[new_ncodes]])
    return result.reset_index()


def main() -> None:
    if not is_weekly_run_day():
        logger.info("今日は週次実行日（月曜）ではないためスキップ")
        return

    logger.info("なろう API から月刊TOP%d を取得開始", NAROU_MAX_COUNT)
    raw = fetch_monthly_top()
    logger.info("取得件数: %d", len(raw))

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
```

- [ ] **Step 4: テストを実行して全て通ることを確認する**

```bash
pytest tests/test_fetch_narou.py -v
```

期待出力: `8 passed`

- [ ] **Step 5: コミット**

```bash
git add scripts/fetch_narou.py tests/test_fetch_narou.py
git commit -m "feat: fetch_narou.py — なろうAPI月刊TOP1000取得・novels.csv upsert"
```

---

### Task 4: fetch_snapshots.py（毎日・daily_snapshots.csv 追記）

**Files:**
- Create: `scripts/fetch_snapshots.py`
- Create: `tests/test_fetch_snapshots.py`

**Interfaces:**
- Consumes: `utils.DAILY_SNAPSHOTS_CSV`, `utils.NOVELS_CSV`, `utils.NAROU_API_URL`, `utils.get_logger`, `utils.load_csv`, `utils.save_csv`
- Produces:
  - `fetch_novel_snapshot(ncode: str) -> dict | None`
  - `calc_daily_view(ncode: str, cumulative_view: int, snapshots: pd.DataFrame, today: date) -> int | None`

- [ ] **Step 1: テストを書く**

`tests/test_fetch_snapshots.py`:
```python
from datetime import date
import pandas as pd
import pytest
from fetch_snapshots import calc_daily_view


def test_calc_daily_view_returns_none_when_no_previous_data():
    result = calc_daily_view("N001", 1000, pd.DataFrame(), date(2026, 6, 19))
    assert result is None


def test_calc_daily_view_returns_diff_from_yesterday():
    snapshots = pd.DataFrame([{
        "ncode": "N001",
        "date": "2026-06-18",
        "cumulative_view": 800,
    }])
    result = calc_daily_view("N001", 1000, snapshots, date(2026, 6, 19))
    assert result == 200


def test_calc_daily_view_returns_none_when_ncode_not_found():
    snapshots = pd.DataFrame([{
        "ncode": "N002",
        "date": "2026-06-18",
        "cumulative_view": 800,
    }])
    result = calc_daily_view("N001", 1000, snapshots, date(2026, 6, 19))
    assert result is None


def test_calc_daily_view_returns_none_when_prev_cumulative_is_nan():
    import numpy as np
    snapshots = pd.DataFrame([{
        "ncode": "N001",
        "date": "2026-06-18",
        "cumulative_view": np.nan,
    }])
    result = calc_daily_view("N001", 1000, snapshots, date(2026, 6, 19))
    assert result is None


def test_calc_daily_view_returns_zero_when_no_change():
    snapshots = pd.DataFrame([{
        "ncode": "N001",
        "date": "2026-06-18",
        "cumulative_view": 1000,
    }])
    result = calc_daily_view("N001", 1000, snapshots, date(2026, 6, 19))
    assert result == 0
```

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
pytest tests/test_fetch_snapshots.py -v
```

期待出力: `ImportError` または `FAILED`

- [ ] **Step 3: fetch_snapshots.py を実装する**

`scripts/fetch_snapshots.py`:
```python
"""
novels.csv の全 ncode を対象に日次スナップショットを取得して daily_snapshots.csv に追記する。
毎日実行。
"""
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
        "out": "jsonlite",
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
    """前日の累計 View 数との差分で daily_view を計算する。"""
    if snapshots.empty:
        return None
    yesterday = (today - timedelta(days=1)).isoformat()
    prev = snapshots[
        (snapshots["ncode"] == ncode) & (snapshots["date"] == yesterday)
    ]
    if prev.empty:
        return None
    prev_cumulative = prev.iloc[0]["cumulative_view"]
    if pd.isna(prev_cumulative):
        return None
    return cumulative_view - int(prev_cumulative)


def main() -> None:
    today = date.today()
    today_str = today.isoformat()

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

        cumulative_view = detail.get("allcount", 0)
        daily_view = calc_daily_view(ncode, cumulative_view, snapshots, today)

        new_rows.append({
            "date": today_str,
            "ncode": ncode,
            "cumulative_view": cumulative_view,
            "daily_view": daily_view,
            "bookmark_count": detail.get("bookmarkcount", 0),
            "monthly_rank": row.get("monthly_rank_latest"),
            "weekly_rank": None,
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
```

- [ ] **Step 4: テストを実行して全て通ることを確認する**

```bash
pytest tests/test_fetch_snapshots.py -v
```

期待出力: `5 passed`

- [ ] **Step 5: コミット**

```bash
git add scripts/fetch_snapshots.py tests/test_fetch_snapshots.py
git commit -m "feat: fetch_snapshots.py — 日次スナップショット取得・daily_view差分計算"
```

---

### Task 5: fetch_trends.py（週次・PyTrends → trends_cache.csv 追記）

**Files:**
- Create: `scripts/fetch_trends.py`
- Create: `tests/test_fetch_trends.py`

**Interfaces:**
- Consumes: `utils.ANIME_WORKS_CSV`, `utils.NOVELS_CSV`, `utils.TRENDS_CACHE_CSV`, `utils.get_logger`, `utils.is_weekly_run_day`, `utils.load_csv`, `utils.rate_limit_sleep`, `utils.save_csv`
- Produces:
  - `get_week_start(d: date) -> str` — 指定日が属する週の月曜日の日付文字列
  - `fetch_trend_score(pytrends: TrendReq, keyword: str) -> tuple[dict[str, int], bool]`
  - `build_trend_rows(id_: str, id_type: str, keyword: str, scores: dict[str, int], success: bool) -> list[dict]`

- [ ] **Step 1: テストを書く**

`tests/test_fetch_trends.py`:
```python
from datetime import date
import pytest
from fetch_trends import build_trend_rows, get_week_start


def test_get_week_start_on_monday():
    # 2026-06-15 は月曜日
    assert get_week_start(date(2026, 6, 15)) == "2026-06-15"


def test_get_week_start_on_wednesday_returns_monday():
    # 2026-06-17 は水曜日 → 属する週の月曜は 2026-06-15
    assert get_week_start(date(2026, 6, 17)) == "2026-06-15"


def test_get_week_start_on_sunday_returns_monday():
    # 2026-06-21 は日曜日 → 属する週の月曜は 2026-06-15
    assert get_week_start(date(2026, 6, 21)) == "2026-06-15"


def test_build_trend_rows_on_success_returns_one_row_per_week():
    scores = {"2026-06-15": 80, "2026-06-22": 60}
    rows = build_trend_rows("N001", "novel", "転スラ", scores, success=True)
    assert len(rows) == 2
    assert all(r["fetch_status"] == "ok" for r in rows)
    assert rows[0]["trend_score"] == 80
    assert rows[1]["trend_score"] == 60


def test_build_trend_rows_on_success_sets_correct_fields():
    scores = {"2026-06-15": 50}
    rows = build_trend_rows("anime_001", "anime", "転スラ", scores, success=True)
    assert rows[0]["id"] == "anime_001"
    assert rows[0]["id_type"] == "anime"
    assert rows[0]["keyword_used"] == "転スラ"
    assert rows[0]["region"] == "JP"
    assert rows[0]["week_start"] == "2026-06-15"


def test_build_trend_rows_on_failure_returns_single_skip_row():
    rows = build_trend_rows("N001", "novel", "転スラ", {}, success=False)
    assert len(rows) == 1
    assert rows[0]["fetch_status"] == "skip"
    assert rows[0]["trend_score"] is None


def test_build_trend_rows_on_failure_sets_correct_fields():
    rows = build_trend_rows("N001", "novel", "転スラ", {}, success=False)
    assert rows[0]["id"] == "N001"
    assert rows[0]["keyword_used"] == "転スラ"
    assert rows[0]["region"] == "JP"
```

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
pytest tests/test_fetch_trends.py -v
```

期待出力: `ImportError` または `FAILED`

- [ ] **Step 3: fetch_trends.py を実装する**

`scripts/fetch_trends.py`:
```python
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

REGION = "JP"
TIMEFRAME = "today 3-m"


def get_week_start(d: date) -> str:
    """指定日が属する週の月曜日の日付文字列を返す。"""
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def fetch_trend_score(
    pytrends: TrendReq, keyword: str
) -> tuple[dict[str, int], bool]:
    """
    1キーワードのトレンドスコアを取得する。
    返り値: (week_start → trend_score の dict, 成功フラグ)
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
) -> list[dict]:
    """trends_cache.csv 用の行リストを生成する。"""
    if not success:
        return [{
            "week_start": get_week_start(date.today()),
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
    if not is_weekly_run_day():
        logger.info("今日は週次実行日（月曜）ではないためスキップ")
        return

    pytrends = TrendReq(hl="ja-JP", tz=540)
    cache = load_csv(TRENDS_CACHE_CSV, dtype={"id": str})
    existing_keys: set[tuple[str, str, str]] = set()
    if not cache.empty:
        existing_keys = set(
            zip(cache["week_start"], cache["id"], cache["keyword_used"])
        )

    novels = load_csv(NOVELS_CSV, dtype={"ncode": str})
    anime_works = load_csv(ANIME_WORKS_CSV)
    new_rows: list[dict] = []
    week_start = get_week_start(date.today())

    # novels: title を1キーワードとして使用
    for _, row in novels.iterrows():
        ncode = str(row["ncode"])
        keyword = str(row["title"])
        if (week_start, ncode, keyword) in existing_keys:
            continue
        scores, success = fetch_trend_score(pytrends, keyword)
        new_rows.extend(build_trend_rows(ncode, "novel", keyword, scores, success))
        rate_limit_sleep()

    # anime_works: title_short と title_full の2キーワードを順番に取得
    for _, row in anime_works.iterrows():
        anime_id = str(row["anime_id"])
        for keyword in [row.get("title_short", ""), row.get("title_full", "")]:
            if not keyword or pd.isna(keyword):
                continue
            keyword = str(keyword)
            if (week_start, anime_id, keyword) in existing_keys:
                continue
            scores, success = fetch_trend_score(pytrends, keyword)
            new_rows.extend(
                build_trend_rows(anime_id, "anime", keyword, scores, success)
            )
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
```

- [ ] **Step 4: テストを実行して全て通ることを確認する**

```bash
pytest tests/test_fetch_trends.py -v
```

期待出力: `7 passed`

- [ ] **Step 5: コミット**

```bash
git add scripts/fetch_trends.py tests/test_fetch_trends.py
git commit -m "feat: fetch_trends.py — PyTrends週次取得・略称+正式名称2キーワード対応"
```

---

### Task 6: backfill_wayback.py（初回手動・Wayback Machine → daily_snapshots.csv 補完）

**Files:**
- Create: `scripts/backfill_wayback.py`
- Create: `tests/test_backfill_wayback.py`

**Interfaces:**
- Consumes: `utils.DAILY_SNAPSHOTS_CSV`, `utils.get_logger`, `utils.load_csv`, `utils.save_csv`
- Produces:
  - `list_archive_urls(start: date, end: date) -> list[dict]`
  - `fetch_archive_html(timestamp: str) -> str | None`
  - `parse_ranking_html(html: str, snapshot_date: str) -> list[dict]`

- [ ] **Step 1: テストを書く**

`tests/test_backfill_wayback.py`:
```python
import pytest
from backfill_wayback import parse_ranking_html

# なろうランキングページの簡略化されたサンプル HTML
SAMPLE_HTML_WITH_RANKS = """
<html><body>
<div class="rank_h"><a href="/novel/N1234AB/">転生小説タイトル</a></div>
<div class="rank_h"><a href="/novel/N5678CD/">異世界小説タイトル</a></div>
<div class="rank_h"><a href="/novel/N9999ZZ/">三番目の小説</a></div>
</body></html>
"""

SAMPLE_HTML_NO_RANKS = "<html><body><p>データなし</p></body></html>"


def test_parse_ranking_html_extracts_ncodes():
    rows = parse_ranking_html(SAMPLE_HTML_WITH_RANKS, "2024-01-15")
    ncodes = [r["ncode"] for r in rows]
    assert "N1234AB" in ncodes
    assert "N5678CD" in ncodes
    assert "N9999ZZ" in ncodes


def test_parse_ranking_html_sets_monthly_rank_in_order():
    rows = parse_ranking_html(SAMPLE_HTML_WITH_RANKS, "2024-01-15")
    assert rows[0]["monthly_rank"] == 1
    assert rows[1]["monthly_rank"] == 2
    assert rows[2]["monthly_rank"] == 3


def test_parse_ranking_html_sets_date():
    rows = parse_ranking_html(SAMPLE_HTML_WITH_RANKS, "2024-01-15")
    assert all(r["date"] == "2024-01-15" for r in rows)


def test_parse_ranking_html_sets_view_fields_to_none():
    rows = parse_ranking_html(SAMPLE_HTML_WITH_RANKS, "2024-01-15")
    assert all(r["cumulative_view"] is None for r in rows)
    assert all(r["daily_view"] is None for r in rows)
    assert all(r["bookmark_count"] is None for r in rows)
    assert all(r["weekly_rank"] is None for r in rows)


def test_parse_ranking_html_returns_empty_list_when_no_items():
    rows = parse_ranking_html(SAMPLE_HTML_NO_RANKS, "2024-01-15")
    assert rows == []


def test_parse_ranking_html_uppercases_ncode():
    html = '<html><body><div class="rank_h"><a href="/novel/n1234ab/">タイトル</a></div></body></html>'
    rows = parse_ranking_html(html, "2024-01-15")
    assert rows[0]["ncode"] == "N1234AB"
```

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
pytest tests/test_backfill_wayback.py -v
```

期待出力: `ImportError` または `FAILED`

- [ ] **Step 3: backfill_wayback.py を実装する**

`scripts/backfill_wayback.py`:
```python
"""
Wayback Machine CDX API でなろうランキングページのアーカイブを取得し、
daily_snapshots.csv に過去のランキング順位データを補完する。
初回のみ手動実行。
"""
import argparse
import re
import time
from datetime import date, timedelta

import pandas as pd
import requests
from bs4 import BeautifulSoup

from utils import DAILY_SNAPSHOTS_CSV, get_logger, load_csv, save_csv

logger = get_logger(__name__)

CDX_API_URL = "http://web.archive.org/cdx/search/cdx"
NAROU_RANKING_URL = "https://yomou.syosetu.com/rank/list/type/monthly_total/"
WAYBACK_SLEEP_SEC = 3


def list_archive_urls(start: date, end: date) -> list[dict]:
    """Wayback Machine CDX API でアーカイブ URL 一覧を取得する。"""
    params = {
        "url": NAROU_RANKING_URL,
        "output": "json",
        "fl": "timestamp,original",
        "from": start.strftime("%Y%m%d"),
        "to": end.strftime("%Y%m%d"),
        "collapse": "timestamp:8",  # 1日1件に絞る
        "limit": 500,
    }
    resp = requests.get(CDX_API_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if len(data) <= 1:
        return []
    # 先頭行はヘッダー ["timestamp", "original"]
    return [{"timestamp": row[0], "original": row[1]} for row in data[1:]]


def fetch_archive_html(timestamp: str) -> str | None:
    """Wayback Machine からアーカイブ HTML を取得する。"""
    url = f"http://web.archive.org/web/{timestamp}/{NAROU_RANKING_URL}"
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("アーカイブ取得失敗 timestamp=%s: %s", timestamp, e)
        return None


def parse_ranking_html(html: str, snapshot_date: str) -> list[dict]:
    """なろうランキング HTML をパースしてランキングデータを抽出する。"""
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    # なろうランキングページの作品ブロック（ページ構造が変わった場合は要確認）
    items = soup.select("div.rank_h") or soup.select("li.rank_h")
    for rank, item in enumerate(items, start=1):
        link = item.select_one("a[href*='/novel/']")
        if not link:
            continue
        href = link.get("href", "")
        match = re.search(r"/novel/([A-Za-z0-9]+)/", href)
        if not match:
            continue
        ncode = match.group(1).upper()
        rows.append({
            "date": snapshot_date,
            "ncode": ncode,
            "cumulative_view": None,
            "daily_view": None,
            "bookmark_count": None,
            "monthly_rank": rank,
            "weekly_rank": None,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wayback Machine から過去のなろうランキングデータを補完する"
    )
    default_start = (date.today() - timedelta(days=365 * 3)).isoformat()
    default_end = date.today().isoformat()
    parser.add_argument("--start", default=default_start, help="取得開始日 (YYYY-MM-DD)")
    parser.add_argument("--end", default=default_end, help="取得終了日 (YYYY-MM-DD)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    logger.info("Wayback Machine アーカイブ一覧取得: %s 〜 %s", start, end)
    archives = list_archive_urls(start, end)
    logger.info("対象アーカイブ件数: %d", len(archives))

    snapshots = load_csv(DAILY_SNAPSHOTS_CSV, dtype={"ncode": str})
    existing_keys: set[tuple[str, str]] = set()
    if not snapshots.empty:
        existing_keys = set(zip(snapshots["date"], snapshots["ncode"]))

    new_rows: list[dict] = []
    for archive in archives:
        timestamp = archive["timestamp"]
        snapshot_date = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"

        html = fetch_archive_html(timestamp)
        if html is None:
            continue

        for row in parse_ranking_html(html, snapshot_date):
            key = (row["date"], row["ncode"])
            if key in existing_keys:
                continue
            new_rows.append(row)
            existing_keys.add(key)

        time.sleep(WAYBACK_SLEEP_SEC)

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
```

- [ ] **Step 4: テストを実行して全て通ることを確認する**

```bash
pytest tests/test_backfill_wayback.py -v
```

期待出力: `6 passed`

- [ ] **Step 5: 全テストを実行して回帰がないことを確認する**

```bash
pytest tests/ -v
```

期待出力: `33 passed`（全タスクのテスト合計: utils=7, fetch_narou=8, fetch_snapshots=5, fetch_trends=7, backfill_wayback=6）

- [ ] **Step 6: コミット**

```bash
git add scripts/backfill_wayback.py tests/test_backfill_wayback.py
git commit -m "feat: backfill_wayback.py — Wayback Machineから過去ランキングデータを補完"
```
