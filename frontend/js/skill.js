/**
 * CP_AI — Skill Module
 * 搜索、上传、管理用户技能
 */

let pendingUploadFile = null;
let currentViewingSkill = null;

// 标签页切换
document.querySelectorAll('.skill-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const tabName = tab.dataset.tab;
        document.querySelectorAll('.skill-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        document.querySelectorAll('.skill-tab-content').forEach(c => c.classList.remove('active'));
        document.getElementById(`skill-tab-${tabName}`)?.classList.add('active');

        if (tabName === 'my') {
            loadMySkills();
        }
    });
});

// ---- 搜索 ----

document.getElementById('form-skill-search')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const resultEl = document.getElementById('skill-result');
    const btn = document.getElementById('btn-skill-search');

    const body = {
        query: document.getElementById('skill-query').value,
        limit: parseInt(document.getElementById('skill-limit').value) || 20,
    };
    const category = document.getElementById('skill-category').value;
    const language = document.getElementById('skill-language').value;
    if (category) body.category = category;
    if (language) body.language = language;

    setLoading(btn, true);
    resultEl.className = 'skill-results info';
    resultEl.innerHTML = '<div class="skill-loading">搜索中...</div>';
    resultEl.classList.remove('hidden');
    document.getElementById('skill-empty')?.classList.add('hidden');

    try {
        const data = await apiRequest('POST', '/skill/search', body, true);
        renderSkillResults(data);
    } catch (err) {
        resultEl.innerHTML = `<div class="skill-error">搜索失败: ${escapeHtml(err.message)}</div>`;
    } finally {
        setLoading(btn, false);
    }
});

function renderSkillResults(data) {
    const resultEl = document.getElementById('skill-result');
    if (!data.skills || data.skills.length === 0) {
        resultEl.innerHTML = '<div class="skill-empty-msg">没有找到相关技能</div>';
        return;
    }

    let html = `<div class="skill-count">找到 ${data.total} 个技能，显示 ${data.skills.length} 个</div>`;
    html += '<div class="skill-list">';

    data.skills.forEach(skill => {
        const desc = skill.description.length > 120
            ? skill.description.substring(0, 117) + '...'
            : skill.description;

        html += `
            <div class="skill-card">
                <div class="skill-card-header">
                    <span class="skill-name">${escapeHtml(skill.name)}</span>
                    <span class="skill-stars">⭐ ${skill.stars}</span>
                </div>
                <div class="skill-category">${escapeHtml(skill.category_name)}</div>
                <div class="skill-desc">${escapeHtml(desc)}</div>
                <div class="skill-links">
                    ${skill.skill_url ? `<a href="${escapeHtml(skill.skill_url)}" target="_blank" class="skill-link">详情页</a>` : ''}
                    ${skill.github_url ? `<a href="${escapeHtml(skill.github_url)}" target="_blank" class="skill-link">GitHub</a>` : ''}
                    ${skill.raw_content_url ? `<a href="${escapeHtml(skill.raw_content_url)}" target="_blank" class="skill-link">SKILL.md</a>` : ''}
                </div>
                ${skill.install_command ? `<div class="skill-install"><code>${escapeHtml(skill.install_command)}</code></div>` : ''}
            </div>
        `;
    });

    html += '</div>';
    resultEl.innerHTML = html;
}

// ---- 我的技能 ----

document.getElementById('upload-skill-file')?.addEventListener('change', function() {
    const file = this.files[0];
    if (!file) return;

    pendingUploadFile = file;
    const reader = new FileReader();
    reader.onload = function(e) {
        const text = e.target.result;
        const parsed = parseFrontmatter(text);
        openSkillEditModal(null, parsed.name, parsed.description);
    };
    reader.readAsText(file);
});

/**
 * 解析 YAML frontmatter（简易版）
 * @param {string} content
 * @returns {{ name: string, description: string }}
 */
function parseFrontmatter(content) {
    const result = { name: '', description: '' };
    let normalized = content.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const match = normalized.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
    if (!match) return result;

    const lines = match[1].split('\n');
    for (const line of lines) {
        const idx = line.indexOf(':');
        if (idx === -1) continue;
        const key = line.slice(0, idx).trim();
        const value = line.slice(idx + 1).trim();
        if (key === 'name') result.name = value;
        else if (key === 'description') result.description = value;
    }

    if (!result.name) {
        const body = normalized.slice(match[0].length);
        const headingMatch = body.match(/^#\s+(.+)/m);
        if (headingMatch) result.name = headingMatch[1].trim();
    }

    return result;
}

function openSkillEditModal(skillId, name, summary) {
    document.getElementById('edit-skill-id').value = skillId || '';
    document.getElementById('edit-skill-name').value = name || '';
    document.getElementById('edit-skill-summary').value = summary || '';
    hideMsg(document.getElementById('edit-skill-msg'));
    document.getElementById('skill-edit-modal')?.classList.remove('hidden');
}

function closeSkillEditModal() {
    document.getElementById('skill-edit-modal')?.classList.add('hidden');
    pendingUploadFile = null;
    document.getElementById('upload-skill-file').value = '';
}

// Modal 关闭按钮事件
document.getElementById('btn-close-modal')?.addEventListener('click', closeSkillEditModal);
document.getElementById('btn-cancel-modal')?.addEventListener('click', closeSkillEditModal);
document.getElementById('modal-overlay')?.addEventListener('click', closeSkillEditModal);

document.getElementById('btn-save-skill-edit')?.addEventListener('click', async () => {
    const msgEl = document.getElementById('edit-skill-msg');
    const btn = document.getElementById('btn-save-skill-edit');
    const skillId = document.getElementById('edit-skill-id').value;
    const name = document.getElementById('edit-skill-name').value.trim();
    const summary = document.getElementById('edit-skill-summary').value.trim();
    hideMsg(msgEl);

    if (!name) {
        showMsg(msgEl, '技能名称不能为空', 'error');
        return;
    }

    setLoading(btn, true);
    try {
        if (skillId) {
            await apiRequest('PATCH', `/skill/my-skills/${skillId}`, { name, summary }, true);
        } else if (pendingUploadFile) {
            const formData = new FormData();
            formData.append('name', name);
            if (summary) formData.append('summary', summary);
            formData.append('file', pendingUploadFile);

            const res = await fetch(API + '/skill/upload', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + state.accessToken },
                body: formData,
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '上传失败');
        }
        closeSkillEditModal();
        loadMySkills();
    } catch (err) {
        showMsg(msgEl, err.message, 'error');
    } finally {
        setLoading(btn, false);
    }
});

