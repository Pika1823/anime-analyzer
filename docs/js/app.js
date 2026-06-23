'use strict';

// ---- モジュール状態 ----
let novelsData = null;
let trendsData = null;
let snapshotsData = null;
let selectedNcode = null;
let currentWeights = { genre: 0, tag: 0, rank: 34, bmView: 33, growth: 0, eval: 33, monthlyPoint: 0, activity: 0 };

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
  cumulative_view_latest: { label: '総合評価（代替）', fmt: (v) => v != null ? v.toLocaleString()           : '—' },
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
    label: '評価件数推移',
    chartTitle: '累計評価件数推移',
    canvasId: 'eval-trend-chart',
    defaultOn: true,
    hint: '読者の能動的な評価行動の蓄積を表します。評価件数が急増している作品は口コミが広がっているサインです。',
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
    hint: '6指標のバランスを直感的に把握できます。面積が大きいほど総合的に強い作品です。偏りが少ない六角形に近い形がアニメ化しやすいプロファイルです。',
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

// Chart.js インスタンス（再描画時に破棄する）
let comparisonChart = null;
let rankingTrendChart = null;
let evalTrendChart = null;
let trendsChart = null;
let topAnimeChart = null;
let radarChart = null;
let benchmarkChart = null;

const DEFAULT_WEIGHTS = { genre: 0, tag: 0, rank: 34, bmView: 33, growth: 0, eval: 33, monthlyPoint: 0, activity: 0 };
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
  populateTrendsSelects();
  renderSettings();
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
  return best;
}

