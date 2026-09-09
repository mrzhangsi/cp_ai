/**
 * CP_AI — Auth Module
 * 登录 / 注册 / 退出
 */

// 登录/注册 Tab 切换
document.querySelectorAll('.login-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const panel = tab.dataset.panel;
        document.querySelectorAll('.login-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        document.querySelectorAll('.login-form').forEach(f => f.classList.remove('active'));
        document.querySelector(`.login-form[data-panel="${panel}"]`)?.classList.add('active');
    });
});

// 登录
document.getElementById('form-login').addEventListener('submit', async (e) => {
    e.preventDefault();
    const msgEl = document.getElementById('login-msg');
    const btn = document.getElementById('btn-login');
    hideMsg(msgEl);

    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;

    setLoading(btn, true);
    try {
        const formBody = new URLSearchParams();
        formBody.append('username', username);
        formBody.append('password', password);

        const res = await fetch(API + '/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formBody.toString(),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || '登录失败');

        const access = data[0]?.token || '';
        const refresh = data[1]?.token || '';
        saveTokens(access, refresh, username);

        try {
            const me = await apiRequest('GET', '/auth/me', null, true);
            state.username = me.username;
            localStorage.setItem('cp_username', me.username);
        } catch (_) {}

        enterMainPage();
    } catch (err) {
        showMsg(msgEl, err.message, 'error');
    } finally {
        setLoading(btn, false);
    }
});

// 注册
document.getElementById('form-register').addEventListener('submit', async (e) => {
    e.preventDefault();
    const msgEl = document.getElementById('register-msg');
    const btn = document.getElementById('btn-register');
    hideMsg(msgEl);

    const body = {
        username: document.getElementById('reg-username').value,
        password: document.getElementById('reg-password').value,
    };
    const email = document.getElementById('reg-email').value;
    if (email) body.email = email;

    setLoading(btn, true);
    try {
        const data = await apiRequest('POST', '/auth/register', body);
        const access = data[0]?.token || '';
        const refresh = data[1]?.token || '';
        saveTokens(access, refresh, body.username);
        showMsg(msgEl, '注册成功！', 'success');
        setTimeout(() => enterMainPage(), 600);
    } catch (err) {
        showMsg(msgEl, err.message, 'error');
    } finally {
        setLoading(btn, false);
    }
});

// 退出登录
document.getElementById('btn-logout').addEventListener('click', async () => {
    try {
        await apiRequest('POST', '/auth/logout', null, true);
    } catch (_) {}
    clearTokens();
    showPage('page-login');
    document.getElementById('form-login').reset();
    hideMsg(document.getElementById('login-msg'));
    hideMsg(document.getElementById('register-msg'));
});
