/**
 * CP_AI — Utility Module
 * 全局状态、API 请求、工具函数、路由
 */

const API = '';

// ============================================
// 状态管理
// ============================================

/** @type {{ accessToken: string, refreshToken: string, username: string }} */
const state = {
    accessToken: localStorage.getItem('cp_access_token') || '',
    refreshToken: localStorage.getItem('cp_refresh_token') || '',
    username: localStorage.getItem('cp_username') || '',
};

const agentState = {
    currentSession: null,
    sessions: [],
};

/**
 * 保存 token 和用户名到状态与 localStorage
 * @param {string} accessToken
 * @param {string} refreshToken
 * @param {string} username
 */
function saveTokens(accessToken, refreshToken, username) {
    state.accessToken = accessToken;
    state.refreshToken = refreshToken;
    state.username = username || '';
    localStorage.setItem('cp_access_token', accessToken);
    localStorage.setItem('cp_refresh_token', refreshToken);
    localStorage.setItem('cp_username', username || '');
}

function clearTokens() {
    state.accessToken = '';
    state.refreshToken = '';
    state.username = '';
    localStorage.removeItem('cp_access_token');
    localStorage.removeItem('cp_refresh_token');
    localStorage.removeItem('cp_username');
}

function isLoggedIn() {
    return !!state.accessToken;
}

// ============================================
// 工具函数
// ============================================

/**
 * 在指定元素上显示消息
 * @param {HTMLElement} el
 * @param {string} text
 * @param {'info'|'success'|'error'} type
 */
function showMsg(el, text, type = 'info') {
    el.className = 'msg ' + type;
    el.textContent = text;
    el.classList.remove('hidden');
}

function hideMsg(el) {
    el.classList.add('hidden');
}

/**
 * 在结果区域显示数据
 * @param {HTMLElement} el
 * @param {string|object} data
 * @param {'info'|'success'|'error'} type
 */
function showResult(el, data, type = 'info') {
    el.className = 'result-area ' + type;
    if (typeof data === 'object') {
        el.textContent = JSON.stringify(data, null, 2);
    } else {
        el.textContent = data;
    }
    el.classList.remove('hidden');
    document.getElementById('query-empty')?.classList.add('hidden');
}

/**
 * 切换按钮的加载状态
 * @param {HTMLButtonElement} btn
 * @param {boolean} loading
 */
function setLoading(btn, loading) {
    if (loading) {
        btn.disabled = true;
        btn.dataset.originalText = btn.textContent;
        btn.textContent = '加载中...';
    } else {
        btn.disabled = false;
        btn.textContent = btn.dataset.originalText || btn.textContent;
    }
}

/**
 * 发送 API 请求
 * @param {string} method
 * @param {string} path
 * @param {object|null} body
 * @param {boolean} useAuth
 * @returns {Promise<any>}
 */
async function apiRequest(method, path, body = null, useAuth = false) {
    const headers = {};
    const isFormData = body instanceof FormData;
    if (!isFormData && body) headers['Content-Type'] = 'application/json';
    if (useAuth) {
        if (!state.accessToken) throw new Error('未登录，请先登录');
        headers['Authorization'] = 'Bearer ' + state.accessToken;
    }
    const opts = { method, headers };
    if (body) opts.body = isFormData ? body : JSON.stringify(body);
    const res = await fetch(API + path, opts);
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.detail || '请求失败 (' + res.status + ')');
    }
    return data;
}

/**
 * HTML 转义，防止 XSS
 * @param {string} text
 * @returns {string}
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

/**
 * 格式化日期字符串
 * @param {string} isoStr
 * @returns {string}
 */
function formatDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

/**
 * 格式化文件大小
 * @param {number} bytes
 * @returns {string}
 */
function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

// ============================================
// 路由
// ============================================

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(pageId)?.classList.add('active');
}

function showView(viewId) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById(viewId)?.classList.add('active');
}

function enterMainPage() {
    showPage('page-main');
    document.getElementById('display-username').textContent = state.username || '用户';
    showView('view-home');
}

// ============================================
// 通用确认弹窗
// ============================================

/**
 * 自定义 confirm 弹窗，返回 Promise<boolean>
 * @param {string} message
 * @param {string} [title='确认操作']
 * @param {string} [okText='确定']
 * @returns {Promise<boolean>}
 */
function confirmModal(message, title = '确认操作', okText = '确定') {
    return new Promise((resolve) => {
        const overlay = document.getElementById('modal-confirm');
        const titleEl = document.getElementById('modal-confirm-title');
        const msgEl = document.getElementById('modal-confirm-message');
        const okBtn = document.getElementById('modal-confirm-ok');
        const cancelBtn = document.getElementById('modal-confirm-cancel');

        if (!overlay) { resolve(false); return; }

        titleEl.textContent = title;
        msgEl.textContent = message;
        okBtn.textContent = okText;
        overlay.classList.remove('hidden');

        function cleanup() {
            overlay.classList.add('hidden');
            okBtn.removeEventListener('click', onOk);
            cancelBtn.removeEventListener('click', onCancel);
            overlay.removeEventListener('click', onBg);
        }
        function onOk() { cleanup(); resolve(true); }
        function onCancel() { cleanup(); resolve(false); }
        function onBg(e) { if (e.target === overlay) { cleanup(); resolve(false); } }

        okBtn.addEventListener('click', onOk);
        cancelBtn.addEventListener('click', onCancel);
        overlay.addEventListener('click', onBg);
    });
}
