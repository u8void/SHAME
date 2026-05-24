const toggleBtn       = document.getElementById('toggleBtn');
const mobileToggleBtn = document.getElementById('mobileToggleBtn');
const sidebar         = document.getElementById('sidebar');
const mainContent     = document.getElementById('mainContent');

if (sidebar) {
    const toggleSidebar = () => sidebar.classList.toggle('expanded');
    if (toggleBtn) toggleBtn.addEventListener('click', toggleSidebar);
    if (mobileToggleBtn) mobileToggleBtn.addEventListener('click', toggleSidebar);
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
document.addEventListener('click', (e) => {
    // Close attach menu if clicking outside
    const menu = document.getElementById('attachMenu');
    if (menu && menu.style.display === 'block') {
        if (!menu.contains(e.target) && !attachBtn.contains(e.target)) {
            menu.style.display = 'none';
        }
    }
    
    // Close sidebar on mobile if clicking outside
    if (window.innerWidth <= 768 && sidebar && sidebar.classList.contains('expanded')) {
        if (!sidebar.contains(e.target) && 
            (!mobileToggleBtn || !mobileToggleBtn.contains(e.target)) && 
            (!toggleBtn || !toggleBtn.contains(e.target))) {
            sidebar.classList.remove('expanded');
        }
    }
});