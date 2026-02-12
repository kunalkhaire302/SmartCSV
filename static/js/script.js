/**
 * SmartCSV – Frontend Application Logic
 *
 * Handles: file upload (drag-and-drop), API calls via Axios, Chart.js rendering,
 * dynamic UI updates, theme toggle, and download functionality.
 */

// ═══════════════════════════════════════════════════════════════════
//  DOM References
// ═══════════════════════════════════════════════════════════════════
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
    uploadZone: $('#uploadZone'),
    fileInput: $('#fileInput'),
    filePreview: $('#filePreview'),
    fileName: $('#fileName'),
    fileSize: $('#fileSize'),
    removeFile: $('#removeFile'),
    metadataPanel: $('#metadataPanel'),
    metaGrid: $('#metaGrid'),
    processBtn: $('#processBtn'),
    processingPanel: $('#processingPanel'),
    loaderText: $('#loaderText'),
    loaderSteps: $('#loaderSteps'),
    etlPanel: $('#etlPanel'),
    etlContent: $('#etlContent'),
    insightsPanel: $('#insightsPanel'),
    insightCards: $('#insightCards'),
    statsPanel: $('#statsPanel'),
    statsTable: $('#statsTable'),
    chartsPanel: $('#chartsPanel'),
    chartsGrid: $('#chartsGrid'),
    downloadBar: $('#downloadBar'),
    downloadName: $('#downloadName'),
    downloadBtn: $('#downloadBtn'),
    themeToggle: $('#themeToggle'),
    iconSun: $('#iconSun'),
    iconMoon: $('#iconMoon'),
};

// ═══════════════════════════════════════════════════════════════════
//  State
// ═══════════════════════════════════════════════════════════════════
let state = {
    file: null,
    uploadedFilename: null,
    processedFilename: null,
    chartInstances: [],
};

// ═══════════════════════════════════════════════════════════════════
//  Theme Toggle
// ═══════════════════════════════════════════════════════════════════
function initTheme() {
    const saved = localStorage.getItem('smartcsv-theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = saved || (prefersDark ? 'dark' : 'dark');
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeIcons(theme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('smartcsv-theme', next);
    updateThemeIcons(next);
}

function updateThemeIcons(theme) {
    if (theme === 'dark') {
        dom.iconSun.classList.remove('hidden');
        dom.iconMoon.classList.add('hidden');
    } else {
        dom.iconSun.classList.add('hidden');
        dom.iconMoon.classList.remove('hidden');
    }
}

dom.themeToggle.addEventListener('click', toggleTheme);
initTheme();

// ═══════════════════════════════════════════════════════════════════
//  File Upload – Drag & Drop + Click
// ═══════════════════════════════════════════════════════════════════
dom.uploadZone.addEventListener('click', () => dom.fileInput.click());
dom.uploadZone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); dom.fileInput.click(); }
});

['dragenter', 'dragover'].forEach(evt => {
    dom.uploadZone.addEventListener(evt, (e) => { e.preventDefault(); dom.uploadZone.classList.add('drag-over'); });
});
['dragleave', 'drop'].forEach(evt => {
    dom.uploadZone.addEventListener(evt, (e) => { e.preventDefault(); dom.uploadZone.classList.remove('drag-over'); });
});

dom.uploadZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFileSelect(files[0]);
});

dom.fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleFileSelect(e.target.files[0]);
});

dom.removeFile.addEventListener('click', (e) => {
    e.stopPropagation();
    resetAll();
});

function handleFileSelect(file) {
    if (!file.name.toLowerCase().endsWith('.csv')) {
        showToast('Only CSV files are accepted.', 'error');
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        showToast('File exceeds 10 MB limit.', 'error');
        return;
    }
    state.file = file;
    dom.fileName.textContent = file.name;
    dom.fileSize.textContent = formatBytes(file.size);
    dom.filePreview.classList.remove('hidden');
    uploadFile(file);
}

// ═══════════════════════════════════════════════════════════════════
//  API – Upload
// ═══════════════════════════════════════════════════════════════════
async function uploadFile(file) {
    hideAllPanels();
    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await axios.post('/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
        const meta = res.data;
        state.uploadedFilename = meta.filename;
        renderMetadata(meta);
        dom.metadataPanel.classList.remove('hidden');
        dom.processBtn.disabled = false;
    } catch (err) {
        const msg = err.response?.data?.error || 'Upload failed.';
        showToast(msg, 'error');
    }
}

