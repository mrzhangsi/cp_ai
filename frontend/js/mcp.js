/**
 * CP_AI — MCP Market Module
 * MCP 服务浏览与搜索
 */

async function searchMCPServers() {
    const resultEl = document.getElementById('mcp-result');
    const btn = document.getElementById('btn-mcp-search');

    const body = {};
    const query = document.getElementById('mcp-query').value.trim();
    if (query) body.query = query;
    body.total_count = 50;

    setLoading(btn, true);
    resultEl.className = 'mcp-results';
    resultEl.innerHTML = '<div class="mcp-loading">搜索中...</div>';
    resultEl.classList.remove('hidden');
    document.getElementById('mcp-empty')?.classList.add('hidden');

    try {
        const data = await apiRequest('POST', '/mcp/search', body, true);
        renderMCPResults(data);
    } catch (err) {
        resultEl.innerHTML = `<div class="mcp-error">搜索失败: ${escapeHtml(err.message)}</div>`;
    } finally {
        setLoading(btn, false);
    }
}

function renderMCPResults(data) {
    const resultEl = document.getElementById('mcp-result');
    if (!data.servers || data.servers.length === 0) {
        resultEl.innerHTML = '<div class="mcp-empty-msg">没有找到相关 MCP 服务</div>';
        return;
    }

    let html = `<div class="mcp-count">找到 ${data.total} 个服务，显示 ${data.servers.length} 个</div>`;
    html += '<div class="mcp-list">';

    data.servers.forEach(server => {
        const desc = server.description.length > 150
            ? server.description.substring(0, 147) + '...'
            : server.description;

        html += `
            <div class="mcp-card" onclick="viewMCPDetail('${escapeHtml(server.id)}')">
                <div class="mcp-card-header">
                    <span class="mcp-card-name">${escapeHtml(server.name)}</span>
                    <span class="mcp-card-id">${escapeHtml(server.id)}</span>
                </div>
                <div class="mcp-card-desc">${escapeHtml(desc)}</div>
                ${server.url ? `<a href="${escapeHtml(server.url)}" target="_blank" class="mcp-card-link" onclick="event.stopPropagation()">在 ModelScope 查看 ↗</a>` : ''}
            </div>
        `;
    });

    html += '</div>';
    resultEl.innerHTML = html;
}

async function viewMCPDetail(serverId) {
    const panel = document.getElementById('mcp-detail-panel');
    const titleEl = document.getElementById('mcp-detail-title');
    const descEl = document.getElementById('mcp-detail-desc');
    const endpointsEl = document.getElementById('mcp-detail-endpoints');

    try {
        const data = await apiRequest('GET', `/mcp/server?server_id=${encodeURIComponent(serverId)}`, null, true);

        titleEl.textContent = data.name;
        let descHtml = '';
        if (data.url) {
            descHtml += `<div style="margin-bottom: var(--space-2);"><a href="${escapeHtml(data.url)}" target="_blank" class="mcp-detail-link">在 ModelScope 查看 ↗</a></div>`;
        }
        if (data.description) {
            descHtml += `<div>${escapeHtml(data.description)}</div>`;
        }
        descEl.innerHTML = descHtml ? `<div class="skill-detail-label">描述</div>${descHtml}` : '';

        if (data.servers && data.servers.length > 0) {
            let epHtml = '<div class="skill-detail-label">可用端点</div>';
            epHtml += '<div class="mcp-endpoints">';
            data.servers.forEach(ep => {
                epHtml += `
                    <div class="mcp-endpoint">
                        <div class="mcp-endpoint-type">${escapeHtml(ep.type)}</div>
                        <div class="mcp-endpoint-url">${escapeHtml(ep.url)}</div>
                    </div>
                `;
            });
            epHtml += '</div>';
            endpointsEl.innerHTML = epHtml;
        } else {
            endpointsEl.innerHTML = '<div style="color: var(--gray-400); font-size: var(--text-sm);">暂无可用端点</div>';
        }

        panel.classList.remove('hidden');
        panel.scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
        alert('加载详情失败: ' + err.message);
    }
}

// 事件绑定
document.getElementById('form-mcp-search')?.addEventListener('submit', (e) => {
    e.preventDefault();
    searchMCPServers();
});

document.getElementById('btn-close-mcp-detail')?.addEventListener('click', () => {
    document.getElementById('mcp-detail-panel')?.classList.add('hidden');
});

document.getElementById('btn-mcp-health')?.addEventListener('click', async () => {
    const msgEl = document.getElementById('mcp-health-result');
    try {
        const data = await apiRequest('GET', '/mcp/health');
        showMsg(msgEl, '服务正常: ' + (data.status || 'ok') + (data.token_set ? ' (Token 已设置)' : ' (未设置 Token)'), 'success');
    } catch (err) {
        showMsg(msgEl, '服务异常: ' + err.message, 'error');
    }
});
