# なろう小説アニメ化分析ツール - 開発ガイドライン

## プロジェクト概要

小説家になろうの月刊TOP1000作品を対象に、アニメ化済み/未アニメ化作品の数値推移・ジャンル・タグ・検索トレンドを比較し、アニメ化ポテンシャルの高い未アニメ化作品を発見するための静的Webツール。

**設計書・仕様書は必ず `RequirementsDocument/` フォルダを参照・更新すること。**

---

## 技術スタック

| 領域 | 技術 |
|---|---|
| データ収集 | Python 3.11（`scripts/`） |
| ホスティング | GitHub Pages（`docs/` をルートに設定） |
| フロントエンド | Vanilla JS + Chart.js + D3.js |
| CI/CD | GitHub Actions（毎日 JST 05:00 実行） |

---

## ディレクトリ構成

```
├── .github/workflows/
│   └── daily.yml              # 毎日定時実行（JST 05:00）
├── scripts/
│   ├── fetch_narou.py         # なろうAPI → novels.csv 更新（週次）
│   ├── fetch_snapshots.py     # daily_snapshots.csv 追記（毎日）
│   ├── fetch_trends.py        # pytrends → trends_cache.csv（週次）
│   ├── compute_similarity.py  # 類似度スコア計算 → JSON 出力（毎日）
│   └── backfill_wayback.py    # 過去データ補完（初回のみ手動実行）
├── data/
│   ├── novels.csv             # なろう小説マスター（自動管理）
│   ├── anime_works.csv        # アニメ作品マスター（手動管理）
│   ├── daily_snapshots.csv    # 時系列スナップショット（自動追記）
│   └── trends_cache.csv       # PyTrends キャッシュ（自動追記）
├── docs/                      # GitHub Pages ルート
│   ├── index.html
│   └── js/app.js
└── RequirementsDocument/      # 設計書（新規作成・変更時はここに記述）
    └── OverallDesignDocument.md
```

---

## 設計書の運用ルール

- 新機能の実装前に `RequirementsDocument/OverallDesignDocument.md` を必ず確認すること。
- 設計に変更が生じた場合は実装と同時に設計書を更新すること。
- 新たな仕様書や機能設計書は `RequirementsDocument/` フォルダに追加すること。

---

## コーディング規約

### 共通

- コードのコメントとエラーログメッセージは日本語で記述すること。
- ハードコーディングは絶対に必要な場合を除き避けること（APIエンドポイント・ファイルパス等は定数化）。

### Python

- PEP8 準拠。型ヒント（`typing`）を積極的に使用すること。
- スクリプトは単体でも `python scripts/xxx.py` で実行できる設計にすること。
- 失敗時はスクリプトを停止せず、`fetch_status=skip` 等で記録して続行すること（特に `fetch_trends.py`）。
- pytrends はレート制限が厳しいため、1リクエストごとに 30〜60 秒のスリープを挿入すること。

### JavaScript

- ES2020+ 構文を使用すること。
- GitHub Pages の静的構成のため、外部APIの実行時呼び出しは禁止（データはすべて事前生成済みの JSON を `fetch()` で読む）。

---

## データ管理ルール

- `data/` 配下の CSV はスクリプトで自動管理される。`anime_works.csv` のみ手動管理。
- 手動管理ファイルの変更時はスキーマを `RequirementsDocument/OverallDesignDocument.md` で確認すること。
- `data/` 配下の生成済み JSON（`similarity.json` 等）は `.gitignore` に含めないこと（GitHub Pages から参照されるため）。
- なろう API は累計 View 数のみ返す。差分計算で日次 View 数を算出し `daily_view` に格納すること。

---

## 類似度スコアの扱い

- 重みは仮説ベース。初期実装後、10〜20タイトルで直感と照合しながらチューニングすること。
- スコア計算の詳細は `RequirementsDocument/OverallDesignDocument.md` の「類似度スコアの設計」を参照。
- Trends スコアは相対値（0〜100）のため同一期間内の比較にのみ使用すること。

---

## 実装優先順位

`RequirementsDocument/OverallDesignDocument.md` の「実装着手の優先順位」セクションを参照すること。

1. `anime_works.csv` 手動作成（B: 20〜30タイトル、C: 5〜10タイトル）
2. `backfill_wayback.py` 実装・実行
3. `fetch_narou.py` で `novels.csv` 作成
4. `fetch_snapshots.py` を GitHub Actions に乗せる
5. `fetch_trends.py` 追加
6. `compute_similarity.py` 実装
7. フロントエンド実装

---

## 既知の制約

| 制約 | 対処方針 |
|---|---|
| pytrends は非公式・不安定 | `fetch_status=skip` で欠損許容 |
| なろう API は累計 View 数のみ | 差分計算で日次算出、初日は `null` |
| Wayback Machine のアーカイブは疎 | ランキング順位補完のみ、View 数は期待しない |
| Trends スコアは相対値 | 同一期間内の相対比較にのみ使用 |
