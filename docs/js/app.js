'use strict';

// ---- モジュール状態 ----
let novelsData = null;
let trendsData = null;
let snapshotsData = null;
let selectedNcode = null;
let currentWeights = { genre: 22, tag: 18, rank: 17, bmView: 13, growth: 8, eval: 7, monthlyPoint: 10, activity: 5 };

// ページネーション
let currentPage = 0;
const PAGE_SIZE = 100;

// 並び替え
let sortBy = 'score';

// グラフ表示設定
let visibleGraphs = new Set();
const GRAPHS_LS_KEY = 'animeTool.graphs';

// 並び替え列の定義（score / monthly_rank_latest / all_hyoka_cnt_latest は常時表示列のため追加不要）
const SORT_EXTRA_COL = {
  all_point_latest:       { label: '評価ポイント',     fmt: (v) => v != null ? v.toLocaleString() + ' pt'  : '—' },
  global_point_latest:    { label: '総合評価ポイント',  fmt: (v) => v != null ? v.toLocaleString()           : '—' },
  monthly_point_latest:   { label: '月間ポイント',     fmt: (v) => v != null ? v.toLocaleString() + ' pt'  : '—' },
  impression_cnt_latest:  { label: '感想件数',         fmt: (v) => v != null ? v.toLocaleString() + ' 件'  : '—' },
  best_rank_ever:         { label: '歴代最高順位',     fmt: (v) => v != null ? v + ' 位'                   : '—' },
};

// グラフ設定一覧
const GRAPH_CONFIGS = [
  {
    id: 'rank_trend',
    label: '月刊ランク推移',
    chartTitle: '月刊ランキング推移',
    canvasId: 'ranking-trend-chart',
    defaultOn: true,
    hint: 'ランクが安定して上位に留まっているか確認できます。上位維持が長いほどアニメ化需要が持続している可能性があります。',
  },
  {
    id: 'eval_trend',
    label: '評価推移',
    chartTitle: '評価推移',
    canvasId: 'eval-trend-chart',
    defaultOn: true,
    hint: '読者の能動的な評価行動の蓄積を表します。「日次増分」に切り替えると日々の伸びが確認できます。急増しているタイミングを口コミ拡散のサインとして捉えられます。',
    controls: `<div class="graph-controls">
      <button class="eval-ctrl-btn active" data-ctrl="metric" data-val="hyoka">評価件数</button>
      <button class="eval-ctrl-btn" data-ctrl="metric" data-val="point">評価ポイント</button>
      <button class="eval-ctrl-btn active" data-ctrl="mode" data-val="cumulative">累計</button>
      <button class="eval-ctrl-btn" data-ctrl="mode" data-val="delta">日次増分</button>
    </div>`,
  },
  {
    id: 'score_breakdown',
    label: 'スコア内訳',
    chartTitle: 'スコア内訳（最類似アニメとの比較）',
    canvasId: 'score-breakdown-chart',
    defaultOn: true,
    hint: 'どの指標でスコアが高いか一目で確認できます。ランクとBM/Viewが高い作品はコア読者の定着度が高い傾向にあります。',
  },
  {
    id: 'top_anime',
    label: '類似アニメTop5',
    chartTitle: '類似アニメ Top5 スコア',
    canvasId: 'top-anime-chart',
    defaultOn: true,
    hint: '複数のアニメと比較した際のスコア分布です。上位アニメとのスコア差が小さいほど幅広い作品に似ており、汎用性が高いことを示します。',
  },
  {
    id: 'radar',
    label: 'レーダーチャート',
    chartTitle: 'スコアレーダーチャート（最類似アニメとの比較）',
    canvasId: 'radar-chart',
    defaultOn: false,
    hint: '8指標のバランスを直感的に把握できます。面積が大きいほど総合的に強い作品です。偏りが少ない形がアニメ化しやすいプロファイルです。',
  },
  {
    id: 'benchmark',
    label: '全作品比較',
    chartTitle: '全ランキング作品中のパーセンタイル',
    canvasId: 'benchmark-chart',
    defaultOn: false,
    hint: '現在の評価件数・ブックマーク数・月刊順位が全ランキング作品の中で上位何%にいるかを示します。100%に近いほど上位です。',
  },
];

// 評価グラフ状態
let evalDisplayMode = 'cumulative'; // 'cumulative' | 'delta'
let evalMetric = 'hyoka';           // 'hyoka' | 'point'
let currentEvalHistory = [];
let currentEvalNovelTitle = '';

// Chart.js インスタンス（再描画時に破棄する）
let comparisonChart = null;
let rankingTrendChart = null;
let evalTrendChart = null;
let trendsChart = null;
let topAnimeChart = null;
let radarChart = null;
let benchmarkChart = null;
let growthTrendChart = null;
let correlationChart = null;

// ---- 成長分析タブの状態 ----
let growthMetric = 'all_hyoka_cnt';
let growthPeriod = '30d';
let growthValueType = 'delta';
let growthTopN = 10;

// 相関グラフ軸の選択肢定義
const CORR_AXIS_OPTIONS = [
  { key: 'all_hyoka_cnt_latest',           label: '評価件数（現在値）' },
  { key: 'all_point_latest',               label: '評価ポイント（現在値）' },
  { key: 'monthly_rank_latest',            label: '月刊順位（現在）' },
  { key: 'monthly_point_latest',           label: '月間ポイント（現在値）' },
  { key: 'growth_all_hyoka_cnt_1d_delta',  label: '評価件数 前日増加数' },
  { key: 'growth_all_hyoka_cnt_7d_delta',  label: '評価件数 7日増加数' },
  { key: 'growth_all_hyoka_cnt_30d_delta', label: '評価件数 30日増加数' },
  { key: 'growth_all_hyoka_cnt_1d_rate',   label: '評価件数 前日増加率(%)' },
  { key: 'growth_all_hyoka_cnt_7d_rate',   label: '評価件数 7日増加率(%)' },
  { key: 'growth_all_hyoka_cnt_30d_rate',  label: '評価件数 30日増加率(%)' },
  { key: 'growth_all_point_1d_delta',      label: '評価ポイント 前日増加数' },
  { key: 'growth_all_point_7d_delta',      label: '評価ポイント 7日増加数' },
  { key: 'growth_all_point_30d_delta',     label: '評価ポイント 30日増加数' },
  { key: 'growth_all_point_1d_rate',       label: '評価ポイント 前日増加率(%)' },
  { key: 'growth_all_point_7d_rate',       label: '評価ポイント 7日増加率(%)' },
  { key: 'growth_all_point_30d_rate',      label: '評価ポイント 30日増加率(%)' },
];

const DEFAULT_WEIGHTS = { genre: 22, tag: 18, rank: 17, bmView: 13, growth: 8, eval: 7, monthlyPoint: 10, activity: 5 };
const LS_KEY = 'animeTool.weights';

// ---- データ読み込み ----
async function loadData() {
  showLoading();
  try {
    const [novelsRes, trendsRes, snapshotsRes] = await Promise.allSettled([
      fetch('./data/novels_merged.json'),
      fetch('./data/trends_merged.json'),
      fetch('./data/snapshots_merged.json'),
    ]);

    if (novelsRes.status === 'fulfilled' && novelsRes.value.ok) {
      novelsData = await novelsRes.value.json();
    } else {
      novelsData = null;
    }

    if (trendsRes.status === 'fulfilled' && trendsRes.value.ok) {
      trendsData = await trendsRes.value.json();
    } else {
      trendsData = null;
    }

    if (snapshotsRes.status === 'fulfilled' && snapshotsRes.value.ok) {
      snapshotsData = await snapshotsRes.value.json();
    } else {
      snapshotsData = null;
    }
  } catch (_) {
    novelsData = null;
    trendsData = null;
  }

  visibleGraphs = loadVisibleGraphs();
  currentWeights = loadWeights();
  renderFactorBars(currentWeights);
  renderRanking(currentWeights);
  renderSettings();
  initGrowthCorrSelects();
  renderGrowthTab();
}

function showLoading() {
  document.getElementById('ranking-body').innerHTML =
    '<tr><td colspan="7" class="placeholder">データを読み込み中です...</td></tr>';
}

// ---- visibleGraphs のローカルストレージ管理 ----
function loadVisibleGraphs() {
  try {
    const raw = localStorage.getItem(GRAPHS_LS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return new Set(parsed);
    }
  } catch (_) {}
  return new Set(GRAPH_CONFIGS.filter((g) => g.defaultOn).map((g) => g.id));
}

