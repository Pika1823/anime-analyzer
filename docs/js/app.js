'use strict';

// ---- モジュール状態 ----
let novelsData = null;
let trendsData = null;
let snapshotsData = null;
let selectedNcode = null;
let currentWeights = { genre: 25, tag: 20, rank: 20, bmView: 15, growth: 10, eval: 10 };

// ページネーション
let currentPage = 0;
const PAGE_SIZE = 100;

// Chart.js インスタンス（再描画時に破棄する）
let comparisonChart = null;
let rankingTrendChart = null;
let evalTrendChart = null;
let trendsChart = null;

const DEFAULT_WEIGHTS = { genre: 25, tag: 20, rank: 20, bmView: 15, growth: 10, eval: 10 };
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
  } catch (e) {
    novelsData = null;
    trendsData = null;
  }

  currentWeights = loadWeights();
  renderRanking(currentWeights);
  populateTrendsSelects();
  renderSettings();
}

function showLoading() {
  document.getElementById('ranking-body').innerHTML =
    '<tr><td colspan="6" class="placeholder">データを読み込み中です...</td></tr>';
}

// ---- スコア再計算 ----
function calcScore(novel, weights) {
  if (!novel.pattern1_scores || novel.pattern1_scores.length === 0) {
    return { score: 0, animeId: null, animeTitle: null };
  }

  // 重みの合計でスコアを正規化（合計が 100 でなくても正しく動作する）
  const totalWeight =
    (weights.genre || 0) +
    (weights.tag || 0) +
    (weights.rank || 0) +
    (weights.bmView || 0) +
    (weights.growth || 0) +
    (weights.eval || 0);

  if (totalWeight === 0) return { score: 0, animeId: null, animeTitle: null };

  let best = { score: -1, animeId: null, animeTitle: null };
  for (const entry of novel.pattern1_scores) {
    const s =
      (entry.genre_score * (weights.genre || 0) +
        entry.tag_score * (weights.tag || 0) +
        entry.rank_score * (weights.rank || 0) +
        entry.bm_view_score * (weights.bmView || 0) +
        entry.growth_score * (weights.growth || 0) +
        (entry.eval_score || 0) * (weights.eval || 0)) /
      totalWeight;
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
    tbody.innerHTML =
      '<tr><td colspan="6" class="placeholder">データ収集中です。</td></tr>';
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
    .sort((a, b) => b._score - a._score);

  if (ranked.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="6" class="placeholder">条件に合う作品がありません。</td></tr>';
    renderPagination(0, 0);
    return;
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
      return `<tr data-ncode="${n.ncode}" data-anime-id="${n._animeId || ''}">
        <td>${pageOffset + i + 1}</td>
        <td>${escHtml(n.title)}${animeBadge}</td>
        <td>${escHtml(n.genre_label || '—')}</td>
        <td>${n.monthly_rank_latest != null ? n.monthly_rank_latest : '—'}</td>
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

  // 行クリック → 比較グラフへ
  tbody.querySelectorAll('tr[data-ncode]').forEach((row) => {
    row.addEventListener('click', () => {
      const ncode = row.dataset.ncode;
      selectedNcode = ncode;
      switchTab('comparison');
      renderComparison(ncode);
    });
  });
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
        <span><strong>スコア:</strong> ${score.toFixed(3)}</span>
        <span><strong>最類似アニメ:</strong> ${escHtml(animeTitle || '—')}</span>
        <span><strong>Nコード:</strong> <a class="novel-link" href="${narouUrl}" target="_blank" rel="noopener">${ncode}</a></span>
      </div>
    </div>
    ${rankHistory.length >= 2
      ? `<div class="card"><h4 class="chart-title">月刊ランキング推移</h4><div class="chart-container"><canvas id="ranking-trend-chart"></canvas></div></div>`
      : `<div class="card"><p style="color:#888;font-size:0.875rem;">ランキング推移データ蓄積中です（現在 ${rankHistory.length} 件）。毎日追記されます。</p></div>`
    }
    ${evalHistory.length >= 2
      ? `<div class="card"><h4 class="chart-title">累計評価件数の推移</h4><div class="chart-container"><canvas id="eval-trend-chart"></canvas></div></div>`
      : ''
    }
    ${bestEntry ? `<div class="card"><h4 class="chart-title">スコア内訳（vs ${escHtml(animeTitle || '')}）</h4><div class="chart-container"><canvas id="score-breakdown-chart"></canvas></div></div>` : ''}
  `;

  if (rankHistory.length >= 2) {
    renderRankingTrend(rankHistory, novel.title);
  }
  if (evalHistory.length >= 2) {
    renderEvalTrend(evalHistory, novel.title);
  }
  if (bestEntry) {
    renderScoreBreakdown(bestEntry, animeTitle);
  }

  document.getElementById('btn-back-ranking')?.addEventListener('click', () => {
    switchTab('ranking');
  });
}

function renderRankingTrend(history, novelTitle) {
  const ctx = document.getElementById('ranking-trend-chart');
  if (!ctx) return;

  if (rankingTrendChart) {
    rankingTrendChart.destroy();
    rankingTrendChart = null;
  }

  const sorted = [...history].sort((a, b) => a.date.localeCompare(b.date));
  const labels = sorted.map((d) => d.date);
  const ranks = sorted.map((d) => d.monthly_rank);

  rankingTrendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: `月刊ランク: ${novelTitle}`,
          data: ranks,
          borderColor: '#e94560',
          backgroundColor: 'rgba(233,69,96,0.08)',
          pointRadius: 4,
          pointHoverRadius: 6,
          spanGaps: false,
          tension: 0.2,
        },
      ],
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
        x: {
          ticks: { maxTicksLimit: 12, maxRotation: 45 },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => ` ${c.parsed.y != null ? c.parsed.y + '位' : 'データなし'}`,
          },
        },
      },
    },
  });
}

