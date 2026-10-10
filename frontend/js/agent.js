/**
 * CP_AI — Agent Module
 * 会话管理 + 流式聊天 + 技能选择 + 多模态文件上传
 */

agentState.currentSkillId = null;
agentState.mySkills = [];
agentState.pendingFiles = [];

async function loadAgentSessions() {
    try {
        const data = await apiRequest('GET', '/agent/sessions', null, true);
        agentState.sessions = data;
        renderSessionList();
    } catch (err) {
        console.error('加载会话列表失败:', err);
    }
}

async function loadAgentSkills() {
    try {
        const data = await apiRequest('GET', '/skill/my-skills', null, true);
        agentState.mySkills = data || [];
        renderSkillSelect();
    } catch (_) {}
}

function renderSkillSelect() {
    const select = document.getElementById('chat-skill-select');
    if (!select) return;
    const current = select.value;
    select.innerHTML = '<option value="">无（默认）</option>';
    agentState.mySkills.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.name;
        select.appendChild(opt);
    });
    if (current) select.value = current;
}

function renderSessionList() {
    const list = document.getElementById('session-list');
    if (!list) return;
    list.innerHTML = agentState.sessions.map(s => {
        const hasSkill = s.skill_id != null;
        return `
        <div class="session-item ${s.session_id === agentState.currentSession ? 'active' : ''}"
             onclick="selectAgentSession('${s.session_id}')">
            <span class="session-title">${escapeHtml(s.title)}${hasSkill ? ' <span class="session-skill-badge">⚡</span>' : ''}</span>
            <span class="session-delete" onclick="event.stopPropagation(); deleteAgentSession('${s.session_id}')">✕</span>
        </div>`;
    }).join('');
}

async function selectAgentSession(sessionId) {
    agentState.currentSession = sessionId;
    renderSessionList();
    await loadChatHistory(sessionId);
    restoreSessionSkill(sessionId);
    clearPendingFiles();
}

function restoreSessionSkill(sessionId) {
    const session = agentState.sessions.find(s => s.session_id === sessionId);
    const select = document.getElementById('chat-skill-select');
    const status = document.getElementById('chat-skill-status');
    if (!session || !select) return;

    const skillId = session.skill_id;
    select.value = skillId || '';
    agentState.currentSkillId = skillId || null;
    updateSkillStatus(skillId);
}

function updateSkillStatus(skillId) {
    const status = document.getElementById('chat-skill-status');
    if (!status) return;
    if (skillId) {
        const skill = agentState.mySkills.find(s => s.id === skillId);
        status.textContent = skill ? skill.name : '';
        status.classList.add('active');
    } else {
        status.textContent = '';
        status.classList.remove('active');
    }
}

async function setSessionSkill(sessionId, skillId) {
    try {
        await apiRequest('PATCH', `/agent/sessions/${sessionId}/skill`, { skill_id: skillId || null }, true);
        agentState.currentSkillId = skillId || null;
        updateSkillStatus(skillId);
        await loadAgentSessions();
    } catch (err) {
        console.error('更新会话技能失败:', err);
    }
}

async function createAgentSession() {
    const skillId = agentState.currentSkillId || null;
    try {
        const body = {};
        if (skillId) body.skill_id = skillId;
        const data = await apiRequest('POST', '/agent/sessions', body, true);
        agentState.currentSession = data.session_id;
        await loadAgentSessions();
        clearChatMessages();
    } catch (err) {
        console.error('创建会话失败:', err);
    }
}

async function deleteAgentSession(sessionId) {
    try {
        await apiRequest('DELETE', `/agent/sessions/${sessionId}`, null, true);
        if (agentState.currentSession === sessionId) {
            agentState.currentSession = null;
            clearChatMessages();
        }
        await loadAgentSessions();
    } catch (err) {
        console.error('删除会话失败:', err);
    }
}

async function loadChatHistory(sessionId) {
    try {
        const messages = await apiRequest('GET', `/agent/sessions/${sessionId}/messages`, null, true);
        clearChatMessages();
        messages.forEach(msg => {
            if (msg.role !== 'system') {
                appendChatMessage(msg.role, msg.content, msg.metadata);
            }
        });
    } catch (err) {
        console.error('加载聊天历史失败:', err);
    }
}

function clearChatMessages() {
    const container = document.getElementById('chat-messages');
    if (container) container.innerHTML = '';
}

// ============================================
// 文件上传处理
// ============================================

function addPendingFiles(files) {
    for (const file of files) {
        const MAX_SIZE = 20 * 1024 * 1024;
        if (file.size > MAX_SIZE) {
            alert(`文件 ${file.name} 超出 20MB 限制`);
            continue;
        }
        agentState.pendingFiles.push(file);
    }
    renderAttachmentBar();
}

function removePendingFile(index) {
    agentState.pendingFiles.splice(index, 1);
    renderAttachmentBar();
}

function clearPendingFiles() {
    agentState.pendingFiles = [];
    renderAttachmentBar();
    const input = document.getElementById('chat-file-input');
    if (input) input.value = '';
}

