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
import re
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


def _parse_rating(text: str) -> float | None:
    """評価テキストから星評価数値を抽出する。

    Amazon Japan の形式例:
      "5つ星のうち4.5"  →  4.5
      "4.3 out of 5"    →  4.3
    """
    # "のうち" の後の数値を優先取得（例: "5つ星のうち4.5"）
    m = re.search(r'のうち\s*(\d+\.?\d*)', text)
    if m:
        try:
            v = float(m.group(1))
            if 0.0 <= v <= 5.0:
                return v
        except ValueError:
            pass
    # フォールバック: テキスト中の小数 or 整数を順に試す
    for raw in re.findall(r'\d+\.\d+|\d+', text):
        try:
            v = float(raw)
            if 0.0 <= v <= 5.0:
                return v
        except ValueError:
            continue
    return None


def _parse_review_count(text: str) -> int | None:
    """レビュー件数テキストから整数を抽出する。

    Amazon Japan の形式例:
      "1,234個の評価"  →  1234
      "567件のレビュー" →  567
    """
    # カンマ区切り数値を優先取得
    m = re.search(r'([\d,]+)\s*(?:個|件)', text)
    if m:
        try:
            return int(m.group(1).replace(',', ''))
        except ValueError:
            pass
    # フォールバック: 最初に現れる数値列
    m = re.search(r'[\d,]+', text)
    if m:
        try:
            return int(m.group(0).replace(',', ''))
        except ValueError:
            pass
    return None


def _is_captcha_page(soup: BeautifulSoup) -> bool:
    """CAPTCHA ページかどうかを判定する。"""
    return bool(
        soup.select_one("form[action='/errors/validateCaptcha']")
        or "captcha" in (soup.title.string or "").lower()
        if soup.title else False
    )


