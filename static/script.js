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

function handleInput() {
    const input = document.getElementById('chatInput');
    const wave  = document.getElementById('waveIcon');
    const send  = document.getElementById('sendIcon');
    if (!input) return;
    const hasText = input.value.trim() !== '';
    if (wave) wave.style.display = hasText ? 'none'  : 'block';
    if (send) send.style.display = hasText ? 'block' : 'none';
}
window.handleInput = handleInput;
const chatInputEl = document.getElementById('chatInput');
if (chatInputEl) {
    chatInputEl.addEventListener('input', handleInput);
    handleInput();
}

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