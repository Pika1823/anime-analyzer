"""
なろう作品の書籍化情報を Amazon Japan から取得して book_works.csv に保存する。
GitHub Actions の手動トリガーから実行する（定期実行には追加しない）。

実行例:
  python scripts/fetch_books.py                # novels.csv の全作品を対象
  python scripts/fetch_books.py --ncode N1234AB  # 特定の Nコード
  python scripts/fetch_books.py --title "転スラ" # タイトル直接指定
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))

from utils import BOOK_WORKS_CSV, NOVELS_CSV, get_logger, load_csv, save_csv

logger = get_logger(__name__)

# Amazon Japan 検索エンドポイント
AMAZON_SEARCH_URL = "https://www.amazon.co.jp/s"
# Amazon Japan 商品ページベースURL
AMAZON_PRODUCT_BASE = "https://www.amazon.co.jp/dp"

# スクレイピング設定
AMAZON_SLEEP_MIN = 3.0
AMAZON_SLEEP_MAX = 6.0
AMAZON_TIMEOUT = 20
AMAZON_RETRY = 2
# この閾値以上の類似度なら書名一致とみなす
TITLE_MATCH_THRESHOLD = 0.50

# Chrome ライクなリクエストヘッダー（Bot 検知対策）
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}

# book_works.csv のスキーマ定義
BOOK_WORKS_COLUMNS = [
    "ncode",
    "narou_title",
    "is_book",
    "amazon_asin_vol1",
    "amazon_url_vol1",
    "amazon_title_vol1",
    "amazon_rating",
    "amazon_review_count",
    "match_score",
    "checked_at",
]


def _sleep() -> None:
    """Amazon レート制限対策のランダムスリープ。"""
    time.sleep(random.uniform(AMAZON_SLEEP_MIN, AMAZON_SLEEP_MAX))


def _get(session: requests.Session, url: str, params: dict | None = None) -> str | None:
    """GET リクエストを実行してレスポンス HTML を返す。失敗時は None を返す。"""
    for attempt in range(1, AMAZON_RETRY + 1):
        try:
            resp = session.get(url, params=params, timeout=AMAZON_TIMEOUT)
            if resp.status_code == 503:
                logger.warning("Amazon 503 (Bot 検知) attempt=%d URL=%s", attempt, url)
                _sleep()
                continue
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            logger.warning("Amazon リクエスト失敗 attempt=%d: %s", attempt, e)
            if attempt < AMAZON_RETRY:
                _sleep()
    return None


def _title_score(a: str, b: str) -> float:
    """2つのタイトルの類似度スコアを返す（0.0〜1.0）。"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def search_amazon_book(
    session: requests.Session,
    title: str,
) -> dict | None:
    """Amazon Japan で "{title} 1" を検索し、最も類似度の高い書籍を返す。

    Args:
        session: requests.Session
        title: 検索するなろう作品タイトル

    Returns:
        {asin, amazon_title, match_score} または None（見つからない or 閾値未満）
    """
    query = f"{title} 1"
    params = {
        "k": query,
        "i": "stripbooks",  # 書籍カテゴリ
        "__mk_ja_JP": "カタカナ",
    }
    html = _get(session, AMAZON_SEARCH_URL, params=params)
    if not html:
        logger.warning("Amazon 検索 HTML 取得失敗: %s", title)
        return None

    soup = BeautifulSoup(html, "lxml")
    results = soup.select("[data-component-type='s-search-result'][data-asin]")
    if not results:
        # セレクタが Amazon のレイアウト変更で動かない場合のフォールバック
        results = soup.select("[data-asin]:not([data-asin=''])")

    best_asin: str | None = None
    best_title: str | None = None
    best_score = 0.0

    for item in results[:10]:  # 上位10件のみ確認
        asin = item.get("data-asin", "").strip()
        if not asin:
            continue

        # タイトル要素の取得（複数セレクタでフォールバック）
        title_el = (
            item.select_one("h2 .a-text-normal")
            or item.select_one("h2 a span")
            or item.select_one(".a-size-medium.a-color-base.a-text-normal")
        )
        if not title_el:
            continue

        candidate_title = title_el.get_text(strip=True)
        score = _title_score(title, candidate_title)
        if score > best_score:
            best_score = score
            best_asin = asin
            best_title = candidate_title

    if best_score < TITLE_MATCH_THRESHOLD or not best_asin:
        logger.info("Amazon 書名マッチなし (best_score=%.3f): %s", best_score, title)
        return None

    logger.info(
        "Amazon マッチ: '%s' → '%s' (ASIN=%s, score=%.3f)",
        title, best_title, best_asin, best_score,
    )
    return {"asin": best_asin, "amazon_title": best_title, "match_score": round(best_score, 4)}


