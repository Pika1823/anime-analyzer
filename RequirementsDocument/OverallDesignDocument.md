# なろう小説アニメ化分析ツール 設計書

## 概要

小説家になろうの月刊TOP1000作品を対象に、アニメ化済み作品と未アニメ化作品の数値推移・ジャンル・タグ・検索トレンドを比較し、アニメ化ポテンシャルの高い未アニメ化作品を発見するための分析Webツール。

---

## 分析の目的と仮説

**目的**：アニメ化済み作品と数値的・属性的に類似している未アニメ化作品を定量的に特定する。

**仮説**：アニメ化前の一定期間における View 数推移・ブックマーク比率・ジャンル・タグの組み合わせに共通パターンが存在し、それを未アニメ化作品に当てはめることでポテンシャルを推定できる。

**重要な前提**：類似度スコアは仮説に基づく推定値であり、実際のアニメ化判断の根拠とはならない。スコアは初期重みを設定後、10〜20タイトルで直感と照合しながらチューニングする。

---

## 対象エンティティ

3種類のエンティティを扱う。

### A. なろう小説（メインデータ）
- なろう API で取得する月刊 TOP1000 作品
- View 数・ブックマーク・ランキング・ジャンル・タグを保持
- アニメ化済みフラグ（`is_anime`）で B との判別を行う

### B. アニメ化済みなろう原作
- A の部分集合
- A のデータをすべて継承した上で、放送日・話数・スタジオ等のアニメ情報を追加
- 比較グラフの「基準線」となる
- 類似度計算・PyTrends 比較ともに有効

### C. 外部アニメ（なろう原作でない）
- 手動登録する最近の人気アニメ（SPY×FAMILY、進撃の巨人 等）
- なろうデータ（View 数・ランキング等）は存在しない
- **PyTrends ベースの比較と類似度のみ有効**
- ジャンル・タグは手動設定

---

## データモデル

### ファイル一覧

```
data/
├── novels.csv             # A. なろう小説マスター（週次更新）
├── anime_works.csv        # B + C. アニメ作品マスター（手動管理）
├── daily_snapshots.csv    # A の時系列スナップショット（毎日追記）
├── trends_cache.csv       # A + B + C の PyTrends キャッシュ（週次）
└── (generated)
    ├── similarity.json    # 類似度スコア計算結果
    ├── novels_merged.json # フロントエンド用マージ済みデータ
    └── trends_merged.json # フロントエンド用トレンドデータ
```

---

### novels.csv

なろう API から週次で更新するマスターデータ。

| カラム名 | 型 | 説明 |
|---|---|---|
| ncode | string | PK。作品固有ID（例: N1234AB） |
| title | string | 作品タイトル |
| author | string | 著者名 |
| genre | string | なろうの大分類ジャンル |
| tags | string | カンマ区切りのタグ一覧 |
| is_anime | boolean | アニメ化済みフラグ |
| anime_id | string | FK。anime_works.csv への参照（nullable） |
| monthly_rank_latest | integer | 直近の月刊ランキング順位 |
| bookmark_count_latest | integer | 直近のブックマーク数 |
| updated_at | date | レコード更新日 |

---

### anime_works.csv

B（なろう原作アニメ）と C（外部アニメ）を一括管理する。`source_type` で判別する。

| カラム名 | 型 | 説明 |
|---|---|---|
| anime_id | string | PK |
| anime_title | string | アニメタイトル（表示用） |
| title_short | string | 略称（例: 転スラ）。PyTrends キーワードとして使用 |
| title_full | string | 正式名称（例: 転生したらスライムだった件）。PyTrends キーワードとして使用 |
| ncode | string | FK。novels.csv への参照（source_type=narou のみ） |
| source_type | enum | `narou` / `other` |
| air_date | date | 放送開始日 |
| season | string | 放送季（例: 2023Q4） |
| studio | string | 制作スタジオ |
| genre_manual | string | 手動設定ジャンル（C 用・B も補完可） |
| tags_manual | string | 手動設定タグ（C 用） |

**初期登録推奨タイトル（B）**：転スラ・リゼロ・無職転生・オーバーロード・本好きの下剋上・陰の実力者になりたくて・ひとりぼっちの異世界攻略・蜘蛛ですが何か？ 等

**初期登録推奨タイトル（C）**：SPY×FAMILY・進撃の巨人・チェンソーマン・呪術廻戦・鬼滅の刃 等

---

### daily_snapshots.csv

毎日 GitHub Actions で追記するメインの時系列データ。1行 = 1作品の1日分。

| カラム名 | 型 | 説明 |
|---|---|---|
| date | date | スナップショット取得日 |
| ncode | string | FK → novels.csv |
| cumulative_view | integer | API から取得する累計 View 数 |
| daily_view | integer | 前日比の差分（スクリプトで計算） |
| bookmark_count | integer | その日のブックマーク数 |
| monthly_rank | integer | 月刊ランキング順位 |
| weekly_rank | integer | 週間ランキング順位 |