// ---- View 1: 類似度ランキング ----
function renderRanking(weights) {
  const tbody = document.getElementById('ranking-body');

  if (!novelsData || !novelsData.novels) {
    tbody.innerHTML = '<tr><td colspan="7" class="placeholder">データ収集中です。</td></tr>';
    renderPagination(0, 0);
    return;
  }

  // ジャンルフィルター選択肢を構築（未アニメ化全体から）
  const genreSelect = document.getElementById('filter-genre');
  const currentGenre = genreSelect.value;
  if (genreSelect.options.length <= 1) {
    const allNovels = novelsData.novels.filter((n) => !n.is_anime);
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

  // スコア再計算と並び替え
  const ranked = novelsData.novels
    .map((n) => {
      const { score, animeId, animeTitle } = calcScore(n, weights);
      return { ...n, _score: score, _animeId: animeId, _animeTitle: animeTitle };
    })
    .filter((n) => {
      if (filterUnadapted && n.is_anime) return false;
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
      const scorePct = Math.round(n._score * 100);
      const barWidth = Math.max(2, scorePct);
      const animeBadge = n.is_anime ? ' <span class="anime-badge">アニメ化済み</span>' : '';
      const extraCell = extraCol ? `<td>${extraCol.fmt(n[sortBy])}</td>` : '';
      const evalCell = n.all_hyoka_cnt_latest != null ? n.all_hyoka_cnt_latest.toLocaleString() + ' 件' : '—';
      return `<tr data-ncode="${n.ncode}" data-anime-id="${n._animeId || ''}">
        <td>${pageOffset + i + 1}</td>
        <td>${escHtml(n.title)}${animeBadge}</td>
        <td>${escHtml(n.genre_label || '—')}</td>
        <td>${n.monthly_rank_latest != null ? n.monthly_rank_latest : '—'}</td>
        <td>${evalCell}</td>
        ${extraCell}
        <td>
          <div class="score-bar-wrap">
            <div class="score-bar" style="width:${barWidth}px"></div>
            <span class="score-text">${(n._score).toFixed(3)}</span>
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
  const evalHistory = rankHistory.filter((d) => d.all_hyoka_cnt != null && d.all_hyoka_cnt > 0);

  const animeBadge = novel.is_anime ? ' <span class="anime-badge">アニメ化済み</span>' : '';
  const narouUrl = `https://ncode.syosetu.com/${ncode.toLowerCase()}/`;

  // グラフトグルバー
  const toggleBtns = GRAPH_CONFIGS.map((g) => {
    const isOn = visibleGraphs.has(g.id);
    return `<button class="graph-toggle-btn${isOn ? ' active' : ''}" data-graph-id="${g.id}">${g.label}</button>`;
  }).join('');

  // グラフセクション（カードごとに個別表示）
  const graphSections = GRAPH_CONFIGS.map((g) => {
    const isVisible = visibleGraphs.has(g.id);
    return `<div class="card graph-section${isVisible ? '' : ' hidden'}" id="graph-section-${g.id}">
      <h4 class="chart-title">${g.chartTitle}</h4>
      <div class="chart-container"><canvas id="${g.canvasId}"></canvas></div>
      <p class="graph-hint">💡 ${g.hint}</p>
    </div>`;
  }).join('');

  container.innerHTML = `
    <div class="back-bar">
      <button class="btn btn-secondary btn-back" id="btn-back-ranking">← ランキングに戻る</button>
    </div>
    <div class="card">
      <h3>
        <a class="novel-link" href="${narouUrl}" target="_blank" rel="noopener">${escHtml(novel.title)}</a>${animeBadge}
      </h3>
      <div class="meta-row">
        <span><strong>著者:</strong> ${escHtml(novel.author || '—')}</span>
        <span><strong>ジャンル:</strong> ${escHtml(novel.genre_label || '—')}</span>
        <span><strong>月刊順位:</strong> ${novel.monthly_rank_latest ?? '—'}</span>
        <span><strong>歴代最高順位:</strong> ${novel.best_rank_ever ?? '—'}</span>
        <span><strong>評価件数:</strong> ${novel.all_hyoka_cnt_latest != null ? novel.all_hyoka_cnt_latest.toLocaleString() + ' 件' : '—'}</span>
        <span><strong>評価ポイント:</strong> ${novel.all_point_latest != null ? novel.all_point_latest.toLocaleString() + ' pt' : '—'}</span>
        <span><strong>月間ポイント:</strong> ${novel.monthly_point_latest != null ? novel.monthly_point_latest.toLocaleString() + ' pt' : '—'}</span>
        <span><strong>感想件数:</strong> ${novel.impression_cnt_latest != null ? novel.impression_cnt_latest.toLocaleString() + ' 件' : '—'}</span>
        <span><strong>スコア:</strong> ${score.toFixed(3)}</span>
        <span><strong>最類似アニメ:</strong> ${escHtml(animeTitle || '—')}</span>
        <span><strong>Nコード:</strong> <a class="novel-link" href="${narouUrl}" target="_blank" rel="noopener">${ncode}</a></span>
      </div>
      ${novel.story ? `<div class="novel-story">${escHtml(novel.story)}</div>` : ''}
    </div>

    <div class="graph-toggle-bar">
      <span class="graph-toggle-label">表示グラフ:</span>
      ${toggleBtns}
    </div>

    ${graphSections}
  `;

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
        renderGraphById(gId, novel, bestEntry, animeTitle, rankHistory, evalHistory);
      }
      saveVisibleGraphs();
    });
  });

  // 表示中のグラフを初期描画
  GRAPH_CONFIGS.forEach((g) => {
    if (visibleGraphs.has(g.id)) {
      renderGraphById(g.id, novel, bestEntry, animeTitle, rankHistory, evalHistory);
    }
  });

  document.getElementById('btn-back-ranking')?.addEventListener('click', () => {
    switchTab('ranking');
  });
}