function renderEvalTrend(history, novelTitle) {
  const ctx = document.getElementById('eval-trend-chart');
  if (!ctx) return;

  if (evalTrendChart) {
    evalTrendChart.destroy();
    evalTrendChart = null;
  }

  const sorted = [...history].sort((a, b) => a.date.localeCompare(b.date));
  const labels = sorted.map((d) => d.date);
  const counts = sorted.map((d) => d.all_hyoka_cnt);

  evalTrendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: `累計評価件数: ${novelTitle}`,
          data: counts,
          borderColor: '#f5a623',
          backgroundColor: 'rgba(245,166,35,0.08)',
          pointRadius: 4,
          pointHoverRadius: 6,
          spanGaps: false,
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          title: { display: true, text: '累計評価件数（件）' },
          min: 0,
        },
        x: {
          ticks: { maxTicksLimit: 12, maxRotation: 45 },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => ` ${c.parsed.y != null ? c.parsed.y.toLocaleString() + ' 件' : 'データなし'}`,
          },
        },
      },
    },
  });
}

function renderScoreBreakdown(entry, animeTitle) {
  const ctx = document.getElementById('score-breakdown-chart');
  if (!ctx) return;

  if (comparisonChart) {
    comparisonChart.destroy();
    comparisonChart = null;
  }

  comparisonChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['ジャンル', 'タグ', 'ランク', 'BM/View比率', 'View成長率', '評価件数'],
      datasets: [
        {
          label: `スコア内訳（vs ${animeTitle}）`,
          data: [
            entry.genre_score,
            entry.tag_score,
            entry.rank_score,
            entry.bm_view_score,
            entry.growth_score,
            entry.eval_score || 0,
          ],
          backgroundColor: [
            '#e94560cc',
            '#0f3460cc',
            '#16213ecc',
            '#533483cc',
            '#05c46bcc',
            '#f5a623cc',
          ],
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 1, ticks: { stepSize: 0.2 } },
      },
      plugins: {
        legend: { display: true },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.parsed.y.toFixed(3)}`,
          },
        },
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

  novelsData.novels
    .filter((n) => !n.is_anime)
    .forEach((n) => {
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

  // 全週を収集してソート
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

  const novelPoints = allWeeks.map((w) => {
    const d = novelMap[w];
    return d && d.status === 'ok' ? d.score : null;
  });
  const animePoints = allWeeks.map((w) => {
    const d = animeMap[w];
    return d && d.status === 'ok' ? d.score : null;
  });

  container.innerHTML = '<canvas id="trends-chart"></canvas>';

  const ctx = document.getElementById('trends-chart');
  if (trendsChart) {
    trendsChart.destroy();
    trendsChart = null;
  }

  const datasets = [];
  if (ncode) {
    const novel = novelsData?.novels.find((n) => n.ncode === ncode);
    datasets.push({
      label: novel?.title || ncode,
      data: novelPoints,
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
      data: animePoints,
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
        x: {
          ticks: {
            maxTicksLimit: 12,
            maxRotation: 45,
          },
        },
      },
      plugins: {
        legend: { display: true },
      },
    },
  });
}

// ---- View 4: 設定 ----
function renderSettings() {
  updateWeightUI();
}

function updateWeightUI() {
  const keys = ['genre', 'tag', 'rank', 'bmView', 'growth', 'eval'];
  keys.forEach((k) => {
    const slider = document.getElementById(`weight-${k}`);
    const valEl = document.getElementById(`weight-${k}-val`);
    if (slider) slider.value = currentWeights[k];
    if (valEl) valEl.textContent = currentWeights[k] + '%';
  });
  updateWeightTotal();
}

function updateWeightTotal() {
  const keys = ['genre', 'tag', 'rank', 'bmView', 'growth', 'eval'];
  const total = keys.reduce((sum, k) => {
    const el = document.getElementById(`weight-${k}`);
    return sum + (el ? parseInt(el.value, 10) : currentWeights[k]);
  }, 0);
  const totalEl = document.getElementById('weight-total');
  if (totalEl) {
    totalEl.textContent = `合計: ${total}%（自動正規化して適用されます）`;
    totalEl.className = 'weight-total' + (total === 0 ? ' error' : '');
  }
}

function applyWeights() {
  const keys = ['genre', 'tag', 'rank', 'bmView', 'growth', 'eval'];
  const newWeights = {};
  let total = 0;
  keys.forEach((k) => {
    const v = parseInt(document.getElementById(`weight-${k}`).value, 10);
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
  renderRanking(currentWeights);
  // 選択中の作品があれば比較グラフも更新
  if (selectedNcode) renderComparison(selectedNcode);
}

function resetWeights() {
  currentWeights = { ...DEFAULT_WEIGHTS };
  saveWeights(currentWeights);
  updateWeightUI();
  renderRanking(currentWeights);
}

// ---- localStorage ----
function loadWeights() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return { ...DEFAULT_WEIGHTS };
    const parsed = JSON.parse(raw);
    const keys = ['genre', 'tag', 'rank', 'bmView', 'growth', 'eval'];
    if (keys.every((k) => typeof parsed[k] === 'number')) return parsed;
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
  // タブボタンのイベント
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // ジャンルフィルター
  document.getElementById('filter-genre').addEventListener('change', () => {
    currentPage = 0;
    renderRanking(currentWeights);
  });

  // スコア閾値スライダー
  const scoreSlider = document.getElementById('filter-score');
  const scoreLabel = document.getElementById('filter-score-label');
  scoreSlider.addEventListener('input', () => {
    scoreLabel.textContent = `スコア閾値: ${parseFloat(scoreSlider.value).toFixed(2)} 以上`;
    currentPage = 0;
    renderRanking(currentWeights);
  });

  // チェックボックスフィルター
  document.getElementById('filter-top10').addEventListener('change', () => {
    currentPage = 0;
    renderRanking(currentWeights);
  });
  document.getElementById('filter-unadapted').addEventListener('change', () => {
    currentPage = 0;
    renderRanking(currentWeights);
  });

  // ページネーションボタン
  document.getElementById('prev-page').addEventListener('click', () => {
    if (currentPage > 0) {
      currentPage--;
      renderRanking(currentWeights);
    }
  });
  document.getElementById('next-page').addEventListener('click', () => {
    currentPage++;
    renderRanking(currentWeights);
  });

  // 重みスライダーのリアルタイム更新
  ['genre', 'tag', 'rank', 'bmView', 'growth', 'eval'].forEach((k) => {
    const el = document.getElementById(`weight-${k}`);
    if (el) {
      el.addEventListener('input', () => {
        document.getElementById(`weight-${k}-val`).textContent = el.value + '%';
        updateWeightTotal();
      });
    }
  });

  // 設定ボタン
  document.getElementById('btn-apply-weights').addEventListener('click', applyWeights);
  document.getElementById('btn-reset-weights').addEventListener('click', resetWeights);

  // Trendsセレクト変更
  document.getElementById('trends-novel-select').addEventListener('change', renderTrends);
  document.getElementById('trends-anime-select').addEventListener('change', renderTrends);

  // 説明パネルの折りたたみ
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

  // データ読み込み開始
  loadData();
});