function renderAttachmentBar() {
    const bar = document.getElementById('chat-attachment-bar');
    if (!bar) return;
    bar.innerHTML = agentState.pendingFiles.map((file, i) => {
        const isImage = file.type.startsWith('image/');
        const thumb = isImage
            ? `<img src="${URL.createObjectURL(file)}" alt="">`
            : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>`;
        return `
        <div class="chat-attachment-item">
            ${thumb}
            <span class="chat-attachment-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
            <span class="chat-attachment-remove" onclick="removePendingFile(${i})">✕</span>
        </div>`;
    }).join('');
}

function renderAttachmentPreview(attachments) {
    if (!attachments || attachments.length === 0) return '';
    const items = attachments.map(a => {
        const icon = a.type === 'image' ? '🖼️' : a.type === 'audio' ? '🔊' : '📄';
        return `<span class="message-attachment"><span class="message-attachment-name">${icon} ${escapeHtml(a.name)}</span></span>`;
    }).join('');
    return `<div class="message-attachments">${items}</div>`;
}

// ============================================
// 消息渲染
// ============================================

/**
 * 向聊天容器追加一条消息
 * @param {'user'|'assistant'} role
 * @param {string} content
 * @param {object|null} metadata
 * @returns {HTMLDivElement|undefined}
 */
function appendChatMessage(role, content, metadata) {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    const div = document.createElement('div');
    div.className = `chat-message ${role}`;
    const attachHtml = (role === 'user' && metadata?.attachments)
        ? renderAttachmentPreview(metadata.attachments) : '';
    div.innerHTML = `
        <div class="message-label">${role === 'user' ? '你' : '助手'}</div>
        ${attachHtml}
        <div class="message-bubble">${escapeHtml(content)}</div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

function createStreamingBubble() {
    const container = document.getElementById('chat-messages');
    if (!container) return null;
    const div = document.createElement('div');
    div.className = 'chat-message assistant';
    div.innerHTML = `
        <div class="message-label">助手</div>
        <div class="message-bubble"></div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

// ============================================
// 发送消息（支持文件上传）
// ============================================

async function sendAgentMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    const hasFiles = agentState.pendingFiles.length > 0;
    if (!message && !hasFiles) return;

    if (!agentState.currentSession) {
        await createAgentSession();
    }

    const filesToSend = [...agentState.pendingFiles];
    clearPendingFiles();

    // 渲染用户消息
    if (hasFiles) {
        const attachments = filesToSend.map(f => {
            const isImage = f.type.startsWith('image/');
            return { name: f.name, type: isImage ? 'image' : 'document', size: f.size };
        });
        appendChatMessage('user', message || '(已上传 ' + filesToSend.length + ' 个文件)', { attachments });
    } else {
        appendChatMessage('user', message);
    }

    input.value = '';
    input.style.height = 'auto';

    const bubble = createStreamingBubble();
    if (!bubble) return;
    const bubbleContent = bubble.querySelector('.message-bubble');

    const btnSend = document.getElementById('btn-send');
    btnSend.disabled = true;
    btnSend.dataset.originalText = btnSend.textContent;
    btnSend.textContent = '生成中...';

    try {
        let res;
        const remember = document.getElementById('chat-remember')?.checked !== false;
        if (hasFiles) {
            const formData = new FormData();
            formData.append('session_id', agentState.currentSession);
            formData.append('message', message || '');
            formData.append('remember', remember);
            if (agentState.currentSkillId) {
                formData.append('skill_id', agentState.currentSkillId);
            }
            for (const file of filesToSend) {
                formData.append('files', file);
            }
            res = await fetch(API + '/agent/chat/stream', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + state.accessToken },
                body: formData,
            });
        } else {
            const formData = new FormData();
            formData.append('session_id', agentState.currentSession);
            formData.append('message', message);
            formData.append('remember', remember);
            if (agentState.currentSkillId) {
                formData.append('skill_id', agentState.currentSkillId);
            }
            res = await fetch(API + '/agent/chat/stream', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + state.accessToken },
                body: formData,
            });
        }

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || '请求失败 (' + res.status + ')');
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullText = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const jsonStr = line.slice(6);
                if (!jsonStr) continue;

                try {
                    const event = JSON.parse(jsonStr);

                    if (event.type === 'token') {
                        fullText += event.content;
                        bubbleContent.textContent = fullText;
                        bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
                    } else if (event.type === 'tool_start') {
                        bubbleContent.innerHTML = `<span class="tool-status">正在调用 ${escapeHtml(event.name)}...</span>`;
                        bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
                    } else if (event.type === 'tool_end') {
                        let toolResult = event.result;
                        try {
                            const parsed = JSON.parse(toolResult);
                            toolResult = JSON.stringify(parsed, null, 2);
                        } catch (_) {}
                        bubbleContent.innerHTML = `<div class="tool-result"><div class="tool-result-label">工具 ${escapeHtml(event.name)} 返回：</div><pre>${escapeHtml(toolResult)}</pre></div>`;
                        bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
                    } else if (event.type === 'error') {
                        bubbleContent.innerHTML = `<span class="tool-status" style="color: var(--error);">错误: ${escapeHtml(event.message)}</span>`;
                        bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
                    } else if (event.type === 'done') {
                        await loadAgentSessions();
                    }
                } catch (_) {}
            }
        }
    } catch (err) {
        bubbleContent.textContent = '[错误: ' + err.message + ']';
    } finally {
        btnSend.disabled = false;
        btnSend.textContent = btnSend.dataset.originalText || '发送';
    }
}

// ============================================
// 事件绑定
// ============================================

document.getElementById('btn-send')?.addEventListener('click', sendAgentMessage);
document.getElementById('btn-new-session')?.addEventListener('click', createAgentSession);

document.getElementById('chat-file-input')?.addEventListener('change', function() {
    if (this.files.length > 0) {
        addPendingFiles(this.files);
    }
    this.value = '';
});

document.getElementById('chat-skill-select')?.addEventListener('change', function() {
    const skillId = this.value ? parseInt(this.value) : null;
    agentState.currentSkillId = skillId;
    updateSkillStatus(skillId);
    if (agentState.currentSession) {
        setSessionSkill(agentState.currentSession, skillId);
    }
});

document.getElementById('chat-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendAgentMessage();
    }
});

document.getElementById('chat-input')?.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 150) + 'px';
});
