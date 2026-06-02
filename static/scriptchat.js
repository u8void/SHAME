window.fileCardCache = window.fileCardCache || {};

// ─── Shared download helper ───────────────────────────────────────────────
function normaliseExt(raw) {
    const m = {
        python: 'py', javascript: 'js', typescript: 'ts',
        markdown: 'md', bash: 'sh', shell: 'sh', sh: 'sh',
        jsx: 'jsx', tsx: 'tsx', html: 'html', css: 'css',
        json: 'json', yaml: 'yaml', yml: 'yml', toml: 'toml',
        rust: 'rs', go: 'go', cpp: 'cpp', c: 'c', java: 'java',
        kotlin: 'kt', swift: 'swift', rb: 'rb', ruby: 'rb',
        php: 'php', sql: 'sql', r: 'r',
    };
    const key = (raw || 'txt').toLowerCase();
    return m[key] || key;
}

function triggerDownload(filename, content) {
    const blob = new Blob([content], { type: 'text/plain' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

document.addEventListener("DOMContentLoaded", () => {
    let chats = JSON.parse(localStorage.getItem('iris_chats')) || [];
    let currentChatId = null;
    let chatActive = false;
    let currentAbortController = null;
    let isGenerating = false;
    let chatSettings = JSON.parse(localStorage.getItem('iris_chat_settings')) || {
        max_new_tokens: 512,
        temperature: 0.6,
        top_p: 0.9,
        top_k: 40,
        repetition_penalty: 1.3
    };

    fetch('/get_settings')
        .then(res => res.json())
        .then(data => {
            if (Object.keys(data).length > 0) {
                chatSettings = { ...chatSettings, ...data };
                localStorage.setItem('iris_chat_settings', JSON.stringify(chatSettings));
            }
        })
        .catch(e => console.error("Failed to load backend settings:", e));

    window.getChatSettings = () => chatSettings;
    window.setChatSettings = (s) => { chatSettings = s; };
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
    const imageInput            = document.getElementById("imageInput");
    const imagePreviewContainer = document.getElementById("imagePreviewContainer");
    const welcomeSection        = document.getElementById("welcomeSection");
    const mainContent           = document.getElementById("mainContent");
    const sidebar               = document.querySelector(".sidebar");
    const recentLabel           = document.getElementById("recentLabel") || document.querySelector(".recent-label");
    let selectedFile = null;

    function readFileAsText(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(reader.error);
            reader.readAsText(file);
        });
    }

    let searchOpen = false;
    let searchQuery = '';
    function savePersist() {
        localStorage.setItem('iris_chats', JSON.stringify(chats));
    }
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

    function enterChatMode() {
        chatActive = true;
        document.body.classList.add("chat-active");
        if (chatMessages) {
            chatMessages.style.display = '';   
            chatMessages.removeAttribute('hidden');
        }
        if (welcomeSection) welcomeSection.style.display = 'none';
    }

    function exitChatMode() {
        chatActive = false;
        document.body.classList.remove("chat-active");
        if (welcomeSection) welcomeSection.style.display = '';
    }

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
            appendMessageDOM(msg.role, msg.displayText || msg.content, false, msg.imageUrl, msg.attachmentName);
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

    function showTypingIndicator() {
        removeTypingIndicator();
        const div = document.createElement("div");
        div.classList.add("message", "ai-message", "typing-indicator");
        div.id = "typingIndicator";
        const content = document.createElement("div");
        content.classList.add("message-content");
        content.innerHTML = `
            <div class="thinking-text">
                <div class="thinking-dot-container">
                    <span class="thinking-dot"></span>
                    <span class="thinking-dot"></span>
                    <span class="thinking-dot"></span>
                </div>
                <span class="status-text-content">Thinking and finding the best answer...</span>
            </div>
        `;
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

        // Strip leading special tokens/headers that sometimes leak from certain models
        let formatted = text.replace(/^(\s|<\|endoftext\|>|<\|im_start\|>assistant<\|im_sep\|>|<\|im_end\|>)+/gi, '');

        return _formatRefined(formatted);
    }

    function _formatRefined(text) {
        if (!text) return '';
        const blocks = [];

        // 1. Extract Think Block (Internal)
        let work = text.replace(/<think>([\s\S]*?)(?:<\/think>|$)/gi, (match, p1) => {
            const id = `@@@THOUGHT_${blocks.length}@@@`;
            blocks.push({ type: 'thought', content: p1.trim() });
            return id;
        });

        work = work.replace(/\{[\s]*"action"[\s]*:[\s\S]*?\}/gi, (match) => {
            const id = `@@@ACTION_${blocks.length}@@@`;
            blocks.push({ type: 'action', content: match });
            return id;
        });

        work = work.replace(/<action_result>([\s\S]*?)(?:<\/action_result>|$)/gi, (match, p1) => {
            const id = `@@@RESULT_${blocks.length}@@@`;
            blocks.push({ type: 'result', content: p1.trim() });
            return id;
        });

        function isCommandOrShortBlock(lang, content) {
            const lowerLang = (lang || '').toLowerCase();
            if (['bash', 'sh', 'shell', 'cmd', 'powershell', 'terminal', 'run', 'install'].includes(lowerLang)) {
                return true;
            }
            const lines = content.split('\n');
            if (lines.length < 5 && content.length < 200) {
                return true;
            }
            if (lines.length <= 2 && (content.includes('python ') || content.includes('pip ') || content.includes('npm ') || content.includes('node '))) {
                return true;
            }
            return false;
        }

        work = work.replace(/```([^\n`]*)\n?([\s\S]*?)(?:```|$)/gi, (match, lang, codeContent) => {
            const id = `@@@CODE_${blocks.length}@@@`;
            const detectedLang = lang.trim() || 'code';
            const contentTrimmed = codeContent.trim();
            const isCmdOrShort = isCommandOrShortBlock(detectedLang, contentTrimmed);
            blocks.push({
                type: 'code',
                lang: detectedLang,
                content: contentTrimmed,
                hidden: !isCmdOrShort,
                autoCard: !isCmdOrShort,
                claimed: false
            });
            return id;
        });

        // Extract explicit file_card tags emitted by the AI — they override the auto-generated card
        work = work.replace(/<file_card\s+([^>]*?)(?:\/>|>\s*<\/file_card>)/gi,
            (match, attrsStr, offset) => {
                const filenameMatch = attrsStr.match(/filename=["']([^"']+)["']/i);
                const langMatch     = attrsStr.match(/lang=["']([^"']+)["']/i);
                const filename      = filenameMatch ? filenameMatch[1] : 'file.txt';
                const lang          = langMatch ? langMatch[1] : 'text';

                // Find the closest unclaimed code block physically preceding this tag in the string
                const beforeSub = work.substring(0, offset);
                const placeholderRegex = /@@@CODE_(\d+)@@@/g;
                let matchPlaceholder;
                const blockIndices = [];
                while ((matchPlaceholder = placeholderRegex.exec(beforeSub)) !== null) {
                    blockIndices.push(parseInt(matchPlaceholder[1], 10));
                }

                let codeIndex = -1;
                // 1. Try to find a non-command/non-short block first
                for (let j = blockIndices.length - 1; j >= 0; j--) {
                    const idx = blockIndices[j];
                    const block = blocks[idx];
                    if (block && block.type === 'code' && !block.claimed) {
                        const isCmdOrShort = isCommandOrShortBlock(block.lang, block.content);
                        if (!isCmdOrShort) {
                            codeIndex = idx;
                            break;
                        }
                    }
                }

                // 2. Fallback to the closest unclaimed code block if no non-command block is found
                if (codeIndex === -1) {
                    for (let j = blockIndices.length - 1; j >= 0; j--) {
                        const idx = blockIndices[j];
                        const block = blocks[idx];
                        if (block && block.type === 'code' && !block.claimed) {
                            codeIndex = idx;
                            break;
                        }
                    }
                }

                let fileCardId = '';
                if (codeIndex !== -1) {
                    blocks[codeIndex].claimed  = true;
                    blocks[codeIndex].hidden   = true;
                    blocks[codeIndex].autoCard = false; // explicit tag takes over
                    fileCardId = 'fc_' + Math.random().toString(36).substr(2, 9);
                    window.fileCardCache = window.fileCardCache || {};
                    window.fileCardCache[fileCardId] = blocks[codeIndex].content;
                }

                const id = `@@@FILECARD_${blocks.length}@@@`;
                blocks.push({ type: 'filecard', filename, lang: lang.trim(), fileCardId });
                return id;
            }
        );

        if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            work = marked.parse(work, { breaks: true, gfm: true });
            work = DOMPurify.sanitize(work);
            // marked wraps block-level text in <p>, which would break our injected <div>s. Let's unwrap placeholders.
            work = work.replace(/<p>(@@@[A-Z_0-9]+@@@)<\/p>/g, '$1');
        } else {
            work = escapeHtml(work);
            work = work.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            work = work.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
            work = work.replace(/\n/g, '<br>');
        }

        // 5. Re-inject blocks
        blocks.forEach((block, index) => {
            let id, html;
            if (block.type === 'thought') {
                id = `@@@THOUGHT_${index}@@@`;
                html = `
                    <div class="thought-wrapper">
                        <div class="thought-header" onclick="this.parentElement.classList.toggle('expanded')">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.7"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                            <span>Thought Process</span>
                            <svg class="chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                        </div>
                        <div class="thought-content">${escapeHtml(block.content).replace(/\n/g, '<br>')}</div>
                    </div>
                `;
            } else if (block.type === 'action') {
                id = `@@@ACTION_${index}@@@`;
                try {
                    const obj = JSON.parse(block.content);
                    if (obj.action === "chat" && obj.response) {
                        html = escapeHtml(obj.response).replace(/\n/g, '<br>');
                    } else {
                        html = `<div class="action-result-stream" style="font-size:12px; color:#a385ff; opacity:0.8;">⚙️ Action: ${escapeHtml(obj.action)}</div>`;
                    }
                } catch (e) {
                    html = escapeHtml(block.content).replace(/\n/g, '<br>');
                }
            } else if (block.type === 'result') {
                id = `@@@RESULT_${index}@@@`;
                html = `<div class='action-result-stream' style='font-size:13.5px; margin-top: 12px; padding: 12px; background: rgba(163, 133, 255, 0.05); border: 1px solid rgba(163, 133, 255, 0.2); border-radius: 8px;'><strong>Result:</strong><br>${escapeHtml(block.content).replace(/\n/g, '<br>')}</div>`;
            } else if (block.type === 'filecard') {
                id = `@@@FILECARD_${index}@@@`;
                const safeFilename = escapeHtml(block.filename);
                const safeLang     = escapeHtml(block.lang);
                const safeId       = escapeHtml(block.fileCardId || '');
                html = `
                    <div class="file-card"
                         onclick="window.openCodeViewer(this)"
                         data-filename="${safeFilename}"
                         data-lang="${safeLang}"
                         data-filecard-id="${safeId}">
                        <div class="file-card-icon">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                                 stroke="currentColor" stroke-width="1.7"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12
                                         a2 2 0 0 0 2-2V8z"></path>
                                <polyline points="14 2 14 8 20 8"></polyline>
                                <line x1="16" y1="13" x2="8" y2="13"></line>
                                <line x1="16" y1="17" x2="8" y2="17"></line>
                                <polyline points="10 9 9 9 8 9"></polyline>
                            </svg>
                        </div>
                        <div class="file-card-meta">
                            <div class="file-card-name">${safeFilename}</div>
                            <div class="file-card-sub">${safeLang} file</div>
                        </div>
                        <button class="file-card-download"
                                onclick="event.stopPropagation(); window.downloadFileCard(this)"
                                data-filename="${safeFilename}"
                                data-filecard-id="${safeId}">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                                 stroke="currentColor" stroke-width="2"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                <polyline points="7 10 12 15 17 10"></polyline>
                                <line x1="12" y1="15" x2="12" y2="3"></line>
                            </svg>
                            Download
                        </button>
                    </div>
                `;
            } else if (block.type === 'code') {
                id = `@@@CODE_${index}@@@`;
                if (block.hidden) {
                    // Auto-generate a file card for hidden blocks that weren't claimed by an explicit <file_card> tag
                    if (block.autoCard && block.content) {
                        const autoLang = block.lang || 'code';
                        const ext      = normaliseExt(autoLang);
                        const autoFilename = `generated_code.${ext}`;
                        const fcId     = 'fc_' + Math.random().toString(36).substr(2, 9);
                        window.fileCardCache = window.fileCardCache || {};
                        window.fileCardCache[fcId] = block.content;
                        const safeFilename = escapeHtml(autoFilename);
                        const safeLang     = escapeHtml(autoLang);
                        html = `
                            <div class="file-card"
                                 onclick="window.openCodeViewer(this)"
                                 data-filename="${safeFilename}"
                                 data-lang="${safeLang}"
                                 data-filecard-id="${fcId}">
                                <div class="file-card-icon">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                                         stroke="currentColor" stroke-width="1.7"
                                         stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12
                                                 a2 2 0 0 0 2-2V8z"></path>
                                        <polyline points="14 2 14 8 20 8"></polyline>
                                        <line x1="16" y1="13" x2="8" y2="13"></line>
                                        <line x1="16" y1="17" x2="8" y2="17"></line>
                                        <polyline points="10 9 9 9 8 9"></polyline>
                                    </svg>
                                </div>
                                <div class="file-card-meta">
                                    <div class="file-card-name">${safeFilename}</div>
                                    <div class="file-card-sub">${safeLang} file</div>
                                </div>
                                <button class="file-card-download"
                                        onclick="event.stopPropagation(); window.downloadFileCard(this)"
                                        data-filename="${safeFilename}"
                                        data-filecard-id="${fcId}">
                                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                                         stroke="currentColor" stroke-width="2"
                                         stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                        <polyline points="7 10 12 15 17 10"></polyline>
                                        <line x1="12" y1="15" x2="12" y2="3"></line>
                                    </svg>
                                    Download
                                </button>
                            </div>
                        `;
                    } else {
                        html = '';
                    }
                } else {
                    html = `
                        <div class="code-container">
                            <div class="code-header">
                                <span class="code-lang">${escapeHtml(block.lang)}</span>
                                <div style="display: flex; gap: 8px;">
                                    <button class="copy-btn" onclick="downloadCode(this, '${escapeHtml(block.lang)}')">
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                                        Download
                                    </button>
                                    <button class="copy-btn" onclick="copyToClipboard(this)">
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                        Copy
                                    </button>
                                </div>
                            </div>
                            <pre><code>${escapeHtml(block.content)}</code></pre>
                        </div>
                    `;
                }
            } else {
                id = `@@@${block.type.toUpperCase()}_${index}@@@`;
                html = '';
            }
            work = work.replace(id, html);
        });

        return work;
    }
window.downloadCode = (btn, ext) => {
    const container   = btn.closest('.code-container');
    const codeElement = container.querySelector('pre code');
    const text        = codeElement.textContent;
    triggerDownload('generated_code.' + normaliseExt(ext), text);
};

    window.copyToClipboard = (btn) => {
        const container = btn.closest('.code-container');
        const codeElement = container.querySelector('pre code');
        const text = codeElement.textContent;
        
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

    function appendMessageDOM(role, text, scroll = true, imageUrl = null, attachmentName = null) {
        const outer = document.createElement("div");
        outer.classList.add("message", role === "user" ? "user-message" : "ai-message");

        const inner = document.createElement("div");
        inner.classList.add("message-content");
        
        if (imageUrl) {
            const img = document.createElement("img");
            img.src = imageUrl;
            img.classList.add("chat-image");
            inner.appendChild(img);
        } else if (attachmentName) {
            const fileBox = document.createElement("div");
            fileBox.className = "chat-file-attachment";
            fileBox.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                </svg>
                <span>${escapeHtml(attachmentName)}</span>
            `;
            inner.appendChild(fileBox);
        }

        if (role === "bot") {
            const div = document.createElement("div");
            div.innerHTML = formatMessage(text);
            inner.appendChild(div);
        } else if (text) {
            const div = document.createElement("div");
            div.textContent = text;
            inner.appendChild(div);
        }

        outer.appendChild(inner);
        chatMessages.appendChild(outer);
        if (scroll) chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    async function handleSendMessage() {
        const text = chatInput.value.trim();
        const hasFile = !!selectedFile;
        const isImage = hasFile && selectedFile.type.startsWith('image/');
        if (!text && !hasFile) return;

        if (!currentChatId || !chats.find(c => c.id === currentChatId)) {
            startNewChat();
        }

        const chat = normaliseChat(chats.find(c => c.id === currentChatId));

        if (chat.messages.length === 0) {
            chat.title = text ? (text.length > 35 ? text.slice(0, 35) + '…' : text) : (hasFile ? selectedFile.name : "New Conversation");
        }

        let displayImageUrl = null;
        let attachmentName = null;
        let finalContent = text;

        if (hasFile) {
            if (isImage) {
                displayImageUrl = URL.createObjectURL(selectedFile);
            } else {
                attachmentName = selectedFile.name;
                
                // Show a warning if file size > 1MB
                if (selectedFile.size > 1024 * 1024) {
                    alert("File is too large. Please select a file under 1MB.");
                    return;
                }

                try {
                    const fileContent = await readFileAsText(selectedFile);
                    const ext = attachmentName.split('.').pop().toLowerCase();
                    
                    finalContent = `I have attached a file named \`${attachmentName}\`. Here is the content of the file:\n\n` +
                                   `\`\`\`${ext}\n` +
                                   `${fileContent}\n` +
                                   `\`\`\`\n\n` +
                                   `User Prompt:\n${text}`;
                } catch (e) {
                    console.error("Failed to read file:", e);
                    alert("Could not read file content.");
                    return;
                }
            }
        }

        const messageObj = {
            role: 'user',
            content: finalContent,
            displayText: text || `[Attached: ${attachmentName}]`,
            imageUrl: displayImageUrl,
            attachmentName: attachmentName
        };

        chat.messages.push(messageObj);
        savePersist();
        renderChatList();

        enterChatMode();
        appendMessageDOM('user', messageObj.displayText, true, displayImageUrl, attachmentName);

        chatInput.value = '';
        const fileToUpload = selectedFile; // keep reference
        clearFileSelection(); // clear for next message
        
        if (typeof handleInputResize === 'function') handleInputResize();

        setGeneratingState(true);
        showTypingIndicator();

        let fullReply = "";
        let actionResult = "";
        let aiMessageDiv = null;
        let aiContentDiv = null;

        try {
            // Unified Path: Always send to /chat (Agent Path)
            const formData = new FormData();
            if (hasFile && isImage) {
                formData.append('image', fileToUpload);
            }
            formData.append('message', finalContent);
            formData.append('chat_id', currentChatId);
            formData.append('messages', JSON.stringify(chat.messages));
            formData.append('history', chat.historyString);
            formData.append('settings', JSON.stringify(chatSettings));
            const modeSelector = document.getElementById("proModeSelector");
            if (modeSelector) {
                formData.append('mode', modeSelector.value);
            }

            currentAbortController = new AbortController();
            const response = await fetch('/chat', {
                method: 'POST',
                body: formData,
                signal: currentAbortController.signal
            });

            if (!response.ok) {
                const errText = await response.text().catch(() => response.status);
                throw new Error(`Server error ${response.status}: ${errText}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            
            // Create the container but keep it hidden until the first text/token arrives
            aiMessageDiv = document.createElement("div");
            aiMessageDiv.classList.add("message", "ai-message");
            aiMessageDiv.style.display = "none";
            aiContentDiv = document.createElement("div");
            aiContentDiv.classList.add("message-content");
            aiMessageDiv.appendChild(aiContentDiv);
            chatMessages.appendChild(aiMessageDiv);

            let currentResponseText = "";
            let rawResponseText = "";
            let renderPending = false;  // rAF debounce flag
            let renderFrameId = null;
            let firstTokenReceived = false;

            // Flush accumulated tokens to the DOM at display frame rate (≤60fps),
            // not at token-generation rate (potentially 100s/sec).
            function scheduleRender() {
                if (renderPending) return;
                renderPending = true;
                renderFrameId = requestAnimationFrame(() => {
                    try {
                        if (!firstTokenReceived) {
                            removeTypingIndicator();
                            aiMessageDiv.style.display = "";
                            firstTokenReceived = true;
                        }
                        aiContentDiv.innerHTML = formatMessage(currentResponseText);
                        chatMessages.scrollTop = chatMessages.scrollHeight;
                    } catch (e) {
                        console.error("Render error:", e);
                    } finally {
                        renderPending = false;
                        renderFrameId = null;
                    }
                });
            }

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n\n");
                buffer = lines.pop();

                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    const jsonStr = line.replace("data: ", "");
                    try {
                        const event = JSON.parse(jsonStr);
                        if (event.type === "token" || event.type === "text") {
                            currentResponseText += event.content;
                            scheduleRender();
                        } else if (event.type === "status") {
                            
                            console.log("[Agent Status]", event.content);
                            if (!firstTokenReceived) {
                                const ind = document.getElementById("typingIndicator");
                                if (ind) {
                                    const span = ind.querySelector(".status-text-content");
                                    if (span) span.textContent = event.content;
                                }
                            }
                        } else if (event.type === "action_result") {
                            
                            currentResponseText += "\n\n<action_result>" + event.content + "</action_result>";
                            scheduleRender();
                        } else if (event.type === "clear") {
                            if (renderFrameId !== null) {
                                cancelAnimationFrame(renderFrameId);
                                renderFrameId = null;
                            }
                            renderPending = false;
                            currentResponseText = "";
                            rawResponseText = "";
                            firstTokenReceived = false;
                            aiContentDiv.innerHTML = "";
                            aiMessageDiv.style.display = "none";
                            showTypingIndicator();
                        } else if (event.type === "raw_response") {
                            rawResponseText = event.content;
                        }
                    } catch (e) { console.error("Event parse error", e); }
                }
                
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }

            setGeneratingState(false);
            if (!firstTokenReceived) {
                removeTypingIndicator();
                aiMessageDiv.style.display = "";
            }
            
            // Clean up currentResponseText before saving to prevent corrupting the LLM context
            let cleanResponse = rawResponseText || currentResponseText;
            try {
                // If the response contains a JSON action block, we extract the action result 
                // and store ONLY the clean text in history, avoiding massive JSON duplication
                const match = cleanResponse.match(/\{[\s\S]*?"action"[\s\S]*?\}/i);
                if (match) {
                    const actionObj = JSON.parse(match[0]);
                    if (actionObj.action === "chat" && actionObj.response) {
                        cleanResponse = actionObj.response;
                    }
                }
            } catch (e) {}
            
            chat.messages.push({ role: 'bot', content: cleanResponse });
            savePersist();

        } catch (err) {
            console.error('[Iris] fetch error:', err);
            removeTypingIndicator();
            if (err.name === 'AbortError') {
                appendMessageDOM('bot', `⚠️ Generation stopped by user.`);
            } else {
                appendMessageDOM('bot', `⚠️ ${err.message || 'Could not reach the server.'}`);
            }
        } finally {
            setGeneratingState(false);
            chatInput.focus();
        }
    }

    function setGeneratingState(generating) {
        isGenerating = generating;
        chatInput.disabled = generating;
        
        if (generating) {
            sendBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect></svg>`;
            sendBtn.setAttribute("aria-label", "Stop generation");
            sendBtn.classList.add("stop-btn");
        } else {
            sendBtn.innerHTML = `<h3>&nbsp;➤&nbsp;</h3>`;
            sendBtn.setAttribute("aria-label", "Send message");
            sendBtn.classList.remove("stop-btn");
            currentAbortController = null;
        }
    }

    const handleInputResize = () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = (chatInput.scrollHeight) + 'px';
    };
    chatInput.addEventListener('input', handleInputResize);

    sendBtn.addEventListener('click', () => {
        if (isGenerating) {
            if (currentAbortController) currentAbortController.abort();
        } else {
            handleSendMessage();
            setTimeout(handleInputResize, 10);
        }
    });

    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!isGenerating) {
                handleSendMessage();
                setTimeout(handleInputResize, 10);
            }
        }
    });
    newChatBtn.addEventListener('click', startNewChat);

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

    window.appendMessage = appendMessageDOM;

    imageInput?.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;

        selectedFile = file;
        const isImage = file.type.startsWith('image/');

        if (isImage) {
            const reader = new FileReader();
            reader.onload = (e) => {
                imagePreviewContainer.innerHTML = `
                    <img src="${e.target.result}" alt="Preview">
                    <button class="remove-image-btn" id="removeImageBtn" title="Remove image">✕</button>
                `;
                imagePreviewContainer.classList.add('visible');
                document.getElementById('removeImageBtn')?.addEventListener('click', clearFileSelection);
            };
            reader.readAsDataURL(file);
        } else {
            imagePreviewContainer.innerHTML = `
                <div class="file-preview-box">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                    <span class="file-preview-name">${escapeHtml(file.name)}</span>
                </div>
                <button class="remove-image-btn" id="removeImageBtn" title="Remove file">✕</button>
            `;
            imagePreviewContainer.classList.add('visible');
            document.getElementById('removeImageBtn')?.addEventListener('click', clearFileSelection);
        }
    });

    function clearFileSelection() {
        selectedFile = null;
        if (imageInput) imageInput.value = '';
        imagePreviewContainer.innerHTML = '';
        imagePreviewContainer.classList.remove('visible');
    }

    chats = chats.map(normaliseChat);

    if (chats.length > 0) {
        loadChat(chats[0].id);
    } else {
        startNewChat();
    }
});