def search_amazon_book(
    session: requests.Session,
    title: str,
) -> dict | None:
    """Amazon Japan で "{title} 1" を検索し、最も類似度の高い書籍を返す。

    検索結果ページは静的 HTML に評価・レビュー数が含まれているため、
    マッチした商品の評価もここで同時に取得する。

    Args:
        session: requests.Session
        title: 検索するなろう作品タイトル

    Returns:
        {asin, amazon_title, match_score, amazon_rating, amazon_review_count}
        または None（見つからない or 閾値未満）
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

    if _is_captcha_page(soup):
        logger.warning("Amazon CAPTCHA 検出（検索）: %s", title)
        return None

    results = soup.select("[data-component-type='s-search-result'][data-asin]")
    if not results:
        results = soup.select("[data-asin]:not([data-asin=''])")

    best_asin: str | None = None
    best_title: str | None = None
    best_score = 0.0
    best_item = None

    for item in results[:10]:
        asin = item.get("data-asin", "").strip()
        if not asin:
            continue

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
            best_item = item

    if best_score < TITLE_MATCH_THRESHOLD or not best_asin or best_item is None:
        logger.info("Amazon 書名マッチなし (best_score=%.3f): %s", best_score, title)
        return None

    # 検索結果ページから評価・レビュー数を取得（静的 HTML に含まれる）
    rating: float | None = None
    review_count: int | None = None

    rating_el = (
        best_item.select_one("i.a-icon-star-small .a-icon-alt")
        or best_item.select_one("span.a-icon-alt")
        or best_item.select_one("i.a-icon-star .a-icon-alt")
    )
    if rating_el:
        rating = _parse_rating(rating_el.get_text(strip=True))

    review_el = (
        best_item.select_one("span.a-size-base.s-underline-text")
        or best_item.select_one("a[href*='customerReviews'] span.a-size-base")
        or best_item.select_one(".a-size-base[aria-label]")
    )
    if review_el:
        review_count = _parse_review_count(review_el.get_text(strip=True))

    logger.info(
        "Amazon マッチ: '%s' → '%s' (ASIN=%s, score=%.3f, rating=%s, reviews=%s)",
        title, best_title, best_asin, best_score, rating, review_count,
    )
    return {
        "asin": best_asin,
        "amazon_title": best_title,
        "match_score": round(best_score, 4),
        "amazon_rating": rating,
        "amazon_review_count": review_count,
    }


def fetch_product_detail(session: requests.Session, asin: str) -> dict:
    """Amazon 商品ページから星評価・レビュー件数を取得する。

    検索結果ページで取得できなかった場合のフォールバックとして使用する。
    評価セクションは JavaScript 動的生成のため取得できないケースもある。

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

    if _is_captcha_page(soup):
        logger.warning("Amazon CAPTCHA 検出（商品ページ）: ASIN=%s", asin)
        return {"amazon_rating": None, "amazon_review_count": None}

    rating: float | None = None
    # 複数セレクタでフォールバック（Amazon は JS 動的生成のため取れない場合あり）
    for sel in [
        "span[data-hook='rating-out-of-text']",
        "#averageCustomerReviews .a-icon-alt",
        "#acrPopover .a-icon-alt",
        "span.a-icon-alt",
    ]:
        el = soup.select_one(sel)
        if el:
            v = _parse_rating(el.get_text(strip=True))
            if v is not None:
                rating = v
                break

    review_count: int | None = None
    for sel in [
        "span[data-hook='total-review-count']",
        "#acrCustomerReviewText",
        "a[data-hook='see-all-reviews-link-foot']",
    ]:
        el = soup.select_one(sel)
        if el:
            v = _parse_review_count(el.get_text(strip=True))
            if v is not None:
                review_count = v
                break

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
    # 検索結果ページ取得値を優先し、取れなければ商品ページ取得値を使う
    rating = search_result.get("amazon_rating")
    reviews = search_result.get("amazon_review_count")
    if rating is None and product_detail:
        rating = product_detail.get("amazon_rating")
    if reviews is None and product_detail:
        reviews = product_detail.get("amazon_review_count")
    return {
        "ncode": ncode,
        "narou_title": title,
        "is_book": True,
        "amazon_asin_vol1": asin,
        "amazon_url_vol1": f"{AMAZON_PRODUCT_BASE}/{asin}",
        "amazon_title_vol1": search_result.get("amazon_title"),
        "amazon_rating": rating,
        "amazon_review_count": reviews,
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

        # 検索結果ページで評価が取れなかった場合のみ商品ページを追加リクエスト
        product_detail = None
        if search_result and (
            search_result.get("amazon_rating") is None
            or search_result.get("amazon_review_count") is None
        ):
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


def update_ratings(existing: pd.DataFrame) -> list[dict]:
    """is_book=True の作品の Amazon 評価・レビュー数のみを再取得して返す。

    Amazon 検索は行わず、book_works.csv に保存済みの ASIN を直接使って
    商品ページから最新の評価値を取得する。

    Args:
        existing: 現在の book_works.csv DataFrame

    Returns:
        更新後の行辞書リスト（is_book=True の作品分のみ）
    """
    if existing.empty:
        logger.info("book_works.csv が空です。update-only モードをスキップします")
        return []

    # is_book=True の行のみ対象
    book_mask = existing["is_book"].astype(str).str.lower() == "true"
    book_rows = existing[book_mask]

    if book_rows.empty:
        logger.info("書籍化フラグが立っている作品がありません")
        return []

    logger.info("評価再取得対象: %d 件", len(book_rows))
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    updated: list[dict] = []
    total = len(book_rows)

    for i, (_, row) in enumerate(book_rows.iterrows()):
        asin = str(row.get("amazon_asin_vol1") or "").strip()
        title = str(row.get("narou_title") or "")
        ncode = str(row.get("ncode") or "")

        if not asin or asin == "nan":
            logger.warning("[%d/%d] ASIN 未登録のためスキップ: %s (%s)", i + 1, total, title, ncode)
            continue

        logger.info("[%d/%d] 評価再取得: %s (ASIN=%s)", i + 1, total, title, asin)
        detail = fetch_product_detail(session, asin)
        _sleep()

        updated_row = row.to_dict()
        updated_row["amazon_rating"] = detail.get("amazon_rating")
        updated_row["amazon_review_count"] = detail.get("amazon_review_count")
        updated_row["checked_at"] = date.today().isoformat()
        updated.append(updated_row)
        logger.info(
            "  → rating=%s reviews=%s",
            updated_row["amazon_rating"],
            updated_row["amazon_review_count"],
        )

    return updated


def main() -> None:
    """エントリポイント。"""
    parser = argparse.ArgumentParser(description="なろう作品の書籍化情報を Amazon から取得する")
    parser.add_argument("--ncode", default="", help="特定の Nコード（例: N1234AB）")
    parser.add_argument("--title", default="", help="作品タイトル直接指定（ncode 未指定時に使用）")
    parser.add_argument(
        "--update-only",
        action="store_true",
        default=False,
        help="書籍化フラグ済み作品の評価・レビュー数のみ再取得する（新規検索なし）",
    )
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

    existing = load_csv(BOOK_WORKS_CSV, dtype={"ncode": str})

    # --- 評価更新専用モード ---
    if args.update_only:
        logger.info("update-only モード: 書籍化フラグ済み作品の評価を再取得します")
        updated_rows = update_ratings(existing)
        if not updated_rows:
            logger.info("更新対象なし")
            return
        # updated_rows で既存行を上書き
        merged = upsert_book_works(existing, updated_rows)
        save_csv(merged, BOOK_WORKS_CSV)
        logger.info("book_works.csv 更新完了: %d 件の評価を再取得", len(updated_rows))
        return

    # --- 通常モード（新規検索） ---
    novels_df = load_csv(NOVELS_CSV, dtype={"ncode": str})

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
