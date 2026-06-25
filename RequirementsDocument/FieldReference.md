# フィールド・変数名 逆引きリファレンス

このドキュメントは、コードベース全体で使われているフィールド名・変数名・定数の意味を一覧化した逆引きリファレンスです。
フィールド名が何を指すかわからないときにここを参照してください。

---

## 目次

1. [なろう API → CSV フィールド対応表](#1-なろう-api--csv-フィールド対応表)
2. [novels.csv フィールド一覧](#2-novelscsv-フィールド一覧)
3. [daily_snapshots.csv フィールド一覧](#3-daily_snapshotscsv-フィールド一覧)
4. [anime_works.csv フィールド一覧](#4-anime_workscsv-フィールド一覧)
5. [novels_merged.json フィールド一覧](#5-novels_mergedjson-フィールド一覧)
6. [norm_params.json フィールド一覧](#6-norm_paramsjson-フィールド一覧)
7. [スコアキー（weights）一覧](#7-スコアキーweights一覧)
8. [JavaScript グローバル変数一覧](#8-javascript-グローバル変数一覧)
9. [日本語概念 → フィールド名 逆引き](#9-日本語概念--フィールド名-逆引き)

---

## 1. なろう API → CSV フィールド対応表

なろう API のレスポンスフィールド名と、CSV に保存するときのカラム名の対応。
定義元: `scripts/narou_config.py` の `NOVELS_API_MAP` / `SNAPSHOTS_API_MAP`。

| API フィールド | CSV カラム | 意味 |
|---|---|---|
| `ncode` | `ncode` | 作品識別コード（例: N1234AB） |
| `title` | `title` | 作品タイトル |
| `writer` | `author` | 著者名 |
| `biggenre` | `biggenre` | 親ジャンルコード（1=恋愛, 2=ファンタジー, 3=文芸, 4=SF, 98=その他, 99=ノンジャンル） |
| `genre` | `genre` | サブジャンルコード（101=異世界恋愛, 201=ハイファンタジー 等） |
| `keyword` | `tags` | スペース区切りタグ（「転生」「異世界」等） |
| `story` | `story` | あらすじ |
| `fav_novel_cnt` | `bookmark_count_latest` | ブックマーク数（いわゆる「お気に入り」登録数） |
| `weekly_unique` | `weekly_unique_latest` | 週間ユニーク読者数 |
| `length` | `length` | 総文字数 |
| `global_point` | `global_point_latest` | **総合評価ポイント**（※ なろうには View 数 API がないため、この値を累計閲覧指標として代用） |
| `daily_point` | `daily_point_latest` | 日間評価ポイント |
| `weekly_point` | `weekly_point_latest` | 週間評価ポイント |
| `monthly_point` | `monthly_point_latest` | **月間評価ポイント**（直近1ヶ月の盛り上がり指標） |
| `all_point` | `all_point_latest` | 累計評価ポイント（全期間合計） |
| `all_hyoka_cnt` | `all_hyoka_cnt_latest` | **累計評価件数**（いいね数の代替として使用） |
| `impression_cnt` | `impression_cnt_latest` | 感想件数 |
| `review_cnt` | `review_cnt_latest` | レビュー件数 |
| `general_all_no` | `episode_count_latest` | エピソード（話）数 |
| `general_lastup` | `general_lastup` | 最終掲載日（活性度スコア計算に使用） |
| `novelupdated_at` | `novel_updated_at` | 作品情報最終更新日時 |
| `istensei` | `is_isekai_tensei` | 転生要素フラグ（0/1） |
| `istenni` | `is_isekai_tenni` | 転移要素フラグ（0/1） |
| `end` | `is_completed` | 完結フラグ（0=連載中, 1=完結） |

---

## 2. novels.csv フィールド一覧

なろう小説マスターデータ。`scripts/fetch_narou.py` が週次で更新。

| カラム名 | 型 | 説明 |
|---|---|---|
| `ncode` | str | 作品識別コード（主キー） |
| `title` | str | タイトル |
| `author` | str | 著者名 |
| `biggenre` | str | 親ジャンルコード |
| `genre` | str | サブジャンルコード |
| `tags` | str | タグ（スペース区切り） |
| `is_anime` | bool | アニメ化済みフラグ（手動または Annict 連携で設定） |
| `anime_id` | str | アニメ作品ID（`anime_works.csv` の `anime_id` に対応） |
| `monthly_rank_latest` | float | 直近月刊ランク（1〜1000） |
| `bookmark_count_latest` | int | ブックマーク数 |
| `all_hyoka_cnt_latest` | int | 累計評価件数 |
| `all_point_latest` | float | 累計評価ポイント |
| `global_point_latest` | int | 総合評価ポイント（累計閲覧の代替指標） |
| `monthly_point_latest` | float | 月間評価ポイント |
| `daily_point_latest` | float | 日間評価ポイント |
| `weekly_point_latest` | float | 週間評価ポイント |
| `impression_cnt_latest` | float | 感想件数 |
| `review_cnt_latest` | float | レビュー件数 |
| `weekly_unique_latest` | float | 週間ユニーク読者数 |
| `episode_count_latest` | float | エピソード数 |
| `length` | float | 総文字数 |
| `general_lastup` | str | 最終掲載日（YYYY-MM-DD HH:MM:SS） |
| `novel_updated_at` | str | 作品情報更新日時 |
| `story` | str | あらすじ |
| `is_isekai_tensei` | int | 転生要素フラグ |
| `is_isekai_tenni` | int | 転移要素フラグ |
| `is_completed` | int | 完結フラグ |

---

## 3. daily_snapshots.csv フィールド一覧

日次スナップショット。`scripts/fetch_snapshots.py` が毎日追記。

| カラム名 | 型 | 説明 |
|---|---|---|
| `date` | str | スナップショット日（YYYY-MM-DD） |
| `ncode` | str | 作品識別コード |
| `global_point` | int | その日時点の総合評価ポイント |
| `global_point_delta` | int | 前日からの総合評価ポイント増分（初日は null） |
| `bookmark_count` | int | その日時点のブックマーク数 |
| `monthly_rank` | int | その日時点の月刊ランク |
| `weekly_rank` | int | その日時点の週間ランク |
| `weekly_unique` | float | 週間ユニーク読者数 |
| `all_point` | float | 累計評価ポイント |
| `all_hyoka_cnt` | int | 累計評価件数 |
| `episode_count` | float | エピソード数 |

---

## 4. anime_works.csv フィールド一覧

アニメ化済み作品マスター。**手動管理**（スクリプトで自動更新しない）。

| カラム名 | 型 | 説明 |
|---|---|---|
| `anime_id` | str | アニメ作品識別ID（例: `slime_001`）。主キー |
| `anime_title` | str | アニメ作品タイトル |
| `title_short` | str | 短縮タイトル（検索・表示用） |
| `title_full` | str | 正式フルタイトル |
| `ncode` | str | 原作なろう小説の ncode（`novels.csv` と結合） |
| `source_type` | str | 原作タイプ（`narou` / `other`） |
| `air_date` | str | アニメ放映開始日（YYYY-MM-DD） |
| `season` | str | 放映クール（例: `2024Q1`） |
| `studio` | str | 制作スタジオ名 |
| `genre_manual` | str | 手動設定ジャンル（スコア類似度計算に使用） |
| `tags_manual` | str | 手動設定タグ（スペース区切り、スコア類似度計算に使用） |
| `announce_date` | str | **アニメ化発表日**（YYYY-MM-DD。タイムライン分析のイベントマーカーに使用） |
| `novel_publish_date` | str | **書籍化1巻発売日**（YYYY-MM-DD。タイムライン分析のイベントマーカーに使用） |

---

## 5. novels_merged.json フィールド一覧

`scripts/compute_similarity.py` が生成する JSON。`docs/data/novels_merged.json` に出力。
`novels.csv` + `daily_snapshots.csv` + `anime_works.csv` を結合し、スコアを計算したもの。

### トップレベル

| キー | 型 | 説明 |
|---|---|---|
| `generated_at` | str | 生成日時（YYYY-MM-DD HH:MM:SS） |
| `novels` | array | 小説オブジェクトの配列（約1100件） |
| `anime_works` | array | アニメ作品オブジェクトの配列 |

### novels[] の各オブジェクト

novels.csv のフィールドに加えて、以下が追加される：

| フィールド | 型 | 説明 |
|---|---|---|
| `genre_label` | str | ジャンルの日本語ラベル（例: "ハイファンタジー"） |
| `bm_view_ratio` | float | **BM/View比率**。`bookmark_count_latest / global_point_latest` で算出。コア読者の定着度を示す指標 |
| `eval_score` | float | 評価件数を正規化したスコア（0〜1）。norm_params の `all_hyoka_cnt_latest.max` を上限として計算 |
| `view_growth_6mo` | float | 6ヶ月間の総合評価ポイント成長率 |
| `best_rank_ever` | int | 記録している中で最も高かった月刊ランク（数値が小さいほど上位） |
| `pattern1_best_score` | float | 全アニメ作品との類似度スコアのうち最高値（0〜100） |
| `pattern1_best_anime_id` | str | 最も類似しているアニメ作品の `anime_id` |
| `pattern1_scores` | array | 全アニメ作品との比較スコア詳細（下記参照） |
| `growth_metrics` | dict | 1日・7日・30日ごとの評価件数・評価ポイント増分（下記参照） |

### pattern1_scores[] の各オブジェクト

各アニメ作品との比較スコアを格納。

| フィールド | 型 | 説明 |
|---|---|---|
| `anime_id` | str | 比較対象アニメの ID |
| `anime_title` | str | 比較対象アニメのタイトル |
| `score` | float | 合計スコア（0〜100） |
| `genre_score` | float | ジャンル一致スコア（0 or 1） |
| `tag_score` | float | タグ類似度スコア（Jaccard係数、0〜1） |
| `rank_score` | float | ランク帯スコア（1位台=1.0, 101〜300=0.6, 301〜=0.3） |
| `bm_view_score` | float | BM/View比率スコア（norm_params の max を上限に正規化、0〜1） |
| `growth_score` | float | View成長率スコア（0〜1） |
| `eval_score` | float | 評価件数スコア（norm_params の max を上限に正規化、0〜1） |
| `monthly_point_score` | float | 月間ポイントスコア（norm_params の max を上限に正規化、0〜1） |
| `activity_score` | float | 活性スコア（`general_lastup` からの経過日数で計算。30日以内=1.0、1年超=0.0） |

### growth_metrics の構造

```json
{
  "all_hyoka_cnt": {
    "1d": { "delta": 5, "rate": 0.02 },
    "7d": { "delta": 30, "rate": 0.12 },
    "30d": { "delta": 100, "rate": 0.45 }
  },
  "all_point": {
    "1d": { "delta": 50, "rate": 0.01 },
    ...
  }
}
```

- `delta`: 指定期間中の増加数（絶対値）
- `rate`: 指定期間中の増加率（%）
- JS では `growth_all_hyoka_cnt_7d_delta` のようなフラット形式に変換して参照

### anime_works[] の各オブジェクト

`anime_works.csv` の内容に `ncode`, `announce_date`, `novel_publish_date` を追加したもの。

---

## 6. norm_params.json フィールド一覧

`scripts/compute_similarity.py --update-norm-only` が生成。`data/norm_params.json` に出力。
データの 99 パーセンタイル値を上限として算出する（外れ値の影響を抑えるため）。

```json
{
  "computed_at": "YYYY-MM-DD",
  "params": {
    "all_hyoka_cnt_latest":  { "min": 0.0, "max": 35649.86 },
    "all_point_latest":      { "min": 0.0, "max": 337863.26 },
    "monthly_point_latest":  { "min": 0.0, "max": 38900.96 },
    "impression_cnt_latest": { "min": 0.0, "max": 500.0 },
    "bm_view_ratio":         { "min": 0.0, "max": 0.307 }
  }
}
```

| キー | 意味 |
|---|---|
| `all_hyoka_cnt_latest` | 評価件数の満点基準（この値以上で 100 点） |
| `all_point_latest` | 累計評価ポイントの満点基準 |
| `monthly_point_latest` | 月間ポイントの満点基準 |
| `impression_cnt_latest` | 感想件数の満点基準 |
| `bm_view_ratio` | BM/View比率の満点基準（この比率以上で 100 点） |

> ブラウザ設定画面でこれらの値を変更できます（localStorage に保存、ファイルは変更しない）。

---

## 7. スコアキー（weights）一覧

`scripts/narou_config.py` の `PATTERN1_WEIGHTS` と `docs/js/app.js` の `DEFAULT_WEIGHTS` / `currentWeights` で使われるキー。

| Python キー | JS キー | 意味 | デフォルト重み |
|---|---|---|---|
| `genre` | `genre` | ジャンル一致（大分類が同じか） | 0（別画面で実施） |
| `tag` | `tag` | タグ類似度（Jaccard係数） | 0（別画面で実施） |
| `rank` | `rank` | ランク帯（月刊順位から算出） | 0.17 / 17% |
| `bm_view` | `bmView` | BM/View比率（コア読者定着度） | 0.13 / 13% |
| `growth` | `growth` | View成長率（6ヶ月） | 0.08 / 8% |
| `eval` | `eval` | 評価件数 | 0.07 / 7% |
| `monthly_point` | `monthlyPoint` | 月間ポイント | 0.10 / 10% |
| `activity` | `activity` | 活性スコア（最終更新からの経過） | 0.05 / 5% |

> Python と JS でキー名が微妙に異なる点に注意（`bm_view` vs `bmView`、`monthly_point` vs `monthlyPoint`）。

---

## 8. JavaScript グローバル変数一覧

`docs/js/app.js` の先頭付近で宣言されるグローバル変数・定数。

### データ保持変数

| 変数名 | 型 | 保持内容 |
|---|---|---|
| `novelsData` | object \| null | `novels_merged.json` の内容。`.novels[]` が小説一覧、`.anime_works[]` がアニメ作品一覧 |
| `trendsData` | object \| null | `trends_merged.json` の内容。Google Trends のキャッシュデータ |
| `snapshotsData` | object \| null | `snapshots_merged.json` の内容。`daily_snapshots.csv` を JSON 化したもの |
| `fileNormParams` | object \| null | `norm_params.json` から読み込んだファイルデフォルト値。「ファイルの値に戻す」のリセット基準 |
| `currentNormParams` | object \| null | 現在有効な正規化パラメータ。localStorage の値があればそちらを優先 |

### UI 状態変数

| 変数名 | 型 | 説明 |
|---|---|---|
| `selectedNcode` | str \| null | 詳細比較パネルで選択中の作品の ncode |
| `currentWeights` | object | スコア計算の重み。合計が 0 でなければ自動正規化して使用 |
| `currentPage` | int | ランキング一覧のページ番号（0 始まり） |
| `sortBy` | str | ランキング一覧の並び替えキー（デフォルト `'score'`） |
| `visibleGraphs` | Set\<str\> | 詳細パネルで表示するグラフの ID セット |
| `evalDisplayMode` | str | 評価グラフ表示モード（`'cumulative'`=累計 / `'delta'`=日次増分） |
| `evalMetric` | str | 評価グラフで使うメトリクス（`'hyoka'`=評価件数 / `'point'`=評価ポイント） |
| `currentEvalHistory` | array | 詳細パネルで表示中の評価履歴データ |
| `currentEvalNovelTitle` | str | 詳細パネルで表示中の作品タイトル（グラフタイトル用） |
| `growthMetric` | str | 成長分析タブの Y 軸メトリクス（`'all_hyoka_cnt'` / `'all_point'` 等） |
| `growthPeriod` | str | 成長分析タブの比較期間（`'1d'` / `'7d'` / `'30d'`） |
| `growthValueType` | str | 成長値の種類（`'delta'`=増加数 / `'rate'`=増加率） |
| `growthTopN` | int | 成長分析タブで表示する上位件数 |

### 定数

| 定数名 | 値 | 説明 |
|---|---|---|
| `PAGE_SIZE` | 100 | 1ページあたりの表示件数 |
| `DEFAULT_WEIGHTS` | `{ genre:0, tag:0, rank:17, ... }` | スコア重みのデフォルト値。「デフォルトに戻す」のリセット基準 |
| `LS_KEY` | `'animeTool.weights'` | スコア重みを保存する localStorage キー |
| `LS_NORM_KEY` | `'animeTool.normParams'` | 正規化パラメータを保存する localStorage キー |
| `GRAPHS_LS_KEY` | `'animeTool.graphs'` | 表示グラフ選択を保存する localStorage キー |

### Chart.js インスタンス変数

| 変数名 | 対応グラフ |
|---|---|
| `comparisonChart` | 詳細比較パネルのメインスコアグラフ |
| `rankingTrendChart` | 月刊ランク推移グラフ |
| `evalTrendChart` | 評価件数・ポイント推移グラフ |
| `trendsChart` | Google Trends 推移グラフ |
| `topAnimeChart` | 類似アニメ Top5 横棒グラフ |
| `radarChart` | スコアレーダーチャート |
| `benchmarkChart` | 全作品比較パーセンタイルグラフ |
| `growthTrendChart` | 成長分析タブのトレンドグラフ |
| `correlationChart` | 成長分析タブの相関散布図 |

---

## 9. 日本語概念 → フィールド名 逆引き

「この数値はどのフィールドを見ればいいか」の逆引き表。

| 日本語概念 | 対応フィールド / キー |
|---|---|
| ブックマーク数・お気に入り登録数 | `bookmark_count_latest`（API: `fav_novel_cnt`） |
| 評価件数・いいね数の代替 | `all_hyoka_cnt_latest`（API: `all_hyoka_cnt`） |
| 月間評価ポイント・最近の盛り上がり | `monthly_point_latest`（API: `monthly_point`） |
| 累計閲覧数の代替・総合指標 | `global_point_latest`（API: `global_point`） |
| コア読者の定着度 | `bm_view_ratio`（= bookmark / global_point） |
| 満点基準値・スコア正規化の上限 | `norm_params.json` の各エントリ / `currentNormParams` |
| アニメ化との類似度スコア | `pattern1_best_score` / `pattern1_scores[].score` |
| 最も似ているアニメ | `pattern1_best_anime_id` |
| アニメ化発表日 | `anime_works.csv` の `announce_date` |
| 書籍化発売日 | `anime_works.csv` の `novel_publish_date` |
| 活性スコアの計算基準 | `general_lastup`（最終掲載日、`novels.csv`） |
| スコア重みのデフォルト | `PATTERN1_WEIGHTS`（Python）/ `DEFAULT_WEIGHTS`（JS） |
| ジャンルコードの日本語名 | `GENRE_LABEL` / `BIGGENRE_LABEL`（`narou_config.py`） |
| 成長率データ | `growth_metrics`（JSON）/ `growth_[metric]_[period]_[type]`（JS フラット形式） |
| エピソード数・話数 | `episode_count_latest`（API: `general_all_no`） |
| 感想件数 | `impression_cnt_latest`（API: `impression_cnt`） |
| 転生もの判定 | `is_isekai_tensei`（API: `istensei`） |
| 完結作判定 | `is_completed`（API: `end`） |