// ═══════════════════════════════════════════════════════════════════
//  API – Process & Analyse
// ═══════════════════════════════════════════════════════════════════
dom.processBtn.addEventListener('click', processAndAnalyse);

async function processAndAnalyse() {
    if (!state.uploadedFilename) return;

    dom.processBtn.disabled = true;
    showProcessing();

    try {
        // Step 1: ETL
        updateLoaderStep('Running ETL pipeline…', 'active');
        const etlRes = await axios.post('/process', { filename: state.uploadedFilename });
        const etlSummary = etlRes.data;
        state.processedFilename = etlSummary.processed_file;
        updateLoaderStep('ETL complete ✓', 'done');

        // Step 2: Insights
        updateLoaderStep('Generating insights…', 'active');
        const insRes = await axios.get('/insights', { params: { file: state.processedFilename } });
        const insights = insRes.data;
        updateLoaderStep('Insights ready ✓', 'done');

        // Hide loader, show results
        dom.processingPanel.classList.add('hidden');
        renderETLSummary(etlSummary);
        renderInsights(insights);
        renderStats(insights.descriptive_stats);
        renderCharts(insights.charts);
        showDownloadBar();

    } catch (err) {
        dom.processingPanel.classList.add('hidden');
        const msg = err.response?.data?.error || 'Processing failed.';
        showToast(msg, 'error');
        dom.processBtn.disabled = false;
    }
}

// ═══════════════════════════════════════════════════════════════════
//  API – Download
// ═══════════════════════════════════════════════════════════════════
dom.downloadBtn.addEventListener('click', () => {
    if (!state.processedFilename) return;
    window.location.href = `/download?file=${encodeURIComponent(state.processedFilename)}`;
});

// ═══════════════════════════════════════════════════════════════════
//  Rendering – Metadata
// ═══════════════════════════════════════════════════════════════════
function renderMetadata(meta) {
    const items = [
        { label: 'Rows', value: meta.row_count.toLocaleString(), accent: true },
        { label: 'Columns', value: meta.column_count, accent: true },
        { label: 'Size', value: meta.size_kb + ' KB', accent: true },
        { label: 'Duplicates', value: meta.duplicate_rows, accent: true },
    ];

    // Add column types
    if (meta.data_types) {
        const types = Object.values(meta.data_types);
        const summary = {};
        types.forEach(t => { summary[t] = (summary[t] || 0) + 1; });
        const typeStr = Object.entries(summary).map(([k, v]) => `${v} ${k}`).join(', ');
        items.push({ label: 'Data Types', value: typeStr, small: true });
    }

    // Missing values summary
    if (meta.missing_values) {
        const totalMissing = Object.values(meta.missing_values).reduce((a, b) => a + b, 0);
        items.push({ label: 'Total Missing', value: totalMissing.toLocaleString(), accent: true });
    }

    dom.metaGrid.innerHTML = items.map(it => `
        <div class="meta-card">
            <div class="meta-label">${it.label}</div>
            <div class="meta-value${it.small ? ' small' : ''}">${it.value}</div>
        </div>
    `).join('');
}

// ═══════════════════════════════════════════════════════════════════
//  Rendering – Processing Loader
// ═══════════════════════════════════════════════════════════════════
function showProcessing() {
    dom.processingPanel.classList.remove('hidden');
    dom.loaderSteps.innerHTML = '';
    dom.loaderText.textContent = 'Processing your data…';
}

function updateLoaderStep(text, status) {
    const step = document.createElement('div');
    step.className = `loader-step ${status}`;
    step.innerHTML = `${status === 'done' ? '✓' : '⟳'} ${text}`;
    dom.loaderSteps.appendChild(step);

    // Update previous active to done
    if (status === 'active') {
        dom.loaderSteps.querySelectorAll('.active').forEach(el => {
            if (el !== step) { el.classList.remove('active'); el.classList.add('done'); }
        });
    }
}