// ---- グラフ個別描画ディスパッチャー ----
function renderGraphById(graphId, novel, bestEntry, animeTitle, rankHistory, evalHistory) {
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
      if (evalHistory.length >= 2) {
        renderEvalTrend(evalHistory, novel.title);
      } else {
        const el = document.getElementById('eval-trend-chart');
        if (el) el.parentElement.innerHTML =
          '<p style="color:#888;font-size:0.875rem;">評価件数推移データ蓄積中です。</p>';
      }
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
  const ctx = document.getElementById('eval-trend-chart');
  if (!ctx) return;

  if (evalTrendChart) { evalTrendChart.destroy(); evalTrendChart = null; }

  const sorted = [...history].sort((a, b) => a.date.localeCompare(b.date));
  evalTrendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: sorted.map((d) => d.date),
      datasets: [{
        label: `累計評価件数: ${novelTitle}`,
        data: sorted.map((d) => d.all_hyoka_cnt),
        borderColor: '#f5a623',
        backgroundColor: 'rgba(245,166,35,0.08)',
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
        y: { title: { display: true, text: '累計評価件数（件）' }, min: 0 },
        x: { ticks: { maxTicksLimit: 12, maxRotation: 45 } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => ` ${c.parsed.y != null ? c.parsed.y.toLocaleString() + ' 件' : 'データなし'}` } },
      },
    },
  });
}

function renderScoreBreakdown(entry, animeTitle) {
  const ctx = document.getElementById('score-breakdown-chart');
  if (!ctx) return;

  if (comparisonChart) { comparisonChart.destroy(); comparisonChart = null; }

  comparisonChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['ジャンル', 'タグ', 'ランク', 'BM/View比率', 'View成長率', '評価件数', '月間ポイント', '活性スコア'],
      datasets: [{
        label: `スコア内訳（vs ${animeTitle}）`,
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
        backgroundColor: ['#e94560cc','#0f3460cc','#16213ecc','#533483cc','#05c46bcc','#f5a623cc','#4fc3f7cc','#81c784cc'],
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { min: 0, max: 1, ticks: { stepSize: 0.2 } } },
      plugins: {
        legend: { display: true },
        tooltip: { callbacks: { label: (c) => ` ${c.parsed.y.toFixed(3)}` } },
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
      score: totalWeight > 0 ? calcEntryScore(e, currentWeights) / totalWeight : 0,
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  topAnimeChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: top5.map((e) => e.title),
      datasets: [{
        label: '類似度スコア',
        data: top5.map((e) => parseFloat(e.score.toFixed(3))),
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
      scales: { x: { min: 0, max: 1, ticks: { stepSize: 0.2 } } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => ` スコア: ${c.parsed.x.toFixed(3)}` } },
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
      labels: ['ジャンル', 'タグ', 'ランク', 'BM/View比率', 'View成長率', '評価件数'],
      datasets: [{
        label: `vs ${animeTitle}`,
        data: [
          entry.genre_score || 0,
          entry.tag_score || 0,
          entry.rank_score || 0,
          entry.bm_view_score || 0,
          entry.growth_score || 0,
          entry.eval_score || 0,
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

// ---- View 4: 設定 ----
function renderSettings() {
  updateWeightUI();
}

const WEIGHT_KEYS = ['genre', 'tag', 'rank', 'bmView', 'growth', 'eval', 'monthlyPoint', 'activity'];

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

// ---- localStorage ----
function loadWeights() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return { ...DEFAULT_WEIGHTS };
    const parsed = JSON.parse(raw);
    // 旧データに新キーがない場合はデフォルト値で補完
    const merged = { ...DEFAULT_WEIGHTS };
    WEIGHT_KEYS.forEach((k) => {
      if (typeof parsed[k] === 'number') merged[k] = parsed[k];
    });
    return merged;
  } catch (_) {}
  return { ...DEFAULT_WEIGHTS };
}

function saveWeights(w) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(w));
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
    scoreLabel.textContent = `スコア閾値: ${parseFloat(scoreSlider.value).toFixed(2)} 以上`;
    currentPage = 0;
    renderRanking(currentWeights);
  });

  document.getElementById('filter-top10').addEventListener('change', () => {
    currentPage = 0;
    renderRanking(currentWeights);
  });
  document.getElementById('filter-unadapted').addEventListener('change', () => {
    currentPage = 0;
    renderRanking(currentWeights);
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

  document.getElementById('trends-novel-select').addEventListener('change', renderTrends);
  document.getElementById('trends-anime-select').addEventListener('change', renderTrends);

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