// ═══════════════════════════════════════════════════════════════
//  CODE VIEWER PANEL  –  global functions
// ═══════════════════════════════════════════════════════════════
(function () {
    // Build the overlay + panel DOM once
    const overlay = document.createElement('div');
    overlay.className = 'code-viewer-overlay';
    overlay.addEventListener('click', closeViewer);

    const panel = document.createElement('div');
    panel.className = 'code-viewer-panel';
    panel.innerHTML = `
        <div class="code-viewer-header">
            <div class="code-viewer-filename" id="cvFilename">file.txt</div>
            <span class="code-viewer-lang-badge" id="cvLang">text</span>
            <div class="code-viewer-actions">
                <button class="code-viewer-btn primary" id="cvDownloadBtn">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" stroke-width="2"
                         stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                    Download
                </button>
                <button class="code-viewer-btn" id="cvCopyBtn">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" stroke-width="2"
                         stroke-linecap="round" stroke-linejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                    Copy
                </button>
            </div>
            <button class="code-viewer-close" id="cvCloseBtn" title="Close">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>
        <div class="code-viewer-line-numbers">
            <div class="code-viewer-gutters" id="cvGutters"></div>
            <div class="code-viewer-body" id="cvBody">
                <pre><code id="cvCode"></code></pre>
            </div>
        </div>
        <div class="code-viewer-footer">
            <div class="code-viewer-footer-stat">Lines: <span id="cvLineCount">0</span></div>
            <div class="code-viewer-footer-stat">Chars: <span id="cvCharCount">0</span></div>
        </div>
    `;

    document.body.appendChild(overlay);
    document.body.appendChild(panel);

    document.getElementById('cvCloseBtn').addEventListener('click', closeViewer);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeViewer(); });

    document.getElementById('cvCopyBtn').addEventListener('click', () => {
        const text = document.getElementById('cvCode').textContent;
        navigator.clipboard.writeText(text).then(() => {
            const btn = document.getElementById('cvCopyBtn');
            const orig = btn.innerHTML;
            btn.innerHTML = '✓ Copied!';
            btn.style.color = '#a385ff';
            setTimeout(() => { btn.innerHTML = orig; btn.style.color = ''; }, 1800);
        });
    });

    document.getElementById('cvDownloadBtn').addEventListener('click', () => {
        const filename = document.getElementById('cvFilename').textContent;
        const content  = document.getElementById('cvCode').textContent;
        triggerDownload(filename, content);
    });

    let currentCardEl = null;

    function openViewer(filename, lang, code) {
        document.getElementById('cvFilename').textContent = filename;
        document.getElementById('cvLang').textContent     = lang;

        const escaped = code
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        document.getElementById('cvCode').innerHTML = escaped;

        // Build line-number gutter
        const lines   = code.split('\n');
        const gutters = document.getElementById('cvGutters');
        gutters.innerHTML = lines
            .map((_, i) => `<div class="code-viewer-gutter-line">${i + 1}</div>`)
            .join('');

        document.getElementById('cvLineCount').textContent = lines.length;
        document.getElementById('cvCharCount').textContent = code.length.toLocaleString();

        // Sync scroll between gutter and body
        const body = document.getElementById('cvBody');
        body.addEventListener('scroll', () => { gutters.scrollTop = body.scrollTop; });

        overlay.classList.add('visible');
        requestAnimationFrame(() => panel.classList.add('open'));
    }

    function closeViewer() {
        panel.classList.remove('open');
        overlay.classList.remove('visible');
        currentCardEl = null;
    }

    // Called when user clicks anywhere on the file card
    window.openCodeViewer = function (cardEl) {
        currentCardEl = cardEl;
        const filename = cardEl.dataset.filename;
        const lang     = cardEl.dataset.lang;
        const fcId     = cardEl.dataset.filecardId;
        const codeText = window.fileCardCache[fcId] || '';
        openViewer(filename, lang, codeText);
    };

    // Called from the Download button inside the file card
    window.downloadFileCard = function (btn) {
        const card     = btn.closest('.file-card');
        const filename = card.dataset.filename;
        const fcId     = card.dataset.filecardId;
        const codeText = window.fileCardCache[fcId] || '';
        triggerDownload(filename, codeText);
    };
})();