// ═══════════════════════════════════════════════════════════════════
//  Rendering – ETL Summary
// ═══════════════════════════════════════════════════════════════════
function renderETLSummary(summary) {
    let html = '<div class="etl-stat"><span class="etl-stat-label">Rows after cleaning</span><span class="etl-stat-value">' + (summary.rows_after || 0).toLocaleString() + '</span></div>';
    html += '<div class="etl-stat"><span class="etl-stat-label">Columns after</span><span class="etl-stat-value">' + (summary.columns_after || 0) + '</span></div>';
    html += '<div class="etl-stat"><span class="etl-stat-label">Memory saved</span><span class="etl-stat-value">' + (summary.memory_reduction_mb || 0) + ' MB</span></div>';

    if (summary.transformations_applied && summary.transformations_applied.length) {
        html += '<h3 style="margin-top:16px;font-size:0.9rem;color:var(--text-muted)">Transformations Applied</h3>';
        html += '<div class="etl-tags">';
        summary.transformations_applied.forEach(t => {
            html += `<span class="etl-tag">✓ ${escapeHtml(t)}</span>`;
        });
        html += '</div>';
    }

    if (summary.outliers_detected && Object.keys(summary.outliers_detected).length) {
        html += '<h3 style="margin-top:16px;font-size:0.9rem;color:var(--text-muted)">Outliers Detected</h3>';
        html += '<div class="etl-tags">';
        Object.entries(summary.outliers_detected).forEach(([col, cnt]) => {
            html += `<span class="etl-tag">⚠ ${escapeHtml(col)}: ${cnt}</span>`;
        });
        html += '</div>';
    }

    dom.etlContent.innerHTML = html;
    dom.etlPanel.classList.remove('hidden');
}

// ═══════════════════════════════════════════════════════════════════
//  Rendering – Insights (NLG)
// ═══════════════════════════════════════════════════════════════════
function renderInsights(data) {
    if (!data.insights || !data.insights.length) return;

    dom.insightCards.innerHTML = data.insights.map((text, i) => `
        <div class="insight-card">
            <span class="number">${i + 1}</span>
            ${escapeHtml(text)}
        </div>
    `).join('');
    dom.insightsPanel.classList.remove('hidden');
}