> **注意**：なろう API が返すのは累計 View 数のみ。`daily_view` は前日の `cumulative_view` との差分をスクリプトで計算して付与する。

---

### trends_cache.csv

pytrends から取得した検索ボリューム推移のキャッシュ。A・B・C のすべてを対象とする。

| カラム名 | 型 | 説明 |
|---|---|---|
| week_start | date | 週の開始日（月曜） |
| id | string | ncode または anime_id |
| id_type | enum | `novel` / `anime` |
| keyword_used | string | 検索に使用したキーワード（`title_short` または `title_full` の値） |
| trend_score | integer | 0〜100 の相対スコア |
| fetch_status | enum | `ok` / `skip`（取得失敗時） |
| region | string | `JP` 固定 |

**主キー**：`(week_start, id, keyword_used)` — 同一作品・同一週に略称と正式名称の2行が入る。

**集計モード**（フロントエンド・類似度計算で使用）：
- **合算（平均）**: 同一 `(week_start, id)` の `ok` 行のスコアを平均する
- **略称のみ**: `keyword_used = title_short` の行のみ使用
- **正式名称のみ**: `keyword_used = title_full` の行のみ使用

> **pytrends の制約**：非公式ライブラリのためレート制限が厳しい。取得失敗時は `fetch_status=skip` で記録し、欠損扱いにする。類似度計算は `ok` の週のみで行う。スコアは相対値（0〜100）であり絶対的な検索数ではない。

---

## 類似度スコアの設計

比較対象の組み合わせによって使用できる特徴量が異なる。

### パターン1：未アニメ化なろう vs アニメ化済みなろう（メイン）

| 特徴量 | 重み | 説明 |
|---|---|---|
| ジャンル一致 | 30% | 大分類が一致するか（バイナリ） |
| タグ Jaccard 係数 | 25% | タグ集合の類似度 |
| ランク帯（アニメ化時点） | 20% | 1〜100 / 101〜300 / 301〜1000 の帯 |
| ブックマーク / View 比率 | 15% | コア読者の定着度 |
| View 成長率（直近6ヶ月） | 10% | 注目度の上昇傾向 |

### パターン2：未アニメ化なろう vs 外部アニメ（Trends のみ）

| 特徴量 | 重み | 説明 |
|---|---|---|
| Trends 時系列の相関係数 | 60% | 週次スコアの Pearson 相関 |
| ジャンル / タグ（手動設定） | 40% | anime_works.csv の手動値と比較 |

### パターン3：アニメ化済みなろう vs 外部アニメ

| 特徴量 | 重み | 説明 |
|---|---|---|
| Trends 時系列の相関係数 | 70% | 週次スコアの Pearson 相関 |
| ジャンル / タグ | 30% | 双方の設定値で比較 |

> **重みは仮説**。初期実装後、「転スラに最も似ているのはどれか」等の直感チェックを10〜20タイトルで行い、結果が合わない場合はチューニングする。

---

## システムアーキテクチャ

```
GitHub Repository
├── .github/workflows/
│   └── daily.yml              # 毎日定時実行
├── scripts/
│   ├── fetch_narou.py         # なろうAPI → novels.csv 更新
│   ├── fetch_snapshots.py     # daily_snapshots.csv 追記
│   ├── fetch_trends.py        # pytrends → trends_cache.csv 追記
│   ├── compute_similarity.py  # 類似度スコア計算 → JSON 出力
│   └── backfill_wayback.py    # 【初回のみ】過去データ補完
├── data/
│   ├── novels.csv
│   ├── anime_works.csv        # 手動管理
│   ├── daily_snapshots.csv
│   └── trends_cache.csv
└── docs/                      # GitHub Pages ルート
    ├── index.html
    └── js/
        └── app.js
```

---

## 各スクリプトの仕様

### fetch_narou.py（週次）

- なろう API（`https://api.syosetu.com/novelapi/api/`）から月刊ランキング TOP1000 を取得
- `out=jsonlite` 形式、`order=monthlypoint` で取得
- 既存の novels.csv に upsert（ncode をキーに更新・追加）
- `is_anime` フラグは anime_works.csv の ncode 一致で自動付与

### fetch_snapshots.py（毎日）

- novels.csv の全 ncode を対象にスナップショット取得
- `cumulative_view` は API の `allcount` フィールドを使用
- 前日レコードとの差分で `daily_view` を計算
- 初日（前日レコードなし）は `daily_view = null`

### fetch_trends.py（週次）

- novels.csv の全 ncode と anime_works.csv の全 anime_id を対象
- keyword は原則としてタイトル文字列を使用
- pytrends の `build_payload` でタイムフレームを `today 3-m` に設定
- レート制限回避のため1リクエストごとに 30〜60 秒スリープ
- 失敗時は `fetch_status=skip` で記録してスキップ（スクリプトを止めない）

### backfill_wayback.py（初回のみ・手動実行）

