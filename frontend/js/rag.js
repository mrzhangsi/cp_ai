/* ============================================
   RAG Module Logic
   ============================================ */

// ========== 文档管理 ==========

/**
 * 加载文档列表
 */
async function loadRAGDocuments() {
    const listEl = document.getElementById('rag-doc-list');
    if (!listEl) return;

    try {
        const docs = await apiRequest('GET', '/rag/documents', null, true);
        if (!docs || docs.length === 0) {
            listEl.innerHTML = '<div class="rag-doc-empty">暂无文档，请上传</div>';
            return;
        }

        listEl.innerHTML = docs.map(doc => `
            <div class="rag-doc-item" data-id="${doc.id}">
                <div class="rag-doc-info">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                    <span class="rag-doc-name">${escapeHtml(doc.filename)}</span>
                    <span class="rag-doc-meta">${doc.chunk_count} chunks</span>
                    <span class="rag-doc-date">${formatDate(doc.created_at)}</span>
                </div>
                <div class="rag-doc-actions">
                    <button class="btn-icon btn-delete-doc" data-id="${doc.id}" data-name="${escapeHtml(doc.filename)}" title="删除">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        listEl.innerHTML = `<div class="rag-doc-empty">${escapeHtml(err.message)}</div>`;
    }
}

/**
 * 删除文档
 */
async function deleteRAGDocument(docId, filename) {
    const confirmed = await confirmModal(
        `确定删除文档「${filename}」？\n\n删除后将同时移除对应的向量数据。`,
        '删除文档',
        '删除'
    );
    if (!confirmed) return;

    try {
        await apiRequest('DELETE', `/rag/documents/${docId}`, null, true);
        loadRAGDocuments();
    } catch (err) {
        alert('删除失败: ' + err.message);
    }
}

/**
 * 选择文件后显示文件列表
 */
function showIngestFiles(files) {
    const listEl = document.getElementById('ingest-file-list');
    const btnIng = document.getElementById('btn-ingest');
    if (!listEl || !btnIng) return;

    window._ragPendingFiles = Array.from(files);

    if (window._ragPendingFiles.length === 0) {
        listEl.classList.add('hidden');
        btnIng.disabled = true;
        return;
    }

    btnIng.disabled = false;

    listEl.innerHTML = window._ragPendingFiles.map((f, i) => `
        <div class="ingest-file-item">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            <span class="ingest-file-name">${escapeHtml(f.name)}</span>
            <span class="ingest-file-size">${formatSize(f.size)}</span>
            <button class="ingest-file-remove" data-index="${i}" title="移除">&times;</button>
        </div>
    `).join('');

    listEl.classList.remove('hidden');

    listEl.querySelectorAll('.ingest-file-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            window._ragPendingFiles.splice(parseInt(btn.dataset.index), 1);
            showIngestFiles(window._ragPendingFiles);
        });
    });
}

// ========== 入库 ==========

document.getElementById('btn-ingest')?.addEventListener('click', async () => {
    const files = window._ragPendingFiles;
    if (!files || files.length === 0) return;

    const btn = document.getElementById('btn-ingest');
    const msgEl = document.getElementById('ingest-result');

    setLoading(btn, true);
    hideMsg(msgEl);

    try {
        const formData = new FormData();
        files.forEach(f => formData.append('files', f));

        const data = await apiRequest('POST', '/rag/ingest', formData, true);

        showMsg(msgEl, 'success',
            `入库成功：${data.files_processed} 个文件，${data.chunks_written} 个 chunk`);

        window._ragPendingFiles = [];
        document.getElementById('ingest-file-list').classList.add('hidden');
        document.getElementById('ingest-files').value = '';
        btn.disabled = true;

        loadRAGDocuments();
    } catch (err) {
        showMsg(msgEl, 'error', '入库失败: ' + err.message);
    } finally {
        setLoading(btn, false);
    }
});

// ========== 查询 ==========

document.getElementById('form-query')?.addEventListener('submit', async (e) => {
    e.preventDefault();

    const queryText = document.getElementById('query-text').value.trim();
    if (!queryText) return;

    const mode = document.querySelector('input[name="rag-mode"]:checked')?.value || 'retrieve';
    const btn = document.getElementById('btn-query');
    const emptyEl = document.getElementById('query-empty');
    const answerPanel = document.getElementById('rag-answer-panel');
    const contextPanel = document.getElementById('rag-context-panel');
    const ragasPanel = document.getElementById('rag-ragas-panel');

    setLoading(btn, true);

    // 隐藏所有面板
    emptyEl?.classList.add('hidden');
    answerPanel?.classList.add('hidden');
    contextPanel?.classList.add('hidden');
    ragasPanel?.classList.add('hidden');

    try {
        if (mode === 'retrieve') {
            const sources = await apiRequest('POST', '/rag/retrieve', {
                query: queryText,
                top_k: parseInt(document.getElementById('query-topk').value) || 5,
            }, true);

            // 显示检索来源
            renderContextPanel(sources, contextPanel);
        } else {
            const runEval = mode === 'query_eval';
            const body = {
                query: queryText,
                top_k: parseInt(document.getElementById('query-topk').value) || 5,
                run_eval: runEval,
            };

            if (runEval) {
                const metrics = Array.from(document.querySelectorAll('input[name="rag-metric"]:checked'))
                    .map(cb => cb.value);
                body.metrics = metrics;

                const ref = document.getElementById('query-reference')?.value.trim();
                if (ref) body.reference = ref;
            }

            const data = await apiRequest('POST', '/rag/query', body, true);

            // 渲染生成回答
            renderAnswerPanel(data.response, answerPanel);

            // 渲染检索来源
            renderContextPanel(data.source_nodes, contextPanel);

            // 渲染 RAGAS 评估（仅在启用时）
            if (runEval && data.ragas) {
                renderRAGASScores(data.ragas, ragasPanel);
            }
        }
    } catch (err) {
        emptyEl?.classList.remove('hidden');
        emptyEl.innerHTML = `
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="1.5">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="15" y1="9" x2="9" y2="15"></line>
                <line x1="9" y1="9" x2="15" y2="15"></line>
            </svg>
            <p>${escapeHtml(err.message)}</p>
        `;
    } finally {
        setLoading(btn, false);
    }
});

/**
 * 渲染生成回答面板
 */
function renderAnswerPanel(answer, panel) {
    if (!panel) return;
    const content = document.getElementById('rag-answer-content');
    if (content) {
        content.textContent = answer || '无回答内容';
    }
    panel.classList.remove('hidden');
}

/**
 * 渲染检索来源面板
 */
function renderContextPanel(sources, panel) {
    if (!panel) return;

    const list = document.getElementById('rag-context-list');
    const countBadge = document.getElementById('rag-context-count');

    if (!sources || sources.length === 0) {
        if (countBadge) countBadge.textContent = '0 条';
        if (list) list.innerHTML = '<div class="rag-doc-empty">未检索到相关内容</div>';
        panel.classList.remove('hidden');
        return;
    }

    if (countBadge) {
        countBadge.textContent = `${sources.length} 条`;
    }

    if (list) {
        list.innerHTML = sources.map((s, i) => `
            <div class="rag-context-item">
                <div>
                    <span class="rag-context-source">${escapeHtml(s.metadata?.source || s.source || '未知来源')}</span>
                    <span class="rag-context-score">相关度 ${s.score != null ? (s.score * 100).toFixed(1) + '%' : '-'}</span>
                </div>
                <div class="rag-context-text">${escapeHtml(s.content || s.text || '')}</div>
            </div>
        `).join('');
    }

    panel.classList.remove('hidden');
}

/**
 * 渲染 RAGAS 评估分数
 */
function renderRAGASScores(ragas, panel) {
    if (!panel) return;

    // 先隐藏所有指标行
    panel.querySelectorAll('.ragas-item').forEach(el => el.classList.add('hidden'));

    const metricMap = {
        faithfulness: { fillId: 'ragas-faithfulness', valId: 'ragas-faithfulness-val' },
        answer_relevancy: { fillId: 'ragas-answer-relevancy', valId: 'ragas-answer-relevancy-val' },
        context_precision: { fillId: 'ragas-context-precision', valId: 'ragas-context-precision-val' },
        context_recall: { fillId: 'ragas-context-recall', valId: 'ragas-context-recall-val' },
    };

    for (const [key, val] of Object.entries(ragas)) {
        if (val == null || !metricMap[key]) continue;
        const m = metricMap[key];
        const fill = document.getElementById(m.fillId);
        const valEl = document.getElementById(m.valId);
        if (!fill || !valEl) continue;

        const pct = (val * 100).toFixed(1);
        fill.style.width = pct + '%';
        fill.className = 'ragas-fill';
        if (val >= 0.7) fill.classList.add('good');
        else if (val >= 0.4) fill.classList.add('medium');
        else fill.classList.add('low');
        valEl.textContent = pct + '%';

        // 显示这一行
        fill.closest('.ragas-item')?.classList.remove('hidden');
    }

    panel.classList.remove('hidden');
}

// ========== 模式切换 ==========

document.querySelectorAll('input[name="rag-mode"]').forEach((radio) => {
    radio.addEventListener('change', () => {
        const btn = document.getElementById('btn-query');
        const evalOpts = document.getElementById('rag-eval-options');
        if (radio.value === 'retrieve' && radio.checked) {
            btn.textContent = '检索';
            evalOpts?.classList.add('hidden');
        } else if (radio.value === 'query' && radio.checked) {
            btn.textContent = '生成';
            evalOpts?.classList.add('hidden');
        } else if (radio.value === 'query_eval' && radio.checked) {
            btn.textContent = '生成+评估';
            evalOpts?.classList.remove('hidden');
        }
    });
});

// ========== 评估指标选择：context_precision/context_recall 需要 reference ==========

document.querySelectorAll('input[name="rag-metric"]').forEach((cb) => {
    cb.addEventListener('change', () => {
        const needRef = document.querySelector('input[name="rag-metric"][value="context_precision"]')?.checked
            || document.querySelector('input[name="rag-metric"][value="context_recall"]')?.checked;
        const refWrap = document.getElementById('rag-reference-wrap');
        if (needRef) {
            refWrap?.classList.remove('hidden');
        } else {
            refWrap?.classList.add('hidden');
        }
    });
});

// ========== 健康检查 ==========

document.getElementById('btn-rag-health')?.addEventListener('click', async () => {
    const msgEl = document.getElementById('rag-health-result');
    const btn = document.getElementById('btn-rag-health');

    setLoading(btn, true);
    hideMsg(msgEl);

    try {
        const data = await apiRequest('GET', '/rag/health');
        const vs = data.vector_store || {};
        showMsg(msgEl, 'success', `${data.status} | 向量库: ${vs.persist_dir || '-'} | chunks: ${vs.user_count ?? '-'}`);
    } catch (err) {
        showMsg(msgEl, 'error', err.message);
    } finally {
        setLoading(btn, false);
    }
});

// ========== 文件选择 ==========

document.getElementById('ingest-files')?.addEventListener('change', (e) => {
    showIngestFiles(e.target.files);
});

// ========== 拖拽上传 ==========

document.getElementById('ingest-dropzone')?.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.currentTarget.classList.add('dragover');
});

document.getElementById('ingest-dropzone')?.addEventListener('dragleave', (e) => {
    e.currentTarget.classList.remove('dragover');
});

document.getElementById('ingest-dropzone')?.addEventListener('drop', (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove('dragover');

    const mdFiles = Array.from(e.dataTransfer.files).filter(f =>
        f.name.toLowerCase().endsWith('.md')
    );

    if (mdFiles.length === 0) {
        alert('仅支持 .md 格式文件');
        return;
    }

    showIngestFiles(mdFiles);
});

// ========== 文档列表事件委托 ==========

document.getElementById('rag-doc-list')?.addEventListener('click', (e) => {
    const deleteBtn = e.target.closest('.btn-delete-doc');
    if (deleteBtn) {
        deleteRAGDocument(
            parseInt(deleteBtn.dataset.id),
            deleteBtn.dataset.name
        );
    }
});

// ========== 刷新按钮 ==========

document.getElementById('btn-refresh-docs')?.addEventListener('click', () => {
    loadRAGDocuments();
});

// ========== 视图加载 ==========

window.loadRAGView = function () {
    loadRAGDocuments();
};