function saveVisibleGraphs() {
  try {
    localStorage.setItem(GRAPHS_LS_KEY, JSON.stringify([...visibleGraphs]));
  } catch (_) {}
}

// ---- スコア再計算 ----
function calcEntryScore(entry, weights) {
  return (
    (entry.genre_score || 0) * (weights.genre || 0) +
    (entry.tag_score || 0) * (weights.tag || 0) +
    (entry.rank_score || 0) * (weights.rank || 0) +
    (entry.bm_view_score || 0) * (weights.bmView || 0) +
    (entry.growth_score || 0) * (weights.growth || 0) +
    (entry.eval_score || 0) * (weights.eval || 0) +
    (entry.monthly_point_score || 0) * (weights.monthlyPoint || 0) +
    (entry.activity_score || 0) * (weights.activity || 0)
  );
}

function calcScore(novel, weights) {
  if (!novel.pattern1_scores || novel.pattern1_scores.length === 0) {
    return { score: 0, animeId: null, animeTitle: null };
  }

  const totalWeight =
    (weights.genre || 0) + (weights.tag || 0) + (weights.rank || 0) +
    (weights.bmView || 0) + (weights.growth || 0) + (weights.eval || 0) +
    (weights.monthlyPoint || 0) + (weights.activity || 0);

  if (totalWeight === 0) return { score: 0, animeId: null, animeTitle: null };

  let best = { score: -1, animeId: null, animeTitle: null };
  for (const entry of novel.pattern1_scores) {
    const s = calcEntryScore(entry, weights) / totalWeight;
    if (s > best.score) {
      best = { score: s, animeId: entry.anime_id, animeTitle: entry.anime_title };
    }
  }
  // 0〜100 スケールに変換して返す
  return { ...best, score: best.score * 100 };
}

// ---- View 1: 類似度ランキング ----
function renderRanking(weights) {
  const tbody = document.getElementById('ranking-body');

  if (!novelsData || !novelsData.novels) {
    tbody.innerHTML = '<tr><td colspan="7" class="placeholder">データ収集中です。</td></tr>';
    renderPagination(0, 0);
    return;
  }

  // ジャンルフィルター選択肢を構築（全作品から）
  const genreSelect = document.getElementById('filter-genre');
  const currentGenre = genreSelect.value;
  if (genreSelect.options.length <= 1) {
    const allNovels = novelsData.novels;
    const genres = [...new Set(allNovels.map((n) => n.genre_label).filter(Boolean))].sort();
    genres.forEach((g) => {
      const opt = document.createElement('option');
      opt.value = g;
      opt.textContent = g;
      genreSelect.appendChild(opt);
    });
    genreSelect.value = currentGenre;
  }

  const scoreThreshold = parseFloat(document.getElementById('filter-score').value);
  const selectedGenre = genreSelect.value;
  const filterTop10 = document.getElementById('filter-top10').checked;
  const filterUnadapted = document.getElementById('filter-unadapted').checked;
  const filterAdapted = document.getElementById('filter-adapted').checked;
  const filterBookOnly = document.getElementById('filter-book-only')?.checked || false;
  const filterNoBook = document.getElementById('filter-no-book')?.checked || false;
  const filterTitle = (document.getElementById('filter-title')?.value || '').trim().toLowerCase();

  // スコア再計算と並び替え
  const ranked = novelsData.novels
    .map((n) => {
      const { score, animeId, animeTitle } = calcScore(n, weights);
      return { ...n, _score: score, _animeId: animeId, _animeTitle: animeTitle };
    })
    .filter((n) => {
      if (filterUnadapted && n.is_anime) return false;
      if (filterAdapted && !n.is_anime) return false;
      if (filterBookOnly && !n.is_book) return false;
      if (filterNoBook && n.is_book) return false;
      if (filterTitle && !(n.title || '').toLowerCase().includes(filterTitle)) return false;
      if (n._score < scoreThreshold) return false;
      if (selectedGenre && selectedGenre !== 'すべて' && n.genre_label !== selectedGenre) return false;
      if (filterTop10 && (n.best_rank_ever == null || n.best_rank_ever > 10)) return false;
      return true;
    })
    .sort((a, b) => {
      if (sortBy === 'score') return b._score - a._score;
      if (sortBy === 'monthly_rank_latest' || sortBy === 'best_rank_ever') {
        const av = a[sortBy] != null ? a[sortBy] : Infinity;
        const bv = b[sortBy] != null ? b[sortBy] : Infinity;
        return av - bv;
      }
      const av = a[sortBy] != null ? a[sortBy] : -Infinity;
      const bv = b[sortBy] != null ? b[sortBy] : -Infinity;
      return bv - av;
    });

  // 評価件数は常時表示。ソートが評価件数の場合は追加列不要
  const showExtraCol = sortBy !== 'score' && sortBy !== 'monthly_rank_latest' && sortBy !== 'all_hyoka_cnt_latest';
  const extraCol = showExtraCol ? (SORT_EXTRA_COL[sortBy] || null) : null;
  const colCount = extraCol ? 8 : 7;

  if (ranked.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${colCount}" class="placeholder">条件に合う作品がありません。</td></tr>`;
    renderPagination(0, 0);
    return;
  }

  // ヘッダー更新
  const thead = document.getElementById('ranking-head');
  if (thead) {
    thead.innerHTML = `<tr>
      <th>順位</th>
      <th>タイトル</th>
      <th>ジャンル</th>
      <th>月刊順位</th>
      <th>評価件数</th>
      ${extraCol ? `<th>${extraCol.label}</th>` : ''}
      <th>スコア <span class="th-tooltip" title="アニメ化済み作品との類似度（0.00〜1.00）。クリックで内訳を表示">ⓘ</span></th>
      <th>最類似アニメ <span class="th-tooltip" title="スコアが最も高かった比較対象のアニメ作品">ⓘ</span></th>
    </tr>`;
  }

  const totalPages = Math.ceil(ranked.length / PAGE_SIZE);
  if (currentPage >= totalPages) currentPage = 0;

  const pageItems = ranked.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const pageOffset = currentPage * PAGE_SIZE;

  tbody.innerHTML = pageItems
    .map((n, i) => {
      const barWidth = Math.max(2, Math.round(n._score));
      const animeBadge = n.is_anime ? ' <span class="anime-badge">アニメ化済み</span>' : '';
      const bookBadge = n.is_book ? ' <span class="book-badge">書籍化</span>' : '';
      const extraCell = extraCol ? `<td>${extraCol.fmt(n[sortBy])}</td>` : '';
      const evalCell = n.all_hyoka_cnt_latest != null ? n.all_hyoka_cnt_latest.toLocaleString() + ' 件' : '—';
      return `<tr data-ncode="${n.ncode}" data-anime-id="${n._animeId || ''}">
        <td>${pageOffset + i + 1}</td>
        <td>${escHtml(n.title)}${animeBadge}${bookBadge}</td>
        <td>${escHtml(n.genre_label || '—')}</td>
        <td>${n.monthly_rank_latest != null ? n.monthly_rank_latest : '—'}</td>
        <td>${evalCell}</td>
        ${extraCell}
        <td>
          <div class="score-bar-wrap">
            <div class="score-bar" style="width:${barWidth}px"></div>
            <span class="score-text">${(n._score).toFixed(1)}</span>
          </div>
        </td>
        <td>${escHtml(n._animeTitle || '—')}</td>
      </tr>`;
    })
    .join('');

  renderPagination(currentPage, totalPages, ranked.length);

  tbody.querySelectorAll('tr[data-ncode]').forEach((row) => {
    row.addEventListener('click', () => {
      const ncode = row.dataset.ncode;
      selectedNcode = ncode;
      switchTab('comparison');
      renderComparison(ncode);
    });
  });
}

// フィルターをすべてリセットして初期状態に戻す
function resetFilters() {
  sortBy = 'score';
  const sortSel = document.getElementById('sort-by');
  if (sortSel) sortSel.value = 'score';

  const genreSelect = document.getElementById('filter-genre');
  if (genreSelect) genreSelect.value = 'すべて';

  const scoreSlider = document.getElementById('filter-score');
  if (scoreSlider) scoreSlider.value = 0;
  const scoreLabel = document.getElementById('filter-score-label');
  if (scoreLabel) scoreLabel.textContent = 'スコア閾値: 0.00 以上';

  const top10 = document.getElementById('filter-top10');
  if (top10) top10.checked = false;
  const unadapted = document.getElementById('filter-unadapted');
  if (unadapted) unadapted.checked = true;
  const adapted = document.getElementById('filter-adapted');
  if (adapted) adapted.checked = false;
  const bookOnly = document.getElementById('filter-book-only');
  if (bookOnly) bookOnly.checked = false;
  const noBook = document.getElementById('filter-no-book');
  if (noBook) noBook.checked = false;
  const titleInput = document.getElementById('filter-title');
  if (titleInput) titleInput.value = '';

  currentPage = 0;
  renderRanking(currentWeights);
}