- Wayback Machine CDX API でなろうランキングページのアーカイブ URL を列挙
- 各アーカイブ HTML をパースしてランキング情報を抽出
- 抽出結果を daily_snapshots.csv に追記
- **制約**：アーカイブは週数回程度しか保存されていない日付が多く、View 数は取れないことが多い。ランキング順位の過去データとして利用する

### compute_similarity.py（毎日・fetch 後）

- novels.csv・anime_works.csv・daily_snapshots.csv・trends_cache.csv を読み込み
- 上記の類似度スコア計算ロジックを実行
- 結果を `data/similarity.json` として出力
- あわせて `novels_merged.json`・`trends_merged.json` を生成（フロントエンド用）

---

## GitHub Actions ワークフロー

```yaml
# .github/workflows/daily.yml
name: Daily data update
on:
  schedule:
    - cron: '0 20 * * *'  # 毎日 JST 05:00
  workflow_dispatch:       # 手動実行も可能

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r scripts/requirements.txt
      - run: python scripts/fetch_narou.py       # 週次（曜日チェックをスクリプト内で行う）
      - run: python scripts/fetch_snapshots.py
      - run: python scripts/fetch_trends.py      # 週次（同上）
      - run: python scripts/compute_similarity.py
      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/ docs/
          git diff --staged --quiet || git commit -m "chore: daily data update $(date '+%Y-%m-%d')"
          git push
```

---

## フロントエンド仕様

### 技術スタック

- Vanilla JS + Chart.js（グラフ）+ D3.js（補助）
- `fetch()` で data/ 配下の JSON を読み込む静的構成
- GitHub Pages でホスト（docs/ をルートに設定）
- 外部 API 呼び出しなし（データはすべて事前生成済みの JSON）

### 3つのメインビュー

#### ビュー1：類似度ランキング

- 未アニメ化作品をパターン1のスコア降順で一覧表示
- フィルタ：ジャンル・タグ・ランク帯・スコア閾値
- 行クリックでビュー2（比較グラフ）に遷移
- 比較対象のアニメ化済み作品を変更可能（デフォルト：スコア最高の作品）

#### ビュー2：比較グラフ（核心）

- **X 軸はアニメ放送開始日を 0 週とした相対時間軸**（絶対日付では比較不可）
- Y 軸左：週次 View 数差分
- Y 軸右：月刊ランキング順位（反転。1位が上）
- アニメ化済みなろう = 実線、未アニメ化なろう = 破線
- 外部アニメの Trends スコアを第3軸として点線で重ねる
- 放送開始日に縦線マーカー
- 複数作品の同時重ねあわせに対応（最大5作品程度）

#### ビュー3：Trends 比較

- C（外部アニメ）との比較専用画面
- なろう作品と外部アニメの Trends スコアを重ねて表示
- `fetch_status=skip` の週は欠損として点線で補間

---

## 実装着手の優先順位

| 順序 | タスク | 理由 |
|---|---|---|
| 1 | `anime_works.csv` を手動作成（B: 20〜30タイトル、C: 5〜10タイトル） | これがないと類似度計算もグラフも動かない |
| 2 | `backfill_wayback.py` を書いて実行 | 過去データ収集に時間がかかるため早めに着手 |
| 3 | `fetch_narou.py` で novels.csv を作成 | マスターデータの基盤 |
| 4 | `fetch_snapshots.py` を GitHub Actions に乗せる | データ積み上げ開始 |
| 5 | `fetch_trends.py` を追加 | 失敗許容なので後回し可 |
| 6 | `compute_similarity.py` を実装 | データが揃ってから |
| 7 | フロントエンド実装 | 4が数週間回ってから着手でも遅くない |

---

## 既知の制約と対処方針

| 制約 | 対処 |
|---|---|
| pytrends は非公式・不安定 | `fetch_status=skip` で欠損許容。Trends 依存の類似度は参考値扱い |
| なろう API は累計 View 数のみ返す | 差分計算で日次 View 数を算出。初日は null |
| Wayback Machine のアーカイブは疎 | ランキング順位の補完に留める。View 数の過去データは期待しない |
| タイトルの名寄せ（なろう ↔ AniList 等） | anime_works.csv で手動管理し、ncode を直接指定することで回避 |
| Trends スコアは相対値（0〜100）であり絶対数ではない | 同一期間内の相対比較にのみ使用する |

---

## 用語定義

| 用語 | 定義 |
|---|---|
| ncode | なろうの作品固有 ID（例: N1234AB） |
| 月刊 TOP1000 | なろうの月間ポイントランキング上位1000作品 |
| BM / View 比率 | ブックマーク数 ÷ 累計 View 数。コア読者の定着度の指標 |
| 相対時間軸 | アニメ放送開始日を 0 週として前後に展開した時間軸。作品間の比較に使用 |
| Jaccard 係数 | 2つの集合の類似度。共通要素数 ÷ 全要素数（重複除く） |
| ランク帯 | 1〜100位 / 101〜300位 / 301〜1000位 の3区分 |