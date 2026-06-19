# フェーズ1 データ基盤スクリプト 設計書

**作成日**: 2026-06-19  
**スコープ**: Pythonスクリプト4本 + utils.py + requirements.txt + anime_works.csv 初期データ

---

## 目的

なろう小説アニメ化分析ツールのデータ収集基盤を構築する。
GitHub Actions で毎日自動実行され、CSVファイルにデータを蓄積する。

---

## スコープ外

- 類似度計算（compute_similarity.py）— フェーズ2
- フロントエンド — フェーズ3

---

## ファイル構成

```
scripts/
├── utils.py               # 共通ユーティリティ
├── fetch_narou.py         # なろうAPI → novels.csv upsert（週次）
├── fetch_snapshots.py     # daily_snapshots.csv 追記（毎日）
├── fetch_trends.py        # PyTrends → trends_cache.csv 追記（週次）
├── backfill_wayback.py    # Wayback Machine → daily_snapshots.csv 補完（初回手動）
└── requirements.txt
data/
├── anime_works.csv        # 初期データあり（略称・正式名称カラム追加済み）
├── novels.csv             # fetch_narou.py が生成
├── daily_snapshots.csv    # fetch_snapshots.py が生成
└── trends_cache.csv       # fetch_trends.py が生成
```

---

## データモデル変更点

### anime_works.csv（設計書から追加）

| 追加カラム | 型 | 説明 |
|---|---|---|
| `title_short` | string | 略称（例: 転スラ）。PyTrends キーワード用 |
| `title_full` | string | 正式名称（例: 転生したらスライムだった件）。同上 |

### trends_cache.csv（主キー変更）

- **変更前**: `(week_start, id)` 
- **変更後**: `(week_start, id, keyword_used)`
- 同一作品・同一週に略称行と正式名称行の2行を保存する

**集計モード（後フェーズで使用）**:
- 合算（平均）: 同一 `(week_start, id)` の `ok` 行のスコアを平均
- 略称のみ / 正式名称のみ: `keyword_used` でフィルタ

---

## utils.py

| 提供する機能 | 説明 |
|---|---|
| `DATA_DIR` 等パス定数 | `scripts/` からの相対パスでなく絶対パスで管理 |
| `get_logger(name)` | 標準ロギング設定（レベル INFO、タイムスタンプ付き） |
| `rate_limit_sleep()` | 30〜60秒ランダムスリープ（pytrends レート制限回避） |
| `is_weekly_run_day(weekday=0)` | 今日が指定曜日（デフォルト月曜）かチェック |
| `load_csv(path, dtypes)` | pandas で CSV 読み込み。ファイルなければ空 DataFrame |
| `save_csv(df, path)` | pandas で CSV 書き込み（index なし） |

---

## fetch_narou.py

**実行タイミング**: 週次（月曜。`is_weekly_run_day()` で判定し、月曜以外は即終了）

**処理フロー**:
1. なろうAPI `https://api.syosetu.com/novelapi/api/` に `order=monthlypoint` でリクエスト
2. 100件ずつページングして TOP1000 を取得
3. novels.csv を読み込み、ncode をキーに upsert
4. anime_works.csv の ncode 一覧と突合し `is_anime` フラグを付与
5. `updated_at` を今日の日付に更新して保存

---

## fetch_snapshots.py

**実行タイミング**: 毎日

**処理フロー**:
1. novels.csv の全 ncode を取得
2. 各 ncode に対してなろうAPI でスナップショット取得
3. daily_snapshots.csv の前日レコードと差分を取り `daily_view` を計算（初日は null）
4. 同日・同 ncode が既存ならスキップ（冪等）
5. 新規行を daily_snapshots.csv に追記

---

## fetch_trends.py

**実行タイミング**: 週次（月曜。`is_weekly_run_day()` で判定）

**処理フロー**:
1. novels.csv と anime_works.csv の全対象を結合してキーワードリストを生成
   - novels: `title` を1キーワードとして使用（略称/正式名称の区別なし）
   - anime_works: `title_short` → `title_full` の2キーワードを順番に使用
2. 各キーワードごとにリクエスト、直後に `rate_limit_sleep()` でスリープ
3. 取得済みの `(week_start, id, keyword_used)` はスキップ（冪等）
4. 失敗時は `fetch_status=skip` で記録して継続（スクリプトを止めない）
5. 結果を trends_cache.csv に追記

---

## backfill_wayback.py

**実行タイミング**: 初回のみ手動実行

**引数**:
- `--start YYYY-MM-DD`（デフォルト: 3年前）
- `--end YYYY-MM-DD`（デフォルト: 今日）

**処理フロー**:
1. Wayback Machine CDX API でなろうランキングページのアーカイブURLを列挙
2. 各アーカイブ HTML を取得・パースしてランキング順位を抽出
3. daily_snapshots.csv に追記（同日・同 ncode が既存ならスキップ）

**制約**: アーカイブは疎（週数回程度）。View 数は取れないため `cumulative_view`・`daily_view` は null。ランキング順位のみ補完。

---

## requirements.txt

```
requests>=2.31.0
pandas>=2.0.0
pytrends>=4.9.2
beautifulsoup4>=4.12.0
lxml>=4.9.0
```

---

## anime_works.csv 初期データ

**B（なろう原作）初期登録タイトル**:
転スラ・リゼロ・無職転生・オーバーロード・本好きの下剋上・陰の実力者になりたくて・ひとりぼっちの異世界攻略・蜘蛛ですが何か？（約8タイトル）

**C（外部アニメ）初期登録タイトル**:
SPY×FAMILY・進撃の巨人・チェンソーマン・呪術廻戦・鬼滅の刃（5タイトル）

---

## 成功基準

- `python scripts/fetch_narou.py` 単体で novels.csv が生成される
- `python scripts/fetch_snapshots.py` 単体で daily_snapshots.csv に行が追記される
- `python scripts/fetch_trends.py` 単体で trends_cache.csv に略称・正式名称の2行が追記される（失敗時も skip で継続）
- `python scripts/backfill_wayback.py` 単体で daily_snapshots.csv にランキング過去データが追記される
- GitHub Actions の `daily.yml` でこれらが順次実行され、エラーなく完了する