def fetch_product_detail(session: requests.Session, asin: str) -> dict:
    """Amazon 商品ページから星評価・レビュー件数を取得する。

    Args:
        session: requests.Session
        asin: Amazon ASIN

    Returns:
        {amazon_rating: float|None, amazon_review_count: int|None}
    """
    url = f"{AMAZON_PRODUCT_BASE}/{asin}"
    html = _get(session, url)
    if not html:
        logger.warning("Amazon 商品ページ取得失敗: ASIN=%s", asin)
        return {"amazon_rating": None, "amazon_review_count": None}

    soup = BeautifulSoup(html, "lxml")

    # 星評価の取得（例: "5つ星のうち4.5"）
    rating: float | None = None
    rating_el = soup.select_one("span[data-hook='rating-out-of-text']")
    if not rating_el:
        rating_el = soup.select_one("#averageCustomerReviews .a-icon-alt")
    if rating_el:
        text = rating_el.get_text(strip=True)
        for part in text.split():
            try:
                rating = float(part)
                if 0.0 <= rating <= 5.0:
                    break
                rating = None
            except ValueError:
                continue

    # レビュー件数の取得（例: "123個の評価"）
    review_count: int | None = None
    review_el = soup.select_one("span[data-hook='total-review-count']")
    if not review_el:
        review_el = soup.select_one("#acrCustomerReviewText")
    if review_el:
        text = review_el.get_text(strip=True).replace(",", "").replace("，", "")
        for part in text.split():
            try:
                review_count = int(part)
                break
            except ValueError:
                continue

    logger.info("商品ページ取得: ASIN=%s rating=%s reviews=%s", asin, rating, review_count)
    return {"amazon_rating": rating, "amazon_review_count": review_count}


def build_book_row(
    ncode: str,
    title: str,
    search_result: dict | None,
    product_detail: dict | None,
) -> dict:
    """book_works.csv の 1 行分の辞書を生成する。"""
    today = date.today().isoformat()
    if search_result is None:
        return {
            "ncode": ncode,
            "narou_title": title,
            "is_book": False,
            "amazon_asin_vol1": None,
            "amazon_url_vol1": None,
            "amazon_title_vol1": None,
            "amazon_rating": None,
            "amazon_review_count": None,
            "match_score": 0.0,
            "checked_at": today,
        }

    asin = search_result["asin"]
    return {
        "ncode": ncode,
        "narou_title": title,
        "is_book": True,
        "amazon_asin_vol1": asin,
        "amazon_url_vol1": f"{AMAZON_PRODUCT_BASE}/{asin}",
        "amazon_title_vol1": search_result.get("amazon_title"),
        "amazon_rating": product_detail.get("amazon_rating") if product_detail else None,
        "amazon_review_count": product_detail.get("amazon_review_count") if product_detail else None,
        "match_score": search_result.get("match_score", 0.0),
        "checked_at": today,
    }


def upsert_book_works(existing: pd.DataFrame, new_rows: list[dict]) -> pd.DataFrame:
    """ncode をキーに book_works.csv を upsert する。"""
    if not new_rows:
        return existing

    new_df = pd.DataFrame(new_rows, columns=BOOK_WORKS_COLUMNS)
    if existing.empty:
        return new_df

    existing_idx = existing.set_index("ncode")
    new_idx = new_df.set_index("ncode")

    for col in existing_idx.columns.intersection(new_idx.columns):
        if existing_idx[col].dtype != new_idx[col].dtype:
            existing_idx[col] = existing_idx[col].astype(object)
            new_idx[col] = new_idx[col].astype(object)

    existing_idx.update(new_idx)
    new_only = new_idx.index.difference(existing_idx.index)
    return pd.concat([existing_idx, new_idx.loc[new_only]]).reset_index()