// ---- ページネーション描画 ----
function renderPagination(page, totalPages, total) {
  const info = document.getElementById('page-info');
  const prevBtn = document.getElementById('prev-page');
  const nextBtn = document.getElementById('next-page');

  if (!info || !prevBtn || !nextBtn) return;

  if (totalPages <= 0) {
    info.textContent = '';
    prevBtn.disabled = true;
    nextBtn.disabled = true;
    return;
  }

  info.textContent = `${page + 1} / ${totalPages} ページ（合計 ${total} 件）`;
  prevBtn.disabled = page === 0;
  nextBtn.disabled = page >= totalPages - 1;
}

// ---- View 2: 比較グラフ ----
function renderComparison(ncode) {
  const container = document.getElementById('comparison-content');

  if (!ncode || !novelsData) {
    container.innerHTML = '<p class="placeholder">左のランキングから作品を選択してください</p>';
    return;
  }

  const novel = novelsData.novels.find((n) => n.ncode === ncode);
  if (!novel) {
    container.innerHTML = '<p class="placeholder">作品データが見つかりません。</p>';
    return;
  }

  const { score, animeId, animeTitle } = calcScore(novel, currentWeights);
  const bestEntry = novel.pattern1_scores?.find((e) => e.anime_id === animeId) || null;

  const rankHistory = snapshotsData?.snapshots?.[ncode] || [];

  const animeBadge = novel.is_anime ? ' <span class="anime-badge">アニメ化済み</span>' : '';
  const bookBadge = novel.is_book ? ' <span class="book-badge">書籍化</span>' : '';
  const narouUrl = `https://ncode.syosetu.com/${ncode.toLowerCase()}/`;

  // グラフトグルバー
  const toggleBtns = GRAPH_CONFIGS.map((g) => {
    const isOn = visibleGraphs.has(g.id);
    return `<button class="graph-toggle-btn${isOn ? ' active' : ''}" data-graph-id="${g.id}">${g.label}</button>`;
  }).join('');

  // グラフセクション（カードごとに個別表示）
  const graphSections = GRAPH_CONFIGS.map((g) => {
    const isVisible = visibleGraphs.has(g.id);
    const controlsHtml = g.controls ? g.controls : '';
    return `<div class="card graph-section${isVisible ? '' : ' hidden'}" id="graph-section-${g.id}">
      <h4 class="chart-title">${g.chartTitle}</h4>
      ${controlsHtml}
      <div class="chart-container"><canvas id="${g.canvasId}"></canvas></div>
      <p class="graph-hint">💡 ${g.hint}</p>
    </div>`;
  }).join('');

  // 伸び指標テーブル生成
  const gm = novel.growth_metrics || null;
  const growthPeriodDefs = [
    { key: '1d',  label: '1日前' },
    { key: '7d',  label: '1週間前' },
    { key: '30d', label: '1ヶ月前' },
  ];
  const fmtDelta = (v, unit) => {
    if (v == null) return '<td>—</td>';
    const sign = v >= 0 ? '+' : '';
    return `<td class="${v >= 0 ? 'positive' : 'negative'}">${sign}${v.toLocaleString()} ${unit}</td>`;
  };
  const fmtRate = (r) => {
    if (r == null) return '';
    const sign = r >= 0 ? '+' : '';
    return ` <span style="color:#888;font-size:0.8em;">(${sign}${r.toFixed(2)}%)</span>`;
  };

  let growthTableHtml = '';
  if (gm) {
    const rows = growthPeriodDefs.map(({ key, label }) => {
      const h = gm.all_hyoka_cnt?.[key];
      const p = gm.all_point?.[key];
      const hCell = h ? `<td class="${(h.delta ?? 0) >= 0 ? 'positive' : 'negative'}">${h.delta != null ? (h.delta >= 0 ? '+' : '') + h.delta.toLocaleString() + ' 件' : '—'}${fmtRate(h.rate)}</td>` : '<td>—</td>';
      const pCell = p ? `<td class="${(p.delta ?? 0) >= 0 ? 'positive' : 'negative'}">${p.delta != null ? (p.delta >= 0 ? '+' : '') + p.delta.toLocaleString() + ' pt' : '—'}${fmtRate(p.rate)}</td>` : '<td>—</td>';
      return `<tr><td>${label}</td>${hCell}${pCell}</tr>`;
    }).join('');
    growthTableHtml = `
      <div class="detail-section">
        <h4 class="detail-section-title">伸び指標</h4>
        <table class="growth-table">
          <thead><tr><th></th><th>評価件数</th><th>評価ポイント</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // Annict情報（アニメ化済み作品のみ）
  let annictHtml = '';
  if (novel.is_anime && (novel.annict_watchers_count != null || novel.annict_satisfaction_rate != null)) {
    annictHtml = `
      <div class="detail-section">
        <h4 class="detail-section-title">Annict情報</h4>
        <div class="meta-row">
          ${novel.annict_watchers_count != null ? `<span><strong>視聴者数:</strong> ${novel.annict_watchers_count.toLocaleString()}人</span>` : ''}
          ${novel.annict_satisfaction_rate != null ? `<span><strong>満足度:</strong> ${novel.annict_satisfaction_rate.toFixed(1)}%</span>` : ''}
          ${novel.annict_reviews_count != null ? `<span><strong>レビュー件数:</strong> ${novel.annict_reviews_count}件</span>` : ''}
        </div>
      </div>`;
  }

  // 書籍情報（書籍化済み作品のみ）
  let bookHtml = '';
  if (novel.is_book) {
    const amazonLink = novel.amazon_url_vol1
      ? `<a class="novel-link" href="${escHtml(novel.amazon_url_vol1)}" target="_blank" rel="noopener">Amazon で見る</a>`
      : '—';
    bookHtml = `
      <div class="detail-section">
        <h4 class="detail-section-title">書籍情報（Amazon）</h4>
        <div class="meta-row">
          ${novel.amazon_title_vol1 != null ? `<span><strong>書籍タイトル(1巻):</strong> ${escHtml(novel.amazon_title_vol1)}</span>` : ''}
          ${novel.amazon_rating != null ? `<span><strong>Amazon 評価:</strong> ★${novel.amazon_rating.toFixed(1)}</span>` : ''}
          ${novel.amazon_review_count != null ? `<span><strong>レビュー件数:</strong> ${novel.amazon_review_count.toLocaleString()}件</span>` : ''}
          <span><strong>Amazon リンク:</strong> ${amazonLink}</span>
        </div>
      </div>`;
  }

  // global_point_latest: 旧カラム名との互換
  const gpLatest = novel.global_point_latest ?? novel.cumulative_view_latest;

  container.innerHTML = `
    <div class="back-bar">
      <button class="btn btn-secondary btn-back" id="btn-back-ranking">← ランキングに戻る</button>
    </div>
    <div class="card">
      <h3>
        <a class="novel-link" href="${narouUrl}" target="_blank" rel="noopener">${escHtml(novel.title)}</a>${animeBadge}${bookBadge}
      </h3>

      <div class="detail-section">
        <div class="meta-row">
          <span><strong>著者:</strong> ${escHtml(novel.author || '—')}</span>
          <span><strong>ジャンル:</strong> ${escHtml(novel.genre_label || '—')}</span>
          <span><strong>話数:</strong> ${novel.episode_count_latest != null ? novel.episode_count_latest + '話' : '—'}</span>
          <span><strong>文字数:</strong> ${novel.length != null ? novel.length.toLocaleString() + '字' : '—'}</span>
          <span><strong>完結:</strong> ${novel.is_completed != null ? (novel.is_completed ? '完結済み' : '連載中') : '—'}</span>
          <span><strong>転生要素:</strong> ${novel.is_isekai_tensei != null ? (novel.is_isekai_tensei ? 'あり' : 'なし') : '—'}</span>
          <span><strong>転移要素:</strong> ${novel.is_isekai_tenni != null ? (novel.is_isekai_tenni ? 'あり' : 'なし') : '—'}</span>
          <span><strong>最終更新:</strong> ${novel.general_lastup ? novel.general_lastup.slice(0, 10) : '—'}</span>
        </div>
      </div>

      <div class="detail-section">
        <h4 class="detail-section-title">評価指標</h4>
        <div class="meta-row">
          <span><strong>評価件数:</strong> ${novel.all_hyoka_cnt_latest != null ? novel.all_hyoka_cnt_latest.toLocaleString() + ' 件' : '—'}</span>
          <span><strong>累計評価ポイント:</strong> ${novel.all_point_latest != null ? novel.all_point_latest.toLocaleString() + ' pt' : '—'}</span>
          <span><strong>総合評価ポイント:</strong> ${gpLatest != null ? gpLatest.toLocaleString() : '—'}</span>
          <span><strong>月間ポイント:</strong> ${novel.monthly_point_latest != null ? novel.monthly_point_latest.toLocaleString() + ' pt' : '—'}</span>
          <span><strong>週間ポイント:</strong> ${novel.weekly_point_latest != null ? novel.weekly_point_latest.toLocaleString() + ' pt' : '—'}</span>
          <span><strong>日間ポイント:</strong> ${novel.daily_point_latest != null ? novel.daily_point_latest.toLocaleString() + ' pt' : '—'}</span>
          <span><strong>ブックマーク:</strong> ${novel.bookmark_count_latest != null ? novel.bookmark_count_latest.toLocaleString() : '—'}</span>
          <span><strong>週間ユニーク:</strong> ${novel.weekly_unique_latest != null ? novel.weekly_unique_latest.toLocaleString() : '—'}</span>
          <span><strong>感想件数:</strong> ${novel.impression_cnt_latest != null ? novel.impression_cnt_latest.toLocaleString() + ' 件' : '—'}</span>
          <span><strong>レビュー件数:</strong> ${novel.review_cnt_latest != null ? novel.review_cnt_latest.toLocaleString() + ' 件' : '—'}</span>
        </div>
      </div>

      <div class="detail-section">
        <h4 class="detail-section-title">順位・ポテンシャル</h4>
        <div class="meta-row">
          <span><strong>月刊順位:</strong> ${novel.monthly_rank_latest != null ? novel.monthly_rank_latest + ' 位' : '—'}</span>
          <span><strong>歴代最高順位:</strong> ${novel.best_rank_ever != null ? novel.best_rank_ever + ' 位' : '—'}</span>
          <span><strong>BM/評価比率:</strong> ${novel.bm_view_ratio != null ? novel.bm_view_ratio.toFixed(4) : '—'}</span>
          <span><strong>評価成長率(6ヶ月):</strong> ${novel.view_growth_6mo != null ? (novel.view_growth_6mo * 100).toFixed(1) + '%' : '—'}</span>
          <span><strong>スコア:</strong> ${score.toFixed(1)}</span>
          <span><strong>最類似アニメ:</strong> ${escHtml(animeTitle || '—')}</span>
          <span><strong>Nコード:</strong> <a class="novel-link" href="${narouUrl}" target="_blank" rel="noopener">${ncode}</a></span>
        </div>
      </div>

      ${growthTableHtml}
      ${annictHtml}
      ${bookHtml}
      ${novel.story ? `<div class="novel-story">${escHtml(novel.story)}</div>` : ''}
    </div>

    <div class="graph-toggle-bar">
      <span class="graph-toggle-label">表示グラフ:</span>
      ${toggleBtns}
    </div>

    ${graphSections}
  `;

  // eval_trend コントロールボタンのイベント
  container.querySelectorAll('.eval-ctrl-btn').forEach((btn) => {
    const ctrl = btn.dataset.ctrl;
    const val = btn.dataset.val;
    // 現在の状態に合わせてアクティブ表示を初期化
    if ((ctrl === 'metric' && val === evalMetric) || (ctrl === 'mode' && val === evalDisplayMode)) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
    btn.addEventListener('click', () => {
      if (ctrl === 'metric') {
        evalMetric = val;
        container.querySelectorAll('[data-ctrl="metric"]').forEach((b) => b.classList.remove('active'));
      } else {
        evalDisplayMode = val;
        container.querySelectorAll('[data-ctrl="mode"]').forEach((b) => b.classList.remove('active'));
      }
      btn.classList.add('active');
      if (visibleGraphs.has('eval_trend') && currentEvalHistory.length > 0) {
        renderEvalTrend(currentEvalHistory, currentEvalNovelTitle);
      }
    });
  });

  // グラフトグルボタンのイベント
  container.querySelectorAll('.graph-toggle-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const gId = btn.dataset.graphId;
      if (visibleGraphs.has(gId)) {
        visibleGraphs.delete(gId);
        btn.classList.remove('active');
        document.getElementById(`graph-section-${gId}`)?.classList.add('hidden');
      } else {
        visibleGraphs.add(gId);
        btn.classList.add('active');
        document.getElementById(`graph-section-${gId}`)?.classList.remove('hidden');
        renderGraphById(gId, novel, bestEntry, animeTitle, rankHistory);
      }
      saveVisibleGraphs();
    });
  });

  // 表示中のグラフを初期描画
  GRAPH_CONFIGS.forEach((g) => {
    if (visibleGraphs.has(g.id)) {
      renderGraphById(g.id, novel, bestEntry, animeTitle, rankHistory);
    }
  });

  document.getElementById('btn-back-ranking')?.addEventListener('click', () => {
    switchTab('ranking');
  });
}

// ---- グラフ個別描画ディスパッチャー ----
function renderGraphById(graphId, novel, bestEntry, animeTitle, rankHistory) {
  switch (graphId) {
    case 'rank_trend':
      if (rankHistory.length >= 2) {
        renderRankingTrend(rankHistory, novel.title);
      } else {
        const el = document.getElementById('ranking-trend-chart');
        if (el) el.parentElement.innerHTML =
          `<p style="color:#888;font-size:0.875rem;">ランキング推移データ蓄積中です（現在 ${rankHistory.length} 件）。毎日追記されます。</p>`;
      }
      break;
    case 'eval_trend':
      renderEvalTrend(rankHistory, novel.title);
      break;
    case 'score_breakdown':
      if (bestEntry) {
        renderScoreBreakdown(bestEntry, animeTitle);
      } else {
        const el = document.getElementById('score-breakdown-chart');
        if (el) el.parentElement.innerHTML =
          '<p style="color:#888;font-size:0.875rem;">スコアデータがありません。</p>';
      }
      break;
    case 'top_anime':
      renderTopAnimeChart(novel);
      break;
    case 'radar':
      if (bestEntry) {
        renderRadarChart(bestEntry, animeTitle);
      } else {
        const el = document.getElementById('radar-chart');
        if (el) el.parentElement.innerHTML =
          '<p style="color:#888;font-size:0.875rem;">スコアデータがありません。</p>';
      }
      break;
    case 'benchmark':
      renderBenchmarkChart(novel);
      break;
  }
}

function renderRankingTrend(history, novelTitle) {
  const ctx = document.getElementById('ranking-trend-chart');
  if (!ctx) return;

  if (rankingTrendChart) { rankingTrendChart.destroy(); rankingTrendChart = null; }

  const sorted = [...history].sort((a, b) => a.date.localeCompare(b.date));
  rankingTrendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: sorted.map((d) => d.date),
      datasets: [{
        label: `月刊ランク: ${novelTitle}`,
        data: sorted.map((d) => d.monthly_rank),
        borderColor: '#e94560',
        backgroundColor: 'rgba(233,69,96,0.08)',
        pointRadius: 4,
        pointHoverRadius: 6,
        spanGaps: false,
        tension: 0.2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          reverse: true,
          title: { display: true, text: '月刊順位（↑ 上位）' },
          ticks: { stepSize: 50 },
          min: 1,
        },
        x: { ticks: { maxTicksLimit: 12, maxRotation: 45 } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => ` ${c.parsed.y != null ? c.parsed.y + '位' : 'データなし'}` } },
      },
    },
  });
}

function renderEvalTrend(history, novelTitle) {
  currentEvalHistory = history;
  currentEvalNovelTitle = novelTitle;

  const ctx = document.getElementById('eval-trend-chart');
  if (!ctx) return;
  if (evalTrendChart) { evalTrendChart.destroy(); evalTrendChart = null; }

  const metricKey = evalMetric === 'hyoka' ? 'all_hyoka_cnt' : 'all_point';
  const metricLabel = evalMetric === 'hyoka' ? '評価件数' : '評価ポイント';
  const unit = evalMetric === 'hyoka' ? '件' : 'pt';
  const borderColor = evalMetric === 'hyoka' ? '#f5a623' : '#4fc3f7';
  const bgColor = evalMetric === 'hyoka' ? 'rgba(245,166,35,0.08)' : 'rgba(79,195,247,0.08)';

  const sorted = [...history]
    .sort((a, b) => a.date.localeCompare(b.date))
    .filter((d) => d[metricKey] != null);

  if (sorted.length < 2) {
    ctx.parentElement.innerHTML = `<p style="color:#888;font-size:0.875rem;">${metricLabel}推移データ蓄積中です（現在 ${sorted.length} 件）。</p>`;
    return;
  }

  let labels, data, yLabel, datasetLabel;
  if (evalDisplayMode === 'cumulative') {
    labels = sorted.map((d) => d.date);
    data = sorted.map((d) => d[metricKey]);
    yLabel = `累計${metricLabel}（${unit}）`;
    datasetLabel = `累計${metricLabel}: ${novelTitle}`;
  } else {
    labels = [];
    data = [];
    for (let i = 1; i < sorted.length; i++) {
      const delta = (sorted[i][metricKey] ?? 0) - (sorted[i - 1][metricKey] ?? 0);
      labels.push(sorted[i].date);
      data.push(Math.max(0, delta));
    }
    yLabel = `日次増分 ${metricLabel}（${unit}/日）`;
    datasetLabel = `日次増分${metricLabel}: ${novelTitle}`;
  }

  evalTrendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: datasetLabel,
        data,
        borderColor,
        backgroundColor: bgColor,
        pointRadius: 3,
        pointHoverRadius: 5,
        spanGaps: false,
        tension: 0.2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { title: { display: true, text: yLabel }, min: 0 },
        x: { ticks: { maxTicksLimit: 12, maxRotation: 45 } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => ` ${c.parsed.y != null ? c.parsed.y.toLocaleString() + ' ' + unit : 'データなし'}` } },
      },
    },
  });
}

function renderScoreBreakdown(entry, animeTitle) {
  const ctx = document.getElementById('score-breakdown-chart');
  if (!ctx) return;
  if (comparisonChart) { comparisonChart.destroy(); comparisonChart = null; }

  const tw = Object.values(currentWeights).reduce((a, b) => a + b, 0) || 100;
  const wVals = [
    currentWeights.genre, currentWeights.tag, currentWeights.rank, currentWeights.bmView,
    currentWeights.growth, currentWeights.eval, currentWeights.monthlyPoint, currentWeights.activity,
  ];
  const baseLabels = ['ジャンル', 'タグ', 'ランク', 'BM/評価比率', '評価成長率', '評価件数', '月間ポイント', '活性スコア'];
  const rawScores = [
    entry.genre_score || 0, entry.tag_score || 0, entry.rank_score || 0, entry.bm_view_score || 0,
    entry.growth_score || 0, entry.eval_score || 0, entry.monthly_point_score || 0, entry.activity_score || 0,
  ];
  const labels = baseLabels.map((l, i) => `${l} (${wVals[i]}%)`);
  // 棒の高さ = 重み付き寄与値（合計 ≈ 総スコア/100）
  const data = rawScores.map((s, i) => parseFloat((s * wVals[i] / tw).toFixed(4)));

  comparisonChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: `スコア寄与値（vs ${animeTitle}）`,
        data,
        backgroundColor: ['#e94560cc','#0f3460cc','#16213ecc','#533483cc','#05c46bcc','#f5a623cc','#4fc3f7cc','#81c784cc'],
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { min: 0, title: { display: true, text: '寄与値（重み×スコア÷合計重み）' } } },
      plugins: {
        legend: { display: true },
        tooltip: {
          callbacks: {
            label: (c) => {
              const i = c.dataIndex;
              return [
                ` 寄与値: ${c.parsed.y.toFixed(4)}`,
                ` 生スコア: ${rawScores[i].toFixed(3)}`,
                ` 重み: ${wVals[i]}%`,
              ];
            },
          },
        },
      },
    },
  });
}

// 類似アニメ Top5 横棒グラフ
function renderTopAnimeChart(novel) {
  const ctx = document.getElementById('top-anime-chart');
  if (!ctx) return;

  if (topAnimeChart) { topAnimeChart.destroy(); topAnimeChart = null; }

  if (!novel.pattern1_scores || novel.pattern1_scores.length === 0) {
    ctx.parentElement.innerHTML = '<p style="color:#888;font-size:0.875rem;">比較データがありません。</p>';
    return;
  }

  const totalWeight =
    (currentWeights.genre || 0) + (currentWeights.tag || 0) + (currentWeights.rank || 0) +
    (currentWeights.bmView || 0) + (currentWeights.growth || 0) + (currentWeights.eval || 0) +
    (currentWeights.monthlyPoint || 0) + (currentWeights.activity || 0);

  const top5 = [...novel.pattern1_scores]
    .map((e) => ({
      title: e.anime_title,
      score: totalWeight > 0 ? calcEntryScore(e, currentWeights) / totalWeight * 100 : 0,
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  topAnimeChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: top5.map((e) => e.title),
      datasets: [{
        label: '類似度スコア',
        data: top5.map((e) => parseFloat(e.score.toFixed(1))),
        backgroundColor: '#e9456099',
        borderColor: '#e94560',
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      scales: { x: { min: 0, max: 100, ticks: { stepSize: 20 } } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => ` スコア: ${c.parsed.x.toFixed(1)}` } },
      },
    },
  });
}

// レーダーチャート（6指標のバランス）
function renderRadarChart(entry, animeTitle) {
  const ctx = document.getElementById('radar-chart');
  if (!ctx) return;

  if (radarChart) { radarChart.destroy(); radarChart = null; }

  radarChart = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: ['ジャンル', 'タグ', 'ランク', 'BM/評価比率', '評価成長率', '評価件数', '月間ポイント', '活性スコア'],
      datasets: [{
        label: `vs ${animeTitle}`,
        data: [
          entry.genre_score || 0,
          entry.tag_score || 0,
          entry.rank_score || 0,
          entry.bm_view_score || 0,
          entry.growth_score || 0,
          entry.eval_score || 0,
          entry.monthly_point_score || 0,
          entry.activity_score || 0,
        ],
        backgroundColor: 'rgba(233,69,96,0.2)',
        borderColor: '#e94560',
        pointBackgroundColor: '#e94560',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          min: 0,
          max: 1,
          ticks: { stepSize: 0.2, display: false },
          pointLabels: { font: { size: 12 } },
        },
      },
      plugins: { legend: { display: true } },
    },
  });
}

// 全ランキング作品中のパーセンタイル棒グラフ
function renderBenchmarkChart(novel) {
  const ctx = document.getElementById('benchmark-chart');
  if (!ctx) return;

  if (benchmarkChart) { benchmarkChart.destroy(); benchmarkChart = null; }

  if (!novelsData?.novels) {
    ctx.parentElement.innerHTML = '<p style="color:#888;font-size:0.875rem;">データがありません。</p>';
    return;
  }

  const all = novelsData.novels;

  const calcPct = (vals, val) => {
    if (val == null) return null;
    const below = vals.filter((v) => v != null && v <= val).length;
    return Math.round((below / vals.filter((v) => v != null).length) * 100);
  };
  // 月刊順位は小さいほど上位（逆転）
  const calcRankPct = (vals, val) => {
    if (val == null) return null;
    const validVals = vals.filter((v) => v != null);
    const above = validVals.filter((v) => v >= val).length;
    return Math.round((above / validVals.length) * 100);
  };

  const metrics = [
    { label: '評価件数',    pct: calcPct(all.map((n) => n.all_hyoka_cnt_latest), novel.all_hyoka_cnt_latest) },
    { label: 'BM数',        pct: calcPct(all.map((n) => n.bookmark_count_latest), novel.bookmark_count_latest) },
    { label: '月刊順位',    pct: calcRankPct(all.map((n) => n.monthly_rank_latest), novel.monthly_rank_latest) },
    { label: '評価ポイント', pct: calcPct(all.map((n) => n.all_point_latest), novel.all_point_latest) },
    { label: '月間ポイント', pct: calcPct(all.map((n) => n.monthly_point_latest), novel.monthly_point_latest) },
  ].filter((m) => m.pct != null);

  if (metrics.length === 0) {
    ctx.parentElement.innerHTML = '<p style="color:#888;font-size:0.875rem;">比較データが不足しています。</p>';
    return;
  }

  benchmarkChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: metrics.map((m) => m.label),
      datasets: [{
        label: '上位 % (100% = 全作品中1位)',
        data: metrics.map((m) => m.pct),
        backgroundColor: metrics.map((m) =>
          m.pct >= 80 ? '#05c46bcc' : m.pct >= 50 ? '#f5a623cc' : '#e94560cc'
        ),
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { min: 0, max: 100, title: { display: true, text: 'パーセンタイル (%)' } } },
      plugins: {
        legend: { display: true },
        tooltip: { callbacks: { label: (c) => ` 上位 ${c.parsed.y}%` } },
      },
    },
  });
}

// ---- View 3: Trends 比較 ----
function populateTrendsSelects() {
  if (!novelsData) return;

  const novelSel = document.getElementById('trends-novel-select');
  const animeSel = document.getElementById('trends-anime-select');

  novelSel.innerHTML = '<option value="">小説を選択...</option>';
  animeSel.innerHTML = '<option value="">アニメを選択...</option>';

  novelsData.novels.filter((n) => !n.is_anime).forEach((n) => {
    const opt = document.createElement('option');
    opt.value = n.ncode;
    opt.textContent = n.title;
    novelSel.appendChild(opt);
  });

  (novelsData.anime_works || []).forEach((a) => {
    const opt = document.createElement('option');
    opt.value = a.anime_id;
    opt.textContent = a.anime_title;
    animeSel.appendChild(opt);
  });
}

function renderTrends() {
  const novelSel = document.getElementById('trends-novel-select');
  const animeSel = document.getElementById('trends-anime-select');
  const container = document.getElementById('trends-chart-container');

  if (!trendsData) {
    container.innerHTML = '<p class="placeholder">Trendsデータ収集中です。</p>';
    return;
  }

  const ncode = novelSel.value;
  const animeId = animeSel.value;

  if (!ncode && !animeId) {
    container.innerHTML = '<p class="placeholder">小説またはアニメを選択してください。</p>';
    return;
  }

  const novelSeries = ncode ? (trendsData.novels?.[ncode] || []) : [];
  const animeSeries = animeId ? (trendsData.anime?.[animeId] || []) : [];

  const allWeeks = [...new Set([
    ...novelSeries.map((d) => d.week_start),
    ...animeSeries.map((d) => d.week_start),
  ])].sort();

  if (allWeeks.length === 0) {
    container.innerHTML = '<p class="placeholder">Trendsデータ収集中です。</p>';
    return;
  }

  const toMap = (series) => Object.fromEntries(series.map((d) => [d.week_start, d]));
  const novelMap = toMap(novelSeries);
  const animeMap = toMap(animeSeries);

  container.innerHTML = '<canvas id="trends-chart"></canvas>';
  const ctx = document.getElementById('trends-chart');
  if (trendsChart) { trendsChart.destroy(); trendsChart = null; }

  const datasets = [];
  if (ncode) {
    const novel = novelsData?.novels.find((n) => n.ncode === ncode);
    datasets.push({
      label: novel?.title || ncode,
      data: allWeeks.map((w) => { const d = novelMap[w]; return d && d.status === 'ok' ? d.score : null; }),
      borderColor: '#e94560',
      backgroundColor: 'transparent',
      borderDash: [6, 3],
      spanGaps: false,
      tension: 0.3,
    });
  }
  if (animeId) {
    const anime = novelsData?.anime_works?.find((a) => a.anime_id === animeId);
    datasets.push({
      label: anime?.anime_title || animeId,
      data: allWeeks.map((w) => { const d = animeMap[w]; return d && d.status === 'ok' ? d.score : null; }),
      borderColor: '#0f3460',
      backgroundColor: 'transparent',
      spanGaps: false,
      tension: 0.3,
    });
  }

  trendsChart = new Chart(ctx, {
    type: 'line',
    data: { labels: allWeeks, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 100 },
        x: { ticks: { maxTicksLimit: 12, maxRotation: 45 } },
      },
      plugins: { legend: { display: true } },
    },
  });
}

// ---- 説明パネルのファクターバーを現在の重みで動的描画 ----
function renderFactorBars(weights) {
  const container = document.getElementById('score-factors');
  if (!container) return;

  const factors = [
    { key: 'genre',        label: 'ジャンル一致',   desc: 'ファンタジー・恋愛など大分類が同じか' },
    { key: 'tag',          label: 'タグ類似度',      desc: '「転生」「異世界」など共通キーワードの割合' },
    { key: 'rank',         label: 'ランク帯',        desc: '月刊1〜100位=高、101〜300=中、301〜=低' },
    { key: 'bmView',       label: 'BM/View比率',    desc: 'ブックマーク数 ÷ 総閲覧数（コア読者の定着度）' },
    { key: 'growth',       label: 'View成長率',      desc: '直近6ヶ月の閲覧数の伸び（データ蓄積後に有効）' },
    { key: 'eval',         label: '評価件数',        desc: '累計評価件数（30000件で満点 — いいね数の代替）' },
    { key: 'monthlyPoint', label: '月間ポイント',    desc: '直近1ヶ月の評価ポイント（10000ptで満点）' },
    { key: 'activity',     label: '活性スコア',      desc: '最終更新からの経過日数（30日以内=1.0）' },
  ];
  const totalW = factors.reduce((s, f) => s + (weights[f.key] || 0), 0) || 1;

  container.innerHTML = factors.map((f) => {
    const w = weights[f.key] || 0;
    const pct = Math.round((w / totalW) * 100);
    return `<div class="factor-row">
      <span class="factor-label">${f.label}</span>
      <div class="factor-bar-bg"><div class="factor-bar" style="width:${pct}%"></div></div>
      <span class="factor-weight">${w}%</span>
      <span class="factor-desc">${f.desc}</span>
    </div>`;
  }).join('');
}

// ---- View 5: 成長分析 ----

// growth_metrics から値を取り出すユーティリティ
function getNovelGrowthValue(novel, axisKey) {
  if (!axisKey.startsWith('growth_')) return novel[axisKey] ?? null;
  const m = axisKey.slice(7).match(/^(.+)_(1d|7d|30d)_(delta|rate)$/);
  if (!m) return null;
  return novel.growth_metrics?.[m[1]]?.[m[2]]?.[m[3]] ?? null;
}

// 成長ランキングの上位N件を取得する（ランキング表・グラフで共用）
function getGrowthRankedNovels(metric, period, valueType, topN) {
  if (!novelsData?.novels) return [];
  return novelsData.novels
    .filter((n) => !n.is_anime)
    .map((n) => {
      const gm = n.growth_metrics?.[metric]?.[period];
      return { ...n, _gval: gm ? gm[valueType] : null };
    })
    .filter((n) => n._gval !== null)
    .sort((a, b) => b._gval - a._gval)
    .slice(0, topN);
}

function initGrowthCorrSelects() {
  const xSel = document.getElementById('corr-x-axis');
  const ySel = document.getElementById('corr-y-axis');
  if (!xSel || !ySel) return;
  const makeOpts = (defaultKey) =>
    CORR_AXIS_OPTIONS.map((o) =>
      `<option value="${o.key}"${o.key === defaultKey ? ' selected' : ''}>${escHtml(o.label)}</option>`
    ).join('');
  xSel.innerHTML = makeOpts('growth_all_hyoka_cnt_30d_delta');
  ySel.innerHTML = makeOpts('growth_all_point_30d_delta');
}

function renderGrowthTab() {
  renderGrowthRankingTable();
  renderGrowthTrendChart();
  renderCorrelationChart();
}

function renderGrowthRankingTable() {
  const thead = document.getElementById('growth-ranking-head');
  const tbody = document.getElementById('growth-ranking-body');
  if (!tbody) return;

  const METRIC_LABELS = { all_hyoka_cnt: '評価件数', all_point: '評価ポイント' };
  const PERIOD_LABELS = { '1d': '前日比', '7d': '7日比', '30d': '30日比' };
  const UNIT = { all_hyoka_cnt: '件', all_point: 'pt' };
  const metricLabel = METRIC_LABELS[growthMetric] || growthMetric;
  const periodLabel = PERIOD_LABELS[growthPeriod] || growthPeriod;
  const unit = UNIT[growthMetric] || '';

  if (thead) {
    thead.innerHTML = `<tr>
      <th>順位</th>
      <th>タイトル</th>
      <th>ジャンル</th>
      <th>月刊順位</th>
      <th>${metricLabel}（現在値）</th>
      <th>${periodLabel} 増加数</th>
      <th>${periodLabel} 増加率(%)</th>
    </tr>`;
  }

  if (!novelsData?.novels) {
    tbody.innerHTML = '<tr><td colspan="7" class="placeholder">データ収集中です。</td></tr>';
    return;
  }

  const novels = getGrowthRankedNovels(growthMetric, growthPeriod, growthValueType, growthTopN);

  if (novels.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="placeholder">成長データが蓄積されていません。スナップショット収集後に表示されます。</td></tr>';
    return;
  }

  tbody.innerHTML = novels.map((n, i) => {
    const gm = n.growth_metrics?.[growthMetric]?.[growthPeriod];
    const currentVal = gm?.current;
    const delta = gm?.delta;
    const rate = gm?.rate;
    const deltaStr = delta != null ? (delta >= 0 ? '+' : '') + delta.toLocaleString() + ' ' + unit : '—';
    const rateStr = rate != null ? (rate >= 0 ? '+' : '') + rate.toFixed(2) + '%' : '—';
    const deltaColor = delta != null && delta > 0 ? 'style="color:#05c46b;font-weight:700;"' : delta != null && delta < 0 ? 'style="color:#e94560;"' : '';
    const rateColor = rate != null && rate > 0 ? 'style="color:#05c46b;font-weight:700;"' : rate != null && rate < 0 ? 'style="color:#e94560;"' : '';
    return `<tr>
      <td>${i + 1}</td>
      <td>${escHtml(n.title)}</td>
      <td>${escHtml(n.genre_label || '—')}</td>
      <td>${n.monthly_rank_latest != null ? n.monthly_rank_latest : '—'}</td>
      <td>${currentVal != null ? currentVal.toLocaleString() + ' ' + unit : '—'}</td>
      <td ${deltaColor}>${deltaStr}</td>
      <td ${rateColor}>${rateStr}</td>
    </tr>`;
  }).join('');
}

function renderGrowthTrendChart() {
  const ctx = document.getElementById('growth-trend-chart');
  const titleEl = document.getElementById('growth-trend-chart-title');
  if (!ctx) return;

  if (growthTrendChart) { growthTrendChart.destroy(); growthTrendChart = null; }

  if (!novelsData?.novels || !snapshotsData?.snapshots) {
    ctx.parentElement.innerHTML = '<p style="color:#888;font-size:0.875rem;">スナップショットデータ収集中です。毎日追記されます。</p>';
    return;
  }

  const topNovels = getGrowthRankedNovels(growthMetric, growthPeriod, growthValueType, growthTopN);
  if (topNovels.length === 0) {
    ctx.parentElement.innerHTML = '<p style="color:#888;font-size:0.875rem;">成長データが蓄積されていません。</p>';
    return;
  }

  const METRIC_LABELS = { all_hyoka_cnt: '累計評価件数（件）', all_point: '累計評価ポイント' };
  const PERIOD_LABELS = { '1d': '前日', '7d': '7日前', '30d': '30日前' };
  if (titleEl) titleEl.textContent = `成長推移グラフ — ${METRIC_LABELS[growthMetric] || growthMetric}（上位${growthTopN}作品）`;

  const allDates = new Set();
  topNovels.forEach((n) => {
    (snapshotsData.snapshots[n.ncode] || []).forEach((s) => allDates.add(s.date));
  });
  const sortedDates = [...allDates].sort();

  if (sortedDates.length === 0) {
    ctx.parentElement.innerHTML = '<p style="color:#888;font-size:0.875rem;">スナップショットデータが空です。</p>';
    return;
  }

  const COLORS = ['#e94560','#0f3460','#f5a623','#05c46b','#533483','#4fc3f7','#ff7043','#66bb6a','#ab47bc','#26c6da',
                  '#ef5350','#1565c0','#ff8f00','#2e7d32','#6a1b9a','#00acc1','#e64a19','#43a047','#8e24aa','#00838f'];

  const datasets = topNovels.map((n, idx) => {
    const snaps = snapshotsData.snapshots[n.ncode] || [];
    const snapMap = Object.fromEntries(snaps.map((s) => [s.date, s]));
    const shortTitle = n.title.length > 18 ? n.title.slice(0, 18) + '…' : n.title;
    return {
      label: shortTitle,
      data: sortedDates.map((d) => snapMap[d]?.[growthMetric] ?? null),
      borderColor: COLORS[idx % COLORS.length],
      backgroundColor: 'transparent',
      pointRadius: 2,
      pointHoverRadius: 5,
      spanGaps: false,
      tension: 0.2,
      borderWidth: 2,
    };
  });

  growthTrendChart = new Chart(ctx, {
    type: 'line',
    data: { labels: sortedDates, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { title: { display: true, text: METRIC_LABELS[growthMetric] || growthMetric }, min: 0 },
        x: { ticks: { maxTicksLimit: 15, maxRotation: 45 } },
      },
      plugins: {
        legend: { display: true, position: 'bottom', labels: { font: { size: 11 }, boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: (c) => ` ${c.dataset.label}: ${c.parsed.y != null ? c.parsed.y.toLocaleString() : 'データなし'}`,
          },
        },
      },
    },
  });
}

function renderCorrelationChart() {
  const ctx = document.getElementById('correlation-chart');
  if (!ctx) return;

  if (correlationChart) { correlationChart.destroy(); correlationChart = null; }

  if (!novelsData?.novels) {
    ctx.parentElement.innerHTML = '<p style="color:#888;font-size:0.875rem;">データ収集中です。</p>';
    return;
  }

  const xKey = document.getElementById('corr-x-axis')?.value || 'growth_all_hyoka_cnt_30d_delta';
  const yKey = document.getElementById('corr-y-axis')?.value || 'growth_all_point_30d_delta';
  const xLabel = CORR_AXIS_OPTIONS.find((o) => o.key === xKey)?.label || xKey;
  const yLabel = CORR_AXIS_OPTIONS.find((o) => o.key === yKey)?.label || yKey;

  const allPoints = novelsData.novels
    .filter((n) => !n.is_anime)
    .map((n) => {
      const x = getNovelGrowthValue(n, xKey);
      const y = getNovelGrowthValue(n, yKey);
      if (x === null || y === null) return null;
      return { x, y, title: n.title, ncode: n.ncode };
    })
    .filter(Boolean);

  if (allPoints.length === 0) {
    ctx.parentElement.innerHTML = '<p style="color:#888;font-size:0.875rem;">相関データがありません。スナップショット蓄積後に表示されます。</p>';
    return;
  }

  // 上位N作品を成長ランキングから取得してハイライト
  const topNcodes = new Set(
    getGrowthRankedNovels(growthMetric, growthPeriod, growthValueType, growthTopN).map((n) => n.ncode)
  );
  const topPoints = allPoints.filter((p) => topNcodes.has(p.ncode));
  const restPoints = allPoints.filter((p) => !topNcodes.has(p.ncode));

  correlationChart = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [
        {
          label: `上位${growthTopN}作品（成長ランキング）`,
          data: topPoints,
          backgroundColor: '#e9456099',
          borderColor: '#e94560',
          pointRadius: 7,
          pointHoverRadius: 9,
        },
        {
          label: 'その他の作品',
          data: restPoints,
          backgroundColor: '#0f346033',
          borderColor: '#0f346055',
          pointRadius: 3,
          pointHoverRadius: 5,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: xLabel } },
        y: { title: { display: true, text: yLabel } },
      },
      plugins: {
        legend: { display: true, position: 'bottom' },
        tooltip: {
          callbacks: {
            label: (c) => {
              const p = c.raw;
              const t = p.title ? (p.title.length > 22 ? p.title.slice(0, 22) + '…' : p.title) : '';
              return ` ${t}: (${p.x != null ? Number(p.x).toLocaleString() : '—'}, ${p.y != null ? Number(p.y).toLocaleString() : '—'})`;
            },
          },
        },
      },
    },
  });
}

// ---- View 4: 設定 ----
function renderSettings() {
  updateWeightUI();
}

const WEIGHT_KEYS = ['genre', 'tag', 'rank', 'bmView', 'growth', 'eval', 'monthlyPoint', 'activity'];

// URL クエリパラメータとの対応マップ（短縮キーで URL を簡潔に保つ）
const WEIGHT_URL_KEYS = {
  genre: 'g', tag: 't', rank: 'r', bmView: 'bv',
  growth: 'gr', eval: 'ev', monthlyPoint: 'mp', activity: 'ac',
};

function updateWeightUI() {
  WEIGHT_KEYS.forEach((k) => {
    const slider = document.getElementById(`weight-${k}`);
    const valEl = document.getElementById(`weight-${k}-val`);
    if (slider) slider.value = currentWeights[k] || 0;
    if (valEl) valEl.textContent = (currentWeights[k] || 0) + '%';
  });
  updateWeightTotal();
}

function updateWeightTotal() {
  const total = WEIGHT_KEYS.reduce((sum, k) => {
    const el = document.getElementById(`weight-${k}`);
    return sum + (el ? parseInt(el.value, 10) : (currentWeights[k] || 0));
  }, 0);
  const totalEl = document.getElementById('weight-total');
  if (totalEl) {
    totalEl.textContent = `合計: ${total}%（自動正規化して適用されます）`;
    totalEl.className = 'weight-total' + (total === 0 ? ' error' : '');
  }
}

function applyWeights() {
  const newWeights = {};
  let total = 0;
  WEIGHT_KEYS.forEach((k) => {
    const el = document.getElementById(`weight-${k}`);
    const v = el ? parseInt(el.value, 10) : 0;
    newWeights[k] = v;
    total += v;
  });

  if (total === 0) {
    alert('重みの合計が 0% です。少なくとも 1 つの指標に値を設定してください。');
    return;
  }

  currentWeights = newWeights;
  saveWeights(currentWeights);
  currentPage = 0;
  renderFactorBars(currentWeights);
  renderRanking(currentWeights);
  if (selectedNcode) renderComparison(selectedNcode);
}

function resetWeights() {
  currentWeights = { ...DEFAULT_WEIGHTS };
  saveWeights(currentWeights);
  updateWeightUI();
  renderFactorBars(currentWeights);
  renderRanking(currentWeights);
}

// ---- localStorage + URL パラメータ ----
function loadWeights() {
  try {
    // URL パラメータを優先（共有リンクからのアクセスに対応）
    const params = new URLSearchParams(window.location.search);
    const fromUrl = {};
    let hasUrl = false;
    WEIGHT_KEYS.forEach((k) => {
      const urlKey = WEIGHT_URL_KEYS[k];
      if (params.has(urlKey)) {
        const v = parseInt(params.get(urlKey), 10);
        if (!isNaN(v)) { fromUrl[k] = v; hasUrl = true; }
      }
    });
    if (hasUrl) {
      const merged = { ...DEFAULT_WEIGHTS };
      WEIGHT_KEYS.forEach((k) => { if (typeof fromUrl[k] === 'number') merged[k] = fromUrl[k]; });
      return merged;
    }
    // URL になければ localStorage から
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return { ...DEFAULT_WEIGHTS };
    const parsed = JSON.parse(raw);
    // 旧データに新キーがない場合はデフォルト値で補完
    const merged = { ...DEFAULT_WEIGHTS };
    WEIGHT_KEYS.forEach((k) => { if (typeof parsed[k] === 'number') merged[k] = parsed[k]; });
    return merged;
  } catch (_) {}
  return { ...DEFAULT_WEIGHTS };
}

function saveWeights(w) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(w));
    // URL に重みを反映（リロードで設定が復元・他ユーザーとの共有が可能になる）
    const params = new URLSearchParams(window.location.search);
    WEIGHT_KEYS.forEach((k) => {
      params.set(WEIGHT_URL_KEYS[k], String(w[k] ?? 0));
    });
    history.replaceState(null, '', '?' + params.toString());
  } catch (_) {}
}

// ---- タブ切り替え ----
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-panel').forEach((panel) => {
    panel.classList.toggle('active', panel.id === `tab-${tabId}`);
  });
}

// ---- ユーティリティ ----
function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ---- 初期化 ----
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  document.getElementById('filter-genre').addEventListener('change', () => {
    currentPage = 0;
    renderRanking(currentWeights);
  });

  const scoreSlider = document.getElementById('filter-score');
  const scoreLabel = document.getElementById('filter-score-label');
  scoreSlider.addEventListener('input', () => {
    scoreLabel.textContent = `スコア閾値: ${parseFloat(scoreSlider.value).toFixed(1)} 以上`;
    currentPage = 0;
    renderRanking(currentWeights);
  });

  document.getElementById('filter-top10').addEventListener('change', () => {
    currentPage = 0;
    renderRanking(currentWeights);
  });
  document.getElementById('filter-unadapted').addEventListener('change', (e) => {
    // 相互排他: 未アニメ化のみ ON → アニメ化済みのみ OFF
    if (e.target.checked) document.getElementById('filter-adapted').checked = false;
    currentPage = 0;
    renderRanking(currentWeights);
  });
  document.getElementById('filter-adapted').addEventListener('change', (e) => {
    // 相互排他: アニメ化済みのみ ON → 未アニメ化のみ OFF
    if (e.target.checked) document.getElementById('filter-unadapted').checked = false;
    currentPage = 0;
    renderRanking(currentWeights);
  });
  document.getElementById('filter-book-only')?.addEventListener('change', (e) => {
    // 相互排他: 書籍化済みのみ ON → 未書籍化のみ OFF
    if (e.target.checked) document.getElementById('filter-no-book').checked = false;
    currentPage = 0;
    renderRanking(currentWeights);
  });
  document.getElementById('filter-no-book')?.addEventListener('change', (e) => {
    // 相互排他: 未書籍化のみ ON → 書籍化済みのみ OFF
    if (e.target.checked) document.getElementById('filter-book-only').checked = false;
    currentPage = 0;
    renderRanking(currentWeights);
  });

  // タイトル検索（入力のたびにリアルタイムで絞り込む）
  let titleSearchTimer = null;
  document.getElementById('filter-title')?.addEventListener('input', () => {
    clearTimeout(titleSearchTimer);
    titleSearchTimer = setTimeout(() => {
      currentPage = 0;
      renderRanking(currentWeights);
    }, 200);
  });

  document.getElementById('btn-reset-filters')?.addEventListener('click', resetFilters);

  document.getElementById('prev-page').addEventListener('click', () => {
    if (currentPage > 0) { currentPage--; renderRanking(currentWeights); }
  });
  document.getElementById('next-page').addEventListener('click', () => {
    currentPage++;
    renderRanking(currentWeights);
  });

  WEIGHT_KEYS.forEach((k) => {
    const el = document.getElementById(`weight-${k}`);
    if (el) {
      el.addEventListener('input', () => {
        const valEl = document.getElementById(`weight-${k}-val`);
        if (valEl) valEl.textContent = el.value + '%';
        updateWeightTotal();
      });
    }
  });

  document.getElementById('btn-apply-weights').addEventListener('click', applyWeights);
  document.getElementById('btn-reset-weights').addEventListener('click', resetWeights);

  // Trends タブは休止中のためイベントリスナーなし

  // 成長分析タブのコントロール
  const growthControls = {
    'growth-metric':     (v) => { growthMetric = v; },
    'growth-period':     (v) => { growthPeriod = v; },
    'growth-value-type': (v) => { growthValueType = v; },
    'growth-top-n':      (v) => { growthTopN = parseInt(v, 10); },
  };
  Object.entries(growthControls).forEach(([id, setter]) => {
    document.getElementById(id)?.addEventListener('change', (e) => {
      setter(e.target.value);
      renderGrowthTab();
    });
  });

  document.getElementById('corr-x-axis')?.addEventListener('change', renderCorrelationChart);
  document.getElementById('corr-y-axis')?.addEventListener('change', renderCorrelationChart);

  const infoToggle = document.getElementById('info-toggle');
  const infoBody = document.getElementById('info-body');
  const infoChevron = document.getElementById('info-chevron');
  const INFO_LS_KEY = 'animeTool.infoOpen';

  const infoOpen = localStorage.getItem(INFO_LS_KEY) !== 'false';
  if (!infoOpen) {
    infoBody.classList.add('collapsed');
    infoChevron.textContent = '▼';
    infoToggle.setAttribute('aria-expanded', 'false');
  }

  infoToggle.addEventListener('click', () => {
    const isCollapsed = infoBody.classList.toggle('collapsed');
    infoChevron.textContent = isCollapsed ? '▼' : '▲';
    infoToggle.setAttribute('aria-expanded', String(!isCollapsed));
    localStorage.setItem(INFO_LS_KEY, String(!isCollapsed));
  });

  document.getElementById('sort-by').addEventListener('change', (e) => {
    sortBy = e.target.value;
    currentPage = 0;
    renderRanking(currentWeights);
  });

  loadData();
});
