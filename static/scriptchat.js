document.addEventListener("DOMContentLoaded", () => {
    // ── State ──────────────────────────────────────────────────────────
    let chats = JSON.parse(localStorage.getItem('iris_chats')) || [];
    let currentChatId = null;
    let chatActive = false;

    let chatSettings = JSON.parse(localStorage.getItem('iris_chat_settings')) || {
        max_new_tokens: 200,
        temperature: 0.6,
        top_p: 0.9,
        top_k: 40,
        repetition_penalty: 1.3
    };

    // Expose settings so settings.js can update them
    window.getChatSettings = () => chatSettings;
    window.setChatSettings = (s) => { chatSettings = s; };

    // ── DOM refs ────────────────────────────────────────────────────────
    const chatInput          = document.getElementById("chatInput");
    const sendBtn            = document.getElementById("sendBtn");
    const chatMessages       = document.getElementById("chatMessages");
    const chatHistory        = document.getElementById("chatHistory");
    const newChatBtn         = document.getElementById("newChatBtn");
    const searchToggleBtn    = document.getElementById("searchToggleBtn");
    const searchBarContainer = document.getElementById("searchBarContainer");
    const searchInput        = document.getElementById("searchInput");
    const searchClearBtn     = document.getElementById("searchClearBtn");
    const searchEmpty        = document.getElementById("searchEmpty");
    const recentLabel        = document.getElementById("recentLabel");
    const sidebar            = document.getElementById("sidebar");
    const mainContent        = document.getElementById("mainContent");
    const centerPanel        = document.getElementById("centerPanel");
    const welcomeSection     = document.getElementById("welcomeSection");

    let searchOpen = false;
    let searchQuery = '';

    // ── Helpers ─────────────────────────────────────────────────────────
    function savePersist() {
        localStorage.setItem('iris_chats', JSON.stringify(chats));
    }

    // Guard: ensure older saved chats always have historyString
    function normaliseChat(chat) {
        if (typeof chat.historyString !== 'string') chat.historyString = '';
        if (!Array.isArray(chat.messages)) chat.messages = [];
        return chat;
    }

    function highlightMatch(text, query) {
        if (!query) return escapeHtml(text);
        const escaped = escapeHtml(text);
        const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return escaped.replace(
            new RegExp(`(${escapedQuery})`, 'gi'),
            '<mark class="search-highlight">$1</mark>'
        );
    }

    function renderChatList(query = '') {
        if (!chatHistory) return;
        chatHistory.innerHTML = '';
        const q = query.trim().toLowerCase();
        let visibleCount = 0;

        chats.forEach(chat => {
            if (q && !chat.title.toLowerCase().includes(q)) return;
            visibleCount++;

            const item = document.createElement('div');
            item.className = `chat-history-item${chat.id === currentChatId ? ' active' : ''}`;
            item.innerHTML = `
                <span class="chat-history-item-title">${highlightMatch(chat.title, q)}</span>
                <button class="chat-delete-btn" data-id="${chat.id}" title="Delete">✕</button>
            `;
            item.querySelector('.chat-history-item-title').addEventListener('click', () => loadChat(chat.id));
            item.querySelector('.chat-delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                deleteChat(chat.id);
            });
            chatHistory.appendChild(item);
        });

        if (recentLabel) recentLabel.textContent = q ? `Results (${visibleCount})` : 'Recent Chats';
        if (searchEmpty) searchEmpty.classList.toggle('visible', q !== '' && visibleCount === 0);
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    // ── UI mode ──────────────────────────────────────────────────────────
    // Directly control visibility so the reply container is always reachable
    // in the DOM regardless of which CSS class the stylesheet uses.
    function enterChatMode() {
        chatActive = true;
        document.body.classList.add("chat-active");
        if (chatMessages) {
            chatMessages.style.display = '';   // let CSS decide, but remove any forced hide
            chatMessages.removeAttribute('hidden');
        }
        if (welcomeSection) welcomeSection.style.display = 'none';
    }

    function exitChatMode() {
        chatActive = false;
        document.body.classList.remove("chat-active");
        if (welcomeSection) welcomeSection.style.display = '';
    }

    // ── Chat lifecycle ───────────────────────────────────────────────────
    function startNewChat() {
        const id = Date.now().toString();
        chats.unshift({ id, title: 'New Conversation', messages: [], historyString: '' });
        currentChatId = id;
        savePersist();
        closeSearch();
        renderChatList();
        chatMessages.innerHTML = '';
        exitChatMode();
    }

    function loadChat(id) {
        currentChatId = id;
        const chat = normaliseChat(chats.find(c => c.id === id) || {});
        if (!chat.id) return;

        chatMessages.innerHTML = '';
        chat.messages.forEach(msg => {
            appendMessageDOM(msg.role, msg.content, false);
        });

        if (chat.messages.length > 0) {
            enterChatMode();
            chatMessages.scrollTop = chatMessages.scrollHeight;
        } else {
            exitChatMode();
        }
        renderChatList();
    }

    function deleteChat(id) {
        chats = chats.filter(c => c.id !== id);
        savePersist();
        if (currentChatId === id) {
            if (chats.length > 0) loadChat(chats[0].id);
            else startNewChat();
        } else {
            renderChatList();
        }
    }

    // ── Typing indicator ─────────────────────────────────────────────────
    function showTypingIndicator() {
        removeTypingIndicator(); // avoid duplicates
        const div = document.createElement("div");
        div.classList.add("message", "ai-message", "typing-indicator");
        div.id = "typingIndicator";
        const content = document.createElement("div");
        content.classList.add("message-content");
        content.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
        div.appendChild(content);
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function removeTypingIndicator() {
        const el = document.getElementById("typingIndicator");
        if (el) el.remove();
    }

    function formatMessage(text) {
        if (!text) return '';

        // 1. Handle code blocks: <code>...</code>
        const codeBlocks = [];
        let formatted = text.replace(/<code>([\s\S]*?)<\/code>/gi, (match, codeContent) => {
            const placeholder = `__CODE_BLOCK_${codeBlocks.length}__`;
            codeBlocks.push(codeContent.trim());
            return placeholder;
        });

        // 2. Escape other HTML
        formatted = escapeHtml(formatted);

        // 3. Bold: **text**
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // 4. Numbered Lists: 1. Item 2. Item ...
        // We capture multi-line content using [\s\S]*? and ensure we look ahead for the next number or end
        formatted = formatted.replace(/(?:^|\n| )(\d+\.\s+[\s\S]*?)(?=(?:\n\s*\d+\.\s+)|(?:\s+\d+\.\s+)|$)/g, (match, p1) => {
            const content = p1.replace(/^\d+\.\s+/, '').trim();
            // Optional: If it looks like "Title: Description", put Description on a new line
            const refinedContent = content.replace(/^(.+?:\s+)/, '<strong>$1</strong><br>');
            return `<li>${refinedContent}</li>`;
        });

        // Wrap consecutive <li> (allowing spaces/newlines between them) into <ol>
        formatted = formatted.replace(/(<li>[\s\S]*?<\/li>(?:\s*<li>[\s\S]*?<\/li>)*)/g, '<ol>$1</ol>');

        // 5. Restore Code Blocks
        codeBlocks.forEach((code, index) => {
            const placeholder = `__CODE_BLOCK_${index}__`;
            const codeHtml = `
                <div class="code-container">
                    <div class="code-header">
                        <span class="code-lang">Code</span>
                        <button class="copy-btn" onclick="copyToClipboard(this, \`${escapeHtml(code).replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`)">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                            Copy
                        </button>
                    </div>
                    <pre><code>${escapeHtml(code)}</code></pre>
                </div>
            `;
            formatted = formatted.replace(placeholder, codeHtml);
        });

        // 6. Final cleanup: Convert remaining newlines to <br> (avoiding already handled blocks)
        // We only do this for text NOT inside <ol> or <pre>
        // A simple way is to replace \n with <br> then fix the tags
        formatted = formatted.replace(/\n/g, '<br>');

        return formatted;
    }

    // Global helper for copy button
    window.copyToClipboard = (btn, text) => {
        navigator.clipboard.writeText(text).then(() => {
            const originalHtml = btn.innerHTML;
            btn.innerHTML = '<span>✓ Copied!</span>';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.innerHTML = originalHtml;
                btn.classList.remove('copied');
            }, 2000);
        }).catch(err => {
            console.error('Failed to copy: ', err);
        });
    };

    // ── Message DOM ───────────────────────────────────────────────────────
    function appendMessageDOM(role, text, scroll = true) {
        const outer = document.createElement("div");
        outer.classList.add("message", role === "user" ? "user-message" : "ai-message");

        const inner = document.createElement("div");
        inner.classList.add("message-content");
        
        if (role === "bot") {
            inner.innerHTML = formatMessage(text);
        } else {
            inner.textContent = text;
        }

        outer.appendChild(inner);
        chatMessages.appendChild(outer);
        if (scroll) chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // ── Send message ──────────────────────────────────────────────────────
    async function handleSendMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        // Ensure there's always a valid current chat
        if (!currentChatId || !chats.find(c => c.id === currentChatId)) {
            startNewChat();
        }

        const chat = normaliseChat(chats.find(c => c.id === currentChatId));

        // First message sets the chat title
        if (chat.messages.length === 0) {
            chat.title = text.length > 35 ? text.slice(0, 35) + '…' : text;
        }

        chat.messages.push({ role: 'user', content: text });
        savePersist();
        renderChatList();

        // Show the user bubble and switch into chat layout BEFORE the fetch
        enterChatMode();
        appendMessageDOM('user', text);

        chatInput.value = '';
        if (typeof handleInput === 'function') handleInput();

        setInputDisabled(true);
        showTypingIndicator();

        try {
            const res = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chat_id: currentChatId,
                    message: text,
                    history: chat.historyString,
                    settings: chatSettings
                })
            });

            if (!res.ok) {
                const errText = await res.text().catch(() => res.status);
                throw new Error(`Server error ${res.status}: ${errText}`);
            }

            const data  = await res.json();
            const reply = (data.reply || '').trim() || '…';

            chat.messages.push({ role: 'bot', content: reply });
            chat.historyString += `User: ${text}\nBot: ${reply}\n`;

            // Trim history to last 80 non-empty lines to cap token growth
            const lines = chat.historyString.split('\n').filter(l => l.trim());
            if (lines.length > 80) {
                chat.historyString = lines.slice(-80).join('\n') + '\n';
            }

            savePersist();
            removeTypingIndicator();
            appendMessageDOM('bot', reply);

        } catch (err) {
            console.error('[Iris] fetch error:', err);
            removeTypingIndicator();
            appendMessageDOM('bot', `⚠️ ${err.message || 'Could not reach the server. Make sure the backend is running.'}`);
        } finally {
            setInputDisabled(false);
            chatInput.focus();
        }
    }

    function setInputDisabled(disabled) {
        chatInput.disabled = disabled;
        sendBtn.disabled   = disabled;
    }

    // ── Event listeners ──────────────────────────────────────────────────
    sendBtn.addEventListener('click', handleSendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });
    newChatBtn.addEventListener('click', startNewChat);

    // ── Search ────────────────────────────────────────────────────────────
    function openSearch() {
        searchOpen = true;
        searchBarContainer?.classList.add('open');
        searchToggleBtn?.classList.add('active');
        if (sidebar && !sidebar.classList.contains('expanded')) {
            sidebar.classList.add('expanded');
            if (mainContent) mainContent.style.marginLeft = 'var(--sidebar-expanded)';
        }
        setTimeout(() => searchInput?.focus(), 320);
    }

    function closeSearch() {
        searchOpen = false;
        searchQuery = '';
        searchBarContainer?.classList.remove('open');
        searchToggleBtn?.classList.remove('active');
        if (searchInput) searchInput.value = '';
        searchClearBtn?.classList.remove('visible');
        if (recentLabel) recentLabel.textContent = 'Recent Chats';
        if (searchEmpty) searchEmpty.classList.remove('visible');
        renderChatList();
    }

    searchToggleBtn?.addEventListener('click', () => {
        searchOpen ? closeSearch() : openSearch();
    });

    searchInput?.addEventListener('input', () => {
        searchQuery = searchInput.value;
        searchClearBtn?.classList.toggle('visible', searchQuery.length > 0);
        renderChatList(searchQuery);
    });

    searchInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeSearch();
    });

    searchClearBtn?.addEventListener('click', () => {
        searchQuery = '';
        if (searchInput) searchInput.value = '';
        searchClearBtn.classList.remove('visible');
        searchInput?.focus();
        renderChatList();
        if (recentLabel) recentLabel.textContent = 'Recent Chats';
        if (searchEmpty) searchEmpty.classList.remove('visible');
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && searchOpen && document.activeElement !== chatInput) {
            closeSearch();
        }
    });

    // ── Expose globally (for settings.js) ───────────────────────────────
    window.appendMessage = appendMessageDOM;

    // ── Init ─────────────────────────────────────────────────────────────
    // Normalise all persisted chats on load (fixes missing historyString field)
    chats = chats.map(normaliseChat);

    if (chats.length > 0) {
        loadChat(chats[0].id);
    } else {
        startNewChat();
    }
});