async function loadMySkills() {
    const listEl = document.getElementById('my-skill-list');
    const emptyEl = document.getElementById('my-skill-empty');
    try {
        const data = await apiRequest('GET', '/skill/my-skills', null, true);
        if (!data || data.length === 0) {
            listEl.innerHTML = '';
            emptyEl.classList.remove('hidden');
            return;
        }
        emptyEl.classList.add('hidden');
        renderMySkillList(data);
    } catch (err) {
        listEl.innerHTML = `<div class="skill-error">加载失败: ${escapeHtml(err.message)}</div>`;
    }
}

function renderMySkillList(skills) {
    const listEl = document.getElementById('my-skill-list');
    let html = '<div class="my-skill-items">';
    skills.forEach(skill => {
        const summary = skill.summary.length > 80
            ? skill.summary.substring(0, 77) + '...'
            : skill.summary || '无摘要';
        html += `
            <div class="my-skill-card" data-skill-id="${skill.id}">
                <div class="my-skill-card-header">
                    <span class="my-skill-name">${escapeHtml(skill.name)}</span>
                    <button class="btn btn-ghost btn-sm my-skill-delete" data-delete-skill-id="${skill.id}" data-delete-skill-name="${escapeHtml(skill.name)}">删除</button>
                </div>
                <div class="my-skill-summary">${escapeHtml(summary)}</div>
                <div class="my-skill-time">${escapeHtml(skill.updated_at)}</div>
            </div>
        `;
    });
    html += '</div>';
    listEl.innerHTML = html;
}

// 事件委托：处理技能卡片点击和删除
document.getElementById('my-skill-list')?.addEventListener('click', (e) => {
    const deleteBtn = e.target.closest('[data-delete-skill-id]');
    if (deleteBtn) {
        e.stopPropagation();
        const id = parseInt(deleteBtn.dataset.deleteSkillId);
        const name = deleteBtn.dataset.deleteSkillName;
        deleteMySkill(id, name);
        return;
    }
    const card = e.target.closest('.my-skill-card');
    if (card) {
        const id = parseInt(card.dataset.skillId);
        viewMySkill(id);
    }
});

async function viewMySkill(skillId) {
    const panel = document.getElementById('skill-detail-panel');
    const titleEl = document.getElementById('skill-detail-title');
    const summaryEl = document.getElementById('skill-detail-summary');
    const contentEl = document.getElementById('skill-detail-content');

    try {
        const data = await apiRequest('GET', `/skill/my-skills/${skillId}`, null, true);
        currentViewingSkill = data;
        titleEl.textContent = data.name;
        summaryEl.innerHTML = data.summary
            ? `<div class="skill-detail-label">摘要</div><div>${escapeHtml(data.summary)}</div>`
            : '';
        const content = data.content || '';
        if (typeof marked !== 'undefined' && marked.parse) {
            contentEl.innerHTML = marked.parse(content);
        } else {
            contentEl.innerHTML = '<pre>' + escapeHtml(content) + '</pre>';
        }
        panel.classList.remove('hidden');
        panel.scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
        alert('加载失败: ' + err.message);
    }
}

document.getElementById('btn-close-skill-detail')?.addEventListener('click', () => {
    document.getElementById('skill-detail-panel')?.classList.add('hidden');
    currentViewingSkill = null;
});

document.getElementById('btn-edit-skill-detail')?.addEventListener('click', () => {
    if (!currentViewingSkill) return;
    openSkillEditModal(currentViewingSkill.id, currentViewingSkill.name, currentViewingSkill.summary);
});

async function deleteMySkill(skillId, skillName) {
    if (!confirm(`确定要删除技能「${skillName}」吗？`)) return;
    try {
        await apiRequest('DELETE', `/skill/my-skills/${skillId}`, null, true);
        document.getElementById('skill-detail-panel')?.classList.add('hidden');
        loadMySkills();
    } catch (err) {
        alert('删除失败: ' + err.message);
    }
}

// Skill 健康检查
document.getElementById('btn-skill-health')?.addEventListener('click', async () => {
    const msgEl = document.getElementById('skill-health-result');
    try {
        const data = await apiRequest('GET', '/skill/health');
        showMsg(msgEl, '服务正常: ' + (data.status || 'ok') + (data.api_key_set ? ' (API Key 已设置)' : ' (匿名模式)'), 'success');
    } catch (err) {
        showMsg(msgEl, '服务异常: ' + err.message, 'error');
    }
});
