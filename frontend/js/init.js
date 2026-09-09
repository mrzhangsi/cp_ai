/**
 * CP_AI — Init Module
 * 应用初始化 + 功能卡片导航
 */

// 功能卡片导航
document.querySelector('[data-feature="rag"]')?.addEventListener('click', () => {
    showView('view-rag');
    loadRAGDocuments();
});

document.querySelector('[data-feature="agent"]')?.addEventListener('click', () => {
    showView('view-agent');
    loadAgentSessions();
    loadAgentSkills();
});

document.querySelector('[data-feature="skill"]')?.addEventListener('click', () => {
    showView('view-skill');
});

document.querySelector('[data-feature="mcp"]')?.addEventListener('click', () => {
    showView('view-mcp');
});

document.getElementById('btn-back-rag')?.addEventListener('click', () => {
    showView('view-home');
});

document.getElementById('btn-back-agent')?.addEventListener('click', () => {
    showView('view-home');
});

document.getElementById('btn-back-skill')?.addEventListener('click', () => {
    showView('view-home');
});

document.getElementById('btn-back-mcp')?.addEventListener('click', () => {
    showView('view-home');
});

// 应用初始化
async function initApp() {
    if (isLoggedIn()) {
        try {
            await apiRequest('GET', '/auth/me', null, true);
            enterMainPage();
        } catch (_) {
            clearTokens();
            showPage('page-login');
        }
    } else {
        showPage('page-login');
    }
}

initApp();