// ═══════════════════════════════════════════════════════════════════
//  Rendering – Descriptive Stats Table
// ═══════════════════════════════════════════════════════════════════
function renderStats(statsArr) {
    if (!statsArr || !statsArr.length) return;

    const headers = ['Column', 'Count', 'Mean', 'Median', 'Std', 'Min', 'Max', 'Skew', 'Kurtosis', 'Missing %'];
    let html = '<table class="stats-table"><thead><tr>';
    headers.forEach(h => html += `<th>${h}</th>`);
    html += '</tr></thead><tbody>';

    statsArr.forEach(s => {
        html += '<tr>';
        html += `<td style="font-weight:600;color:var(--text-primary)">${escapeHtml(s.column)}</td>`;
        html += `<td>${s.count.toLocaleString()}</td>`;
        html += `<td>${fmtNum(s.mean)}</td>`;
        html += `<td>${fmtNum(s.median)}</td>`;
        html += `<td>${fmtNum(s.std)}</td>`;
        html += `<td>${fmtNum(s.min)}</td>`;
        html += `<td>${fmtNum(s.max)}</td>`;
        html += `<td>${fmtNum(s.skewness)}</td>`;
        html += `<td>${fmtNum(s.kurtosis)}</td>`;
        html += `<td>${s.missing_pct}%</td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    dom.statsTable.innerHTML = html;
    dom.statsPanel.classList.remove('hidden');
}

// ═══════════════════════════════════════════════════════════════════
//  Rendering – Charts (Chart.js)
// ═══════════════════════════════════════════════════════════════════
function renderCharts(charts) {
    if (!charts || !charts.length) return;

    // Destroy previous chart instances
    state.chartInstances.forEach(c => c.destroy());
    state.chartInstances = [];
    dom.chartsGrid.innerHTML = '';

    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
    const textColor = isDark ? '#a0a0c0' : '#4a4a6a';

    Chart.defaults.color = textColor;
    Chart.defaults.borderColor = gridColor;

    charts.forEach((cfg, idx) => {
        if (cfg.chart_type === 'heatmap') {
            renderHeatmap(cfg);
            return;
        }

        const card = document.createElement('div');
        card.className = 'chart-card';
        card.innerHTML = `
            <div class="chart-title">${escapeHtml(cfg.title || 'Chart')}</div>
            <div class="chart-canvas-wrapper">
                <canvas id="chart-${idx}"></canvas>
            </div>
        `;
        dom.chartsGrid.appendChild(card);

        const ctx = card.querySelector('canvas').getContext('2d');
        const chartConfig = {
            type: cfg.chart_type,
            data: cfg.data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: cfg.chart_type !== 'bar', labels: { padding: 12, usePointStyle: true } },
                    tooltip: {
                        backgroundColor: isDark ? 'rgba(20,20,50,0.95)' : 'rgba(255,255,255,0.95)',
                        titleColor: isDark ? '#f0f0f8' : '#1a1a2e',
                        bodyColor: isDark ? '#a0a0c0' : '#4a4a6a',
                        borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 8,
                    },
                },
                scales: cfg.chart_type === 'pie' || cfg.chart_type === 'doughnut' ? {} : {
                    x: { grid: { color: gridColor }, ticks: { maxRotation: 45, autoSkip: true, maxTicksLimit: 20 } },
                    y: { grid: { color: gridColor }, beginAtZero: true },
                },
                animation: { duration: 800, easing: 'easeOutQuart' },
            },
        };

        // Scatter plots need different scale config
        if (cfg.chart_type === 'scatter') {
            chartConfig.options.scales = {
                x: { grid: { color: gridColor }, type: 'linear', position: 'bottom' },
                y: { grid: { color: gridColor } },
            };
        }

        const instance = new Chart(ctx, chartConfig);
        state.chartInstances.push(instance);
    });

    dom.chartsPanel.classList.remove('hidden');
}

// ═══════════════════════════════════════════════════════════════════
//  Rendering – Heatmap (as colored table)
// ═══════════════════════════════════════════════════════════════════
function renderHeatmap(cfg) {
    const card = document.createElement('div');
    card.className = 'chart-card';
    const cols = cfg.columns || [];
    const matrix = cfg.matrix || {};

    let html = `<div class="chart-title">${escapeHtml(cfg.title)}</div><div class="heatmap-wrapper"><table class="heatmap-table">`;
    html += '<thead><tr><th></th>';
    cols.forEach(c => html += `<th>${escapeHtml(c)}</th>`);
    html += '</tr></thead><tbody>';

    cols.forEach(r => {
        html += `<tr><th>${escapeHtml(r)}</th>`;
        cols.forEach(c => {
            const val = matrix[r]?.[c] ?? 0;
            const color = heatmapColor(val);
            html += `<td style="background:${color};color:${Math.abs(val) > 0.5 ? '#fff' : 'var(--text-primary)'}">${val.toFixed(2)}</td>`;
        });
        html += '</tr>';
    });

    html += '</tbody></table></div>';
    card.innerHTML = html;
    dom.chartsGrid.appendChild(card);
}

function heatmapColor(val) {
    const abs = Math.abs(val);
    if (val >= 0) {
        const r = Math.round(99 - abs * 65);
        const g = Math.round(102 - abs * 70);
        const b = Math.round(241);
        return `rgba(${r}, ${g}, ${b}, ${0.1 + abs * 0.7})`;
    } else {
        const r = Math.round(236);
        const g = Math.round(72 - abs * 40);
        const b = Math.round(153 - abs * 60);
        return `rgba(${r}, ${g}, ${b}, ${0.1 + abs * 0.7})`;
    }
}

// ═══════════════════════════════════════════════════════════════════
//  Download Bar
// ═══════════════════════════════════════════════════════════════════
function showDownloadBar() {
    if (!state.processedFilename) return;
    dom.downloadName.textContent = state.processedFilename;
    dom.downloadBar.classList.remove('hidden');
}

// ═══════════════════════════════════════════════════════════════════
//  Utilities
// ═══════════════════════════════════════════════════════════════════
function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function fmtNum(n) {
    if (n === null || n === undefined) return '—';
    if (Math.abs(n) >= 1e6) return n.toExponential(2);
    if (Math.abs(n) < 0.01 && n !== 0) return n.toExponential(2);
    return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function hideAllPanels() {
    ['metadataPanel', 'processingPanel', 'etlPanel', 'insightsPanel', 'statsPanel', 'chartsPanel', 'downloadBar'].forEach(id => {
        document.getElementById(id)?.classList.add('hidden');
    });
}

function resetAll() {
    state = { file: null, uploadedFilename: null, processedFilename: null, chartInstances: [] };
    dom.fileInput.value = '';
    dom.filePreview.classList.add('hidden');
    dom.processBtn.disabled = true;
    hideAllPanels();
    state.chartInstances.forEach(c => c.destroy());
    state.chartInstances = [];
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed; bottom: 24px; right: 24px; z-index: 9999;
        padding: 14px 22px; border-radius: 10px;
        font-size: 0.9rem; font-weight: 500; max-width: 380px;
        color: #fff; animation: slideUp 0.3s ease;
        box-shadow: 0 8px 32px rgba(0,0,0,0.25);
        background: ${type === 'error' ? 'linear-gradient(135deg, #ef4444, #dc2626)' : 'linear-gradient(135deg, #6366f1, #4f46e5)'};
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 4000);
}