def process_novels(
    novels_df: pd.DataFrame,
    existing: pd.DataFrame,
    skip_cached: bool,
) -> list[dict]:
    """novels_df の各作品を Amazon で検索して結果リストを返す。"""
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    today = date.today().isoformat()

    # 取得済み ncode のセット（skip_cached=True の場合はスキップ）
    cached_ncodes: set[str] = set()
    if skip_cached and not existing.empty:
        cached_ncodes = set(existing["ncode"].astype(str))

    new_rows: list[dict] = []
    total = len(novels_df)

    for i, (_, row) in enumerate(novels_df.iterrows()):
        ncode = str(row.get("ncode", ""))
        title = str(row.get("title", ""))
        if not ncode or not title or title == "nan":
            continue
        if ncode in cached_ncodes:
            logger.debug("取得済みのためスキップ: %s (%s)", title, ncode)
            continue

        logger.info("[%d/%d] 検索: %s (%s)", i + 1, total, title, ncode)

        search_result = search_amazon_book(session, title)
        _sleep()

        product_detail = None
        if search_result:
            product_detail = fetch_product_detail(session, search_result["asin"])
            _sleep()

        row_dict = build_book_row(ncode, title, search_result, product_detail)
        new_rows.append(row_dict)
        logger.info(
            "  → is_book=%s rating=%s reviews=%s",
            row_dict["is_book"],
            row_dict["amazon_rating"],
            row_dict["amazon_review_count"],
        )

    return new_rows


def main() -> None:
    """エントリポイント。"""
    parser = argparse.ArgumentParser(description="なろう作品の書籍化情報を Amazon から取得する")
    parser.add_argument("--ncode", default="", help="特定の Nコード（例: N1234AB）")
    parser.add_argument("--title", default="", help="作品タイトル直接指定（ncode 未指定時に使用）")
    parser.add_argument(
        "--skip-cached",
        action="store_true",
        default=True,
        help="book_works.csv に既存エントリがある ncode はスキップする（デフォルト: true）",
    )
    parser.add_argument(
        "--no-skip-cached",
        dest="skip_cached",
        action="store_false",
        help="既存エントリも再取得する",
    )
    args = parser.parse_args()

    novels_df = load_csv(NOVELS_CSV, dtype={"ncode": str})
    existing = load_csv(BOOK_WORKS_CSV, dtype={"ncode": str})

    # 処理対象を絞り込む
    if args.ncode:
        ncode_upper = args.ncode.upper()
        target = novels_df[novels_df["ncode"].str.upper() == ncode_upper]
        if target.empty:
            logger.error("novels.csv に ncode=%s が見つかりません", args.ncode)
            return
        logger.info("対象: ncode=%s", ncode_upper)
    elif args.title:
        # タイトル指定の場合は仮の ncode を使用して直接処理
        ncode_tmp = "MANUAL"
        session = requests.Session()
        session.headers.update(REQUEST_HEADERS)
        logger.info("タイトル直接指定: %s", args.title)
        search_result = search_amazon_book(session, args.title)
        _sleep()
        product_detail = None
        if search_result:
            product_detail = fetch_product_detail(session, search_result["asin"])
        row = build_book_row(ncode_tmp, args.title, search_result, product_detail)
        logger.info("結果: %s", row)
        return
    else:
        if novels_df.empty:
            logger.error("novels.csv が空またはファイルが存在しません")
            return
        target = novels_df
        logger.info("novels.csv 全件を対象: %d 件", len(target))

    new_rows = process_novels(target, existing, skip_cached=args.skip_cached)
    if not new_rows:
        logger.info("新規取得なし")
        return

    merged = upsert_book_works(existing, new_rows)
    save_csv(merged, BOOK_WORKS_CSV)
    logger.info("book_works.csv 保存完了: %d 件", len(merged))

    # 結果サマリーをログ出力
    book_count = sum(1 for r in new_rows if r.get("is_book"))
    logger.info("今回の取得: 計%d件, 書籍化あり=%d件, 書籍化なし=%d件",
                len(new_rows), book_count, len(new_rows) - book_count)


if __name__ == "__main__":
    main()
