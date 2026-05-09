// ── Sidebar toggle ────────────────────────────────────────────────────────────
const toggleBtn   = document.getElementById('toggleBtn');
const sidebar     = document.getElementById('sidebar');
const mainContent = document.getElementById('mainContent');

if (toggleBtn && sidebar && mainContent) {
    toggleBtn.addEventListener('click', () => {
        sidebar.classList.toggle('expanded');
        mainContent.style.marginLeft = sidebar.classList.contains('expanded')
            ? 'var(--sidebar-expanded)'
            : 'var(--sidebar-collapsed)';
    });
}

// ── Send-button icon swap (wave ↔ arrow) ──────────────────────────────────────
// Only runs if the optional waveIcon / sendIcon elements exist in the HTML.
function handleInput() {
    const input = document.getElementById('chatInput');
    const wave  = document.getElementById('waveIcon');
    const send  = document.getElementById('sendIcon');

    if (!input) return;                     // element missing — bail out safely

    const hasText = input.value.trim() !== '';
    if (wave) wave.style.display = hasText ? 'none'  : 'block';
    if (send) send.style.display = hasText ? 'block' : 'none';
}

// Expose globally so scriptchat.js can call it after clearing the input
window.handleInput = handleInput;

const chatInputEl = document.getElementById('chatInput');
if (chatInputEl) {
    chatInputEl.addEventListener('input', handleInput);
    handleInput(); // set correct initial state
}

// ── Attach-menu (optional UI element) ────────────────────────────────────────
const attachBtn = document.getElementById('attachBtn');
if (attachBtn) {
    attachBtn.addEventListener('click', (event) => {
        event.stopPropagation();
        const menu = document.getElementById('attachMenu');
        if (menu) menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
    });
}

document.addEventListener('click', () => {
    const menu = document.getElementById('attachMenu');
    if (menu) menu.style.display = 'none';
});
