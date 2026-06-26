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
    window.selectedFiles = [];
    let chatSettings = JSON.parse(localStorage.getItem('iris_chat_settings')) || {
        max_new_tokens: 512,
        temperature: 0.6,
        top_p: 0.9,
        top_k: 40,
        repetition_penalty: 1.05,
        code_review: false
    };

    // Force migrate old bad default of 1.3 down to 1.05
    if (chatSettings.repetition_penalty === 1.3) {
        chatSettings.repetition_penalty = 1.05;
        localStorage.setItem('iris_chat_settings', JSON.stringify(chatSettings));
    }

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

    function renderSelectedFiles() {
        if (!imagePreviewContainer) return;
        imagePreviewContainer.innerHTML = '';
        window.selectedFiles.forEach((file, index) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'file-preview-item';
            wrapper.innerHTML = `
                <span>${escapeHtml(file.name)}</span>
                <button onclick="window.selectedFiles.splice(${index}, 1); renderSelectedFiles();">✕</button>
            `;
            imagePreviewContainer.appendChild(wrapper);
        });
    }

    function handleFilesSelect(files) {
        if (!files) return;
        Array.from(files).forEach(file => {
            window.selectedFiles.push(file);
        });
        renderSelectedFiles();
    }

    function clearFileSelection() {
        window.selectedFiles = [];
        if (imagePreviewContainer) imagePreviewContainer.innerHTML = '';
        if (imageInput) imageInput.value = '';
    }

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
    
    // ── Regenerate the conversation title based on actual topic ──
    function regenerateTitle(chat, debounceMs) {
        if (debounceMs === undefined) debounceMs = 3000;
        const key = chat.id;
        if (!regenerateTitle._pending) regenerateTitle._pending = {};
        if (regenerateTitle._pending[key]) return;
        regenerateTitle._pending[key] = true;
        setTimeout(() => {
            delete regenerateTitle._pending[key];
            const target = chats.find(c => c.id === key);
            if (!target) return;
            const msgs = target.messages || [];
            if (msgs.length === 0) return;
            fetch('/generate_title', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages: msgs })
            })
            .then(res => res.json())
            .then(data => {
                if (data.title && data.title !== "New Conversation") {
                    const t = chats.find(c => c.id === key);
                    if (t && t.title !== data.title) {
                        t.title = data.title;
                        savePersist();
                        renderChatList();
                    }
                }
            })
            .catch(err => console.error("Title regeneration failed:", err));
        }, debounceMs);
    }
    regenerateTitle._pending = {};

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

    function formatActionNormally(obj) {
        const action = (obj.action || '').trim().toLowerCase();
        const params = obj.parameters || obj || {};
        
        function getVal(...keys) {
            for (const k of keys) {
                if (params[k] !== undefined && params[k] !== null) return String(params[k]);
            }
            for (const k of keys) {
                if (obj[k] !== undefined && obj[k] !== null) return String(obj[k]);
            }
            return '';
        }

        if (action.includes("close") || action.includes("kill") || action === "kill_app") {
            let name = getVal("name", "app");
            if (!name) {
                for (const [k, v] of Object.entries(params)) {
                    if (String(v).toLowerCase() === "true" || String(v) === "1" || String(v).toLowerCase() === "yes" || String(v).toLowerCase() === "close" || String(v).toLowerCase() === "kill") {
                        name = k;
                        break;
                    }
                }
            }
            if (!name) {
                const parts = action.split(/\s+/);
                if (parts.length > 1) name = parts.slice(1).join(' ');
            }
            return `⚙️ Closing ${name || 'application'}...`;
        }

        if (action.includes("open") && action.includes("website")) {
            const url = getVal("url", "website", "link");
            return `⚙️ Opening website: ${url || 'URL'}...`;
        }

        if (action.includes("open")) {
            let name = getVal("name", "app");
            if (!name) {
                for (const [k, v] of Object.entries(params)) {
                    if (String(v).toLowerCase() === "true" || String(v) === "1" || String(v).toLowerCase() === "yes" || String(v).toLowerCase() === "open") {
                        name = k;
                        break;
                    }
                }
            }
            if (!name) {
                const parts = action.split(/\s+/);
                if (parts.length > 1) name = parts.slice(1).join(' ');
            }
            return `⚙️ Opening ${name || 'application'}...`;
        }

        if (action.includes("youtube") && action.includes("channel")) {
            const name = getVal("name", "channel");
            return `⚙️ Opening YouTube channel: ${name}...`;
        }

        if (action.includes("youtube")) {
            const query = getVal("query", "video", "search");
            return `⚙️ Playing '${query}' on YouTube...`;
        }

        if (action.includes("spotify")) {
            const query = getVal("query", "song", "search");
            return `⚙️ Playing '${query}' on Spotify...`;
        }

        if (action.includes("email")) {
            const to = getVal("to", "recipient");
            const subj = getVal("subject", "sub");
            const subjStr = subj ? ` (Subject: ${subj})` : '';
            return `Sending email to ${to}${subjStr}...`;
        }

        if (action.includes("search") && action.includes("file")) {
            const query = getVal("query", "name");
            const folder = getVal("folder", "dir");
            return `Searching for '${query}' in '${folder || 'Documents'}'...`;
        }

        if (action.includes("file")) {
            const path = getVal("path", "file");
            return `Opening file: ${path}...`;
        }

        if (action.includes("terminal")) {
            const cmd = getVal("command", "cmd");
            return `Opening terminal and running: \`${cmd}\`...`;
        }

        if (action.includes("command")) {
            const cmd = getVal("command", "cmd");
            return `Running command: \`${cmd}\`...`;
        }

        if (action === "volume_up") return "Increasing system volume...";
        if (action === "volume_down") return "Decreasing system volume...";
        if (action === "volume_mute") return "Muting system volume...";
        if (action.includes("volume_set") || action.includes("volume")) {
            const pct = getVal("percent", "pct", "level", "value");
            return `Setting system volume to ${pct}%...`;
        }

        if (action === "brightness_up") return "Increasing screen brightness...";
        if (action === "brightness_down") return "Decreasing screen brightness...";
        if (action.includes("brightness_set") || action.includes("brightness")) {
            const pct = getVal("percent", "pct", "level", "value");
            return `Setting screen brightness to ${pct}%...`;
        }

        if (action.includes("system")) {
            const what = getVal("what", "info", "query");
            return `Retrieving system ${what || 'information'}...`;
        }

        if (action.includes("clipboard") && action.includes("copy")) return "Copying text to clipboard...";
        if (action.includes("clipboard") && action.includes("read")) return "Reading clipboard content...";

        const cleanAction = action.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        return `Performing action: ${cleanAction}...`;
    }

    function formatMessage(text, isStreaming = false) {
        if (!text) return '';

        // Strip leading special tokens/headers that sometimes leak from certain models
        let formatted = text.replace(/^(\s|<\|endoftext\|>|<\|im_start\|>assistant<\|im_sep\|>|<\|im_end\|>)+/gi, '');

        return _formatRefined(formatted, isStreaming);
    }

    function _formatRefined(text, isStreaming = false) {
        if (!text) return '';
        let work = text;
        const blocks = [];

        // 1. Extract action JSON blocks and results FIRST so they aren't swallowed by think blocks
        let startIdx = work.indexOf('{');
        while (startIdx !== -1) {
            let braceCount = 0;
            let endIdx = -1;
            for (let i = startIdx; i < work.length; i++) {
                const char = work[i];
                if (char === '{') {
                    braceCount++;
                } else if (char === '}') {
                    braceCount--;
                    if (braceCount === 0) {
                        endIdx = i + 1;
                        break;
                    }
                }
            }
            if (endIdx !== -1) {
                const candidate = work.substring(startIdx, endIdx);
                if (candidate.includes('"action"') || candidate.includes("'action'")) {
                    const id = `@@@ACTION_${blocks.length}@@@`;
                    blocks.push({ type: 'action', content: candidate });
                    work = work.substring(0, startIdx) + id + work.substring(endIdx);
                    startIdx = work.indexOf('{', startIdx + id.length);
                    continue;
                }
            }
            startIdx = work.indexOf('{', startIdx + 1);
        }

        work = work.replace(/<action_result>([\s\S]*?)(?:<\/action_result>|$)/gi, (match, p1) => {
            const id = `@@@RESULT_${blocks.length}@@@`;
            blocks.push({ type: 'result', content: p1.trim() });
            return id;
        });

        // 2. Extract Think Block (Internal)
        let hasThought = false;
        work = work.replace(/(?:<think>|<\|thought_start\|>|<thought>)([\s\S]*?)(?:<\/think>|<\|thought_end\|>|<\/thought>|$)/gi, (match, p1) => {
            const content = p1.trim();
            if (!content) return ''; 
            if (hasThought) return '';

            const isClosed = /(?:<\/think>|<\|thought_end\|>|<\/thought>)$/i.test(match);
            const id = `@@@THOUGHT_${blocks.length}@@@`;
            blocks.push({ type: 'thought', content: content, isClosed: isClosed });
            hasThought = true;
            return id;
        });

        work = work.replace(/<coding>([\s\S]*?)(?:<\/coding>|$)/gi, (match, p1) => {
            const id = `@@@CODING_${blocks.length}@@@`;
            blocks.push({ type: 'coding', content: p1.trim() });
            return id;
        });

        work = work.replace(/<review>([\s\S]*?)(?:<\/review>|$)/gi, (match, p1) => {
            const id = `@@@REVIEW_${blocks.length}@@@`;
            blocks.push({ type: 'review', content: p1.trim() });
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
        // Auto-wrap raw HTML in backticks if the model forgot them (Browser Markdown Chokehold prevention)
        if (!work.includes("```html") && !work.includes("```\n<!DOCTYPE") && !work.includes("```\n<html") && !work.includes("```\n<div") && !work.includes("```\n<nav")) {
            // Find raw HTML blocks that appear on a new line and wrap them to the end of the text
            work = work.replace(/(?:^|\n)(?:html\s*\n|CODE\s*\n|CODE\s*\nhtml\s*\n)?((?:<!DOCTYPE|<html|<body|<nav|<div|<main|<header|<footer|<section|<canvas|<svg|<style|<script|<h1|<h2|<h3)[\s\S]*)$/i, '\n```html\n$1\n```\n');
        }

        work = work.replace(/```([^\n`]*)\n?([\s\S]*?)(?:```|$)/gi, (match, lang, codeContent) => {
            const id = `@@@CODE_${blocks.length}@@@`;
            const detectedLang = (lang || '').trim().replace(/@@@[A-Z0-9_]+@@@/gi, '') || 'code';
            
            // Find all thought placeholders inside the code content and move them outside
            const thoughtRegex = /@@@THOUGHT_\d+@@@/g;
            let extractedThoughts = "";
            let matchThought;
            while ((matchThought = thoughtRegex.exec(codeContent)) !== null) {
                extractedThoughts += "\n" + matchThought[0] + "\n";
            }
            
            const cleanContent = codeContent.replace(/@@@THOUGHT_\d+@@@/g, '').trim();
            const isCmdOrShort = isCommandOrShortBlock(detectedLang, cleanContent);
            const isFinished = match.endsWith('```');
            
            blocks.push({
                type: 'code',
                lang: detectedLang,
                content: cleanContent,
                hidden: !isCmdOrShort,
                autoCard: !isCmdOrShort,
                claimed: false,
                finished: isFinished
            });
            // Inject thoughts outside the code block placeholder
            return id + extractedThoughts;
        });

        // Extract explicit file_card tags emitted by the AI — they override the auto-generated card
        work = work.replace(/<file_card\s+([^>]*?)(?:\/>|>\s*<\/file_card>)/gi,
            (match, attrsStr, offset) => {
                const filenameMatch = attrsStr.match(/filename=["']([^"']+)["']/i);
                const langMatch     = attrsStr.match(/lang=["']([^"']+)["']/i);
                const filename      = filenameMatch ? filenameMatch[1] : 'file.txt';
                const lang          = langMatch ? langMatch[1] : 'text';

                // Find the closest unclaimed code block physically succeeding this tag in the string
                const afterSub = work.substring(offset);
                const placeholderRegex = /@@@CODE_(\d+)@@@/g;
                let matchPlaceholder;
                const blockIndices = [];
                while ((matchPlaceholder = placeholderRegex.exec(afterSub)) !== null) {
                    blockIndices.push(parseInt(matchPlaceholder[1], 10));
                }

                let codeIndex = -1;
                // 1. Try to find a non-command/non-short block first
                for (let j = 0; j < blockIndices.length; j++) {
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
                    for (let j = 0; j < blockIndices.length; j++) {
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
                    if (isStreaming) {
                        fileCardId = 'fc_stream_' + codeIndex;
                    } else {
                        let hash = 0;
                        const c = blocks[codeIndex].content;
                        for (let i = 0; i < c.length; i++) hash = Math.imul(31, hash) + c.charCodeAt(i) | 0;
                        fileCardId = 'fc_static_' + hash;
                    }
                    window.fileCardCache = window.fileCardCache || {};
                    window.fileCardCache[fileCardId] = blocks[codeIndex].content;
                }

                const id = `@@@FILECARD_${blocks.length}@@@`;
                blocks.push({ type: 'filecard', filename, lang: lang.trim(), fileCardId });
                return id;
            }
        );

        if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            if (typeof markedKatex !== 'undefined') {
                marked.use(markedKatex({ throwOnError: false }));
            }
            work = marked.parse(work, { breaks: true, gfm: true });
            const purifyConfig = {
                ADD_TAGS: ['math', 'mrow', 'mi', 'mo', 'mn', 'ms', 'mspace', 'mtext', 'menclose', 'merror', 'mphantom', 'mpadded', 'mroot', 'mfrac', 'msub', 'msup', 'msubsup', 'munder', 'mover', 'munderover', 'mmultiscripts', 'msection', 'maction', 'annotation', 'semantics'],
                ADD_ATTR: ['mathvariant', 'mathcolor', 'mathsize', 'mathbackground', 'display', 'xmlns']
            };
            work = DOMPurify.sanitize(work, purifyConfig);
            // marked wraps block-level text in <p>, which would break our injected <div>s. Let's unwrap placeholders.
            work = work.replace(/<p>(@@@[A-Z_0-9]+@@@)<\/p>/g, '$1');
        } else {
            work = escapeHtml(work);
            work = work.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            work = work.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
            work = work.replace(/\n/g, '<br>');
        }

        // 5. Re-inject blocks recursively
        const blockHtmlMap = {};
        blocks.forEach((block, index) => {
            let id, html;
            if (block.type === 'thought') {
                id = `@@@THOUGHT_${index}@@@`;
                const tKey = 't_' + index;
                window.toggledBlocks = window.toggledBlocks || {};
                let isExpanded = window.toggledBlocks[tKey] !== undefined ? window.toggledBlocks[tKey] : !block.isClosed;
                let inner = escapeHtml(block.content || '').replace(/\n/g, '<br>');

                if (!block.isClosed) {
                    const animDelay = -(Date.now() % 1000);
                    html = `
                        <div class="thought-wrapper ${isExpanded ? 'expanded' : ''}">
                            <div class="thought-header streaming" onclick="window.toggledBlocks['${tKey}'] = this.parentElement.classList.toggle('expanded')" style="cursor: pointer;">
                                <div class="thought-loader" style="animation-delay: ${animDelay}ms;"></div>
                                <span>Thinking...</span>
                            </div>
                            <div class="thought-content">${inner}</div>
                        </div>
                    `;
                } else {
                    html = `
                        <div class="thought-wrapper ${isExpanded ? 'expanded' : ''}">
                            <div class="thought-header" onclick="window.toggledBlocks['${tKey}'] = this.parentElement.classList.toggle('expanded')">
                                <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
                                <span>Thought Process</span>
                            </div>
                            <div class="thought-content">${inner}</div>
                        </div>
                    `;
                }
            } else if (block.type === 'coding') {
                id = `@@@CODING_${index}@@@`;
                const tKey = 'c_' + index;
                window.toggledBlocks = window.toggledBlocks || {};
                let isExpanded = window.toggledBlocks[tKey] !== undefined ? window.toggledBlocks[tKey] : true;
                let inner = '';
                if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                    const purifyConfig = { ADD_TAGS: ['math', 'mrow', 'mi', 'mo', 'mn', 'ms', 'mspace', 'mtext', 'menclose', 'merror', 'mphantom', 'mpadded', 'mroot', 'mfrac', 'msub', 'msup', 'msubsup', 'munder', 'mover', 'munderover', 'mmultiscripts', 'msection', 'maction', 'annotation', 'semantics'], ADD_ATTR: ['mathvariant', 'mathcolor', 'mathsize', 'mathbackground', 'display', 'xmlns'] };
                    inner = DOMPurify.sanitize(marked.parse(block.content, { breaks: true, gfm: true }), purifyConfig).replace(/<p>(@@@[A-Z_0-9]+@@@)<\/p>/g, '$1');
                } else {
                    inner = escapeHtml(block.content).replace(/\n/g, '<br>');
                }
                html = `
                    <div class="thought-wrapper ${isExpanded ? 'expanded' : ''}">
                        <div class="thought-header" onclick="window.toggledBlocks['${tKey}'] = this.parentElement.classList.toggle('expanded')">
                            <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
                            <span>Writing Code</span>
                        </div>
                        <div class="thought-content">${inner}</div>
                    </div>
                `;
            } else if (block.type === 'review') {
                id = `@@@REVIEW_${index}@@@`;
                const tKey = 'r_' + index;
                window.toggledBlocks = window.toggledBlocks || {};
                let isExpanded = window.toggledBlocks[tKey] !== undefined ? window.toggledBlocks[tKey] : true;
                let inner = '';
                if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                    const purifyConfig = { ADD_TAGS: ['math', 'mrow', 'mi', 'mo', 'mn', 'ms', 'mspace', 'mtext', 'menclose', 'merror', 'mphantom', 'mpadded', 'mroot', 'mfrac', 'msub', 'msup', 'msubsup', 'munder', 'mover', 'munderover', 'mmultiscripts', 'msection', 'maction', 'annotation', 'semantics'], ADD_ATTR: ['mathvariant', 'mathcolor', 'mathsize', 'mathbackground', 'display', 'xmlns'] };
                    inner = DOMPurify.sanitize(marked.parse(block.content, { breaks: true, gfm: true }), purifyConfig).replace(/<p>(@@@[A-Z_0-9]+@@@)<\/p>/g, '$1');
                } else {
                    inner = escapeHtml(block.content).replace(/\n/g, '<br>');
                }
                html = `
                    <div class="thought-wrapper ${isExpanded ? 'expanded' : ''}">
                        <div class="thought-header" onclick="window.toggledBlocks['${tKey}'] = this.parentElement.classList.toggle('expanded')">
                            <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
                            <span>Code Review</span>
                        </div>
                        <div class="thought-content">${inner}</div>
                    </div>
                `;
            } else if (block.type === 'action') {
                id = `@@@ACTION_${index}@@@`;
                try {
                    const obj = JSON.parse(block.content);
                    if (obj.action === "chat" && obj.response) {
                        html = escapeHtml(obj.response).replace(/\n/g, '<br>');
                    } else {
                        const formattedAction = formatActionNormally(obj);
                        html = `<div class="action-result-stream" style="font-size:12px; color:#a385ff; opacity:0.8;">${escapeHtml(formattedAction)}</div>`;
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
                if (!block.finished && isStreaming) {
                    const animDelay = -(Date.now() % 1000);
                    let inner = escapeHtml(block.content);
                    let streamingStatus = `
                        <div style="display: flex; align-items: center; gap: 8px; color: #a385ff; font-size: 13px;">
                            <div style="width: 14px; height: 14px; border: 2px solid rgba(163, 133, 255, 0.3); border-top-color: #a385ff; border-radius: 50%; animation: spin-loader 1s linear infinite; animation-delay: ${animDelay}ms;"></div>
                            <span>Writing ${escapeHtml(block.lang || 'code')}...</span>
                        </div>
                    `;
                    if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                        const codeMd = "```" + (block.lang || '') + "\n" + block.content + "\n```";
                        const purifyConfig = { ADD_TAGS: ['math', 'mrow', 'mi', 'mo', 'mn', 'ms', 'mspace', 'mtext', 'menclose', 'merror', 'mphantom', 'mpadded', 'mroot', 'mfrac', 'msub', 'msup', 'msubsup', 'munder', 'mover', 'munderover', 'mmultiscripts', 'msection', 'maction', 'annotation', 'semantics'], ADD_ATTR: ['mathvariant', 'mathcolor', 'mathsize', 'mathbackground', 'display', 'xmlns', 'class'] };
                        let mdHtml = DOMPurify.sanitize(marked.parse(codeMd, { breaks: true, gfm: true }), purifyConfig);
                        html = `
                            <div class="code-container">
                                <div class="code-header" style="justify-content: flex-start; padding-top: 12px; padding-bottom: 12px;">
                                    ${streamingStatus}
                                </div>
                                ${mdHtml}
                            </div>
                        `;
                    } else {
                        html = `
                            <div class="code-container">
                                <div class="code-header" style="justify-content: flex-start; padding-top: 12px; padding-bottom: 12px;">
                                    ${streamingStatus}
                                </div>
                                <pre><code class="language-${escapeHtml(block.lang)}">${inner}</code></pre>
                            </div>
                        `;
                    }
                } else if (block.hidden) {
                    // Auto-generate a file card for hidden blocks that weren't claimed by an explicit <file_card> tag
                    if (block.autoCard && block.content && !block.claimed) {
                        const autoLang = block.lang || 'code';
                        const ext      = normaliseExt(autoLang);
                        const autoFilename = window.extractFilenameFromCode ? window.extractFilenameFromCode(block.content, ext) : `snippet.${ext}`;
                        let fcId;
                        if (isStreaming) {
                            fcId = 'fc_stream_' + index;
                        } else {
                            let hash = 0;
                            const c = block.content;
                            for (let i = 0; i < c.length; i++) hash = Math.imul(31, hash) + c.charCodeAt(i) | 0;
                            fcId = 'fc_static_' + hash;
                        }
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
            blockHtmlMap[id] = html;
        });

        let previousWork = '';
        let passCount = 0;
        while (work !== previousWork && passCount < 10) {
            previousWork = work;
            for (const [id, html] of Object.entries(blockHtmlMap)) {
                if (work.includes(id)) {
                    work = work.replace(id, html);
                }
            }
            passCount++;
        }

        return work;
    }
window.extractFilenameFromCode = function(code, ext) {
    if (!code) return 'snippet.' + ext;
    const lines = code.trim().split('\n').slice(0, 10);
    for (const line of lines) {
        const match = line.match(/^\s*(?:#|\/\/|\/\*|<!--)\s*([\w-]+\.\w+)\s*(?:\*\/|-->)?\s*$/i);
        if (match && match[1]) return match[1];
    }
    const classMatch = code.match(/(?:public\s+)?(?:class|struct|interface)\s+([a-zA-Z0-9_]+)/);
    if (classMatch && classMatch[1]) return classMatch[1] + '.' + ext;
    if (code.match(/def\s+main\s*\(/) || code.match(/int\s+main\s*\(/) || code.match(/function\s+main\s*\(/)) return 'main.' + ext;
    const funcMatch = code.match(/(?:def|function|func)\s+([a-zA-Z0-9_]+)\s*\(/);
    if (funcMatch && funcMatch[1]) return funcMatch[1] + '.' + ext;
    return 'snippet.' + ext;
};

window.downloadCode = (btn, ext) => {
    const container   = btn.closest('.code-container');
    const codeElement = container.querySelector('pre code');
    const text        = codeElement.textContent;
    const filename    = window.extractFilenameFromCode(text, normaliseExt(ext));
    triggerDownload(filename, text);
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
        outer.setAttribute("dir", "auto");

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
        const hasFiles = window.selectedFiles.length > 0;
        if (!text && !hasFiles) return;

        if (!currentChatId || !chats.find(c => c.id === currentChatId)) {
            startNewChat();
        }

        const chat = normaliseChat(chats.find(c => c.id === currentChatId));

        // ── Title: regenerate after EVERY exchange based on full conversation ──
        const isFirstMessage = chat.messages.length === 0;
        if (isFirstMessage) {
            chat.title = text ? (text.length > 40 ? text.slice(0, 40) + '…' : text) : (hasFiles ? window.selectedFiles[0].name : "New Conversation");
        }
        if (text) {
            regenerateTitle(chat);
        }

        let displayImageUrl = null;
        let attachmentName = null;
        
        if (hasFiles) {
            const firstFile = window.selectedFiles[0];
            if (firstFile.type.startsWith('image/')) {
                displayImageUrl = URL.createObjectURL(firstFile);
            } else {
                attachmentName = window.selectedFiles.length > 1 ? `${window.selectedFiles.length} files attached` : firstFile.name;
            }
        }

        const messageObj = {
            role: 'user',
            content: text,
            displayText: text || `[Attached: ${attachmentName || 'files'}]`,
            imageUrl: displayImageUrl,
            attachmentName: attachmentName
        };

        chat.messages.push(messageObj);
        savePersist();
        renderChatList();

        enterChatMode();
        appendMessageDOM('user', messageObj.displayText, true, displayImageUrl, attachmentName);

        chatInput.value = '';
        const filesToUpload = [...window.selectedFiles];
        clearFileSelection();
        
        if (typeof handleInputResize === 'function') handleInputResize();

        setGeneratingState(true);
        showTypingIndicator();
        
        window._inThinkingStream = false;

        let fullReply = "";
        let actionResult = "";
        let aiMessageDiv = null;
        let aiContentDiv = null;

        try {
            const formData = new FormData();
            filesToUpload.forEach(f => {
                if (f.type.startsWith('image/')) {
                    formData.append('image', f);
                } else {
                    formData.append('document', f);
                }
            });
            formData.append('message', text);
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
            aiMessageDiv.setAttribute("dir", "auto");
            aiMessageDiv.style.display = "none";
            aiContentDiv = document.createElement("div");
            aiContentDiv.classList.add("message-content");
            aiMessageDiv.appendChild(aiContentDiv);
            chatMessages.appendChild(aiMessageDiv);

            let currentResponseText = "";
            let rawResponseText = "";
            let lastRenderTime = 0;
            let renderTimer = null;
            let firstTokenReceived = false;

            // Throttle accumulated tokens to the DOM to max 15fps
            // This prevents "The Browser Markdown Chokehold" where marked.parse+DOMPurify freezes the main thread
            function scheduleRender() {
                if (renderTimer) return;
                const now = Date.now();
                const delay = Math.max(0, 66 - (now - lastRenderTime)); // ~15 FPS max
                renderTimer = setTimeout(() => {
                    try {
                        if (!firstTokenReceived) {
                            removeTypingIndicator();
                            aiMessageDiv.style.display = "";
                            firstTokenReceived = true;
                        }
                        const isAtBottom = chatMessages.scrollHeight - chatMessages.scrollTop <= chatMessages.clientHeight + 50;
                        aiContentDiv.innerHTML = formatMessage(currentResponseText, true);
                        if (isAtBottom) {
                            chatMessages.scrollTop = chatMessages.scrollHeight;
                        }

                        // Update code viewer if open and streaming
                        if (window.currentCardEl) {
                            const activeFcId = window.currentCardEl.dataset.filecardId;
                            if (activeFcId && activeFcId.startsWith('fc_stream_') && window.fileCardCache && window.fileCardCache[activeFcId]) {
                                const newCode = window.fileCardCache[activeFcId];
                                const cvCode = document.getElementById('cvCode');
                                if (cvCode && cvCode.textContent !== newCode) {
                                    const escaped = newCode.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                                    cvCode.innerHTML = escaped;
                                    const lines = newCode.split('\n');
                                    const gutters = document.getElementById('cvGutters');
                                    if (gutters && gutters.children.length !== lines.length) {
                                        gutters.innerHTML = lines.map((_, i) => `<div class="code-viewer-gutter-line">${i + 1}</div>`).join('');
                                        document.getElementById('cvLineCount').textContent = lines.length;
                                    }
                                    document.getElementById('cvCharCount').textContent = newCode.length.toLocaleString();
                                    
                                    // Auto-scroll the code viewer body if it was at the bottom
                                    const cvBody = document.getElementById('cvBody');
                                    if (cvBody) {
                                        const isCvAtBottom = cvBody.scrollHeight - cvBody.scrollTop <= cvBody.clientHeight + 50;
                                        if (isCvAtBottom) {
                                            cvBody.scrollTop = cvBody.scrollHeight;
                                        }
                                    }
                                }
                            }
                        }
                        lastRenderTime = Date.now();
                    } catch (e) {
                        console.error("Render error:", e);
                    } finally {
                        renderTimer = null;
                    }
                }, delay);
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
                            if (window._inThinkingStream) {
                                currentResponseText += "\n</think>\n";
                                window._inThinkingStream = false;
                            }
                            currentResponseText += event.content;
                            scheduleRender();
                        } else if (event.type === "thinking") {
                            if (!window._inThinkingStream) {
                                currentResponseText += "\n<think>\n";
                                window._inThinkingStream = true;
                            }
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
                            const isInsideThink = currentResponseText.lastIndexOf("<think>") > currentResponseText.lastIndexOf("</think>");
                            if (isInsideThink) {
                                currentResponseText += "\n</think>\n\n<action_result>" + event.content + "</action_result>\n\n<think>\n";
                            } else {
                                currentResponseText += "\n\n<action_result>" + event.content + "</action_result>";
                            }
                            scheduleRender();
                        } else if (event.type === "clear") {
                            if (renderTimer !== null) {
                                clearTimeout(renderTimer);
                                renderTimer = null;
                            }
                            lastRenderTime = 0;
                            currentResponseText = "";
                            rawResponseText = "";
                            firstTokenReceived = false;
                            window._inThinkingStream = false;
                            aiContentDiv.innerHTML = "";
                            aiMessageDiv.style.display = "none";
                            showTypingIndicator();
                        } else if (event.type === "raw_response") {
                            rawResponseText = event.content;
                        } else if (event.type === "text" || event.type === "error") {
                            if (!firstTokenReceived) {
                                firstTokenReceived = true;
                                removeTypingIndicator();
                                aiMessageDiv.style.display = "";
                            }
                            currentResponseText += `\n\n> ⚠️ **${event.type === "error" ? "Error" : "System Notification"}**: ${event.content}\n\n`;
                            scheduleRender();
                        }
                    } catch (e) { console.error("Event parse error", e); }
                }
                
                const isAtBottom = chatMessages.scrollHeight - chatMessages.scrollTop <= chatMessages.clientHeight + 50;
                if (isAtBottom) {
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                }
            }

            setGeneratingState(false);
            if (!firstTokenReceived) {
                removeTypingIndicator();
                if (currentResponseText.trim() !== '') {
                    aiMessageDiv.style.display = "";
                } else {
                    currentResponseText = "> **System Notification**: Server closed connection without sending any response.";
                    aiMessageDiv.style.display = "";
                    aiContentDiv.innerHTML = formatMessage(currentResponseText);
                }
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
            
            // Regenerate title after every complete exchange (debounced 3s)
            regenerateTitle(chat);
            
            // Final render to apply non-streaming fallback logic (like stripping unclosed <think> tags)
            if (aiContentDiv) {
                aiContentDiv.innerHTML = formatMessage(cleanResponse, false);
            }

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

    // ── Dictation Button Logic (Local Whisper Backend) ──
    const dictationBtn = document.getElementById("dictationBtn");
    if (dictationBtn && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        let mediaRecorder = null;
        let audioChunks = [];
        let isRecording = false;
        
        dictationBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            
            if (!isRecording) {
                isRecording = true; // Set instantly to prevent double clicks
                dictationBtn.classList.add('recording-active');
                dictationBtn.style.color = '#ff4d4d';
                chatInput.placeholder = "Listening...";
                
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    
                    let options = { mimeType: 'audio/webm' };
                    if (typeof MediaRecorder.isTypeSupported === 'function' && !MediaRecorder.isTypeSupported('audio/webm')) {
                        options = { mimeType: 'audio/mp4' };
                    }
                    
                    mediaRecorder = new MediaRecorder(stream, options);
                    audioChunks = [];
                    
                    mediaRecorder.ondataavailable = (event) => {
                        if (event.data && event.data.size > 0) {
                            audioChunks.push(event.data);
                        }
                    };
                    
                    mediaRecorder.onstop = async () => {
                        isRecording = false;
                        dictationBtn.classList.remove('recording-active');
                        dictationBtn.style.color = '';
                        chatInput.placeholder = "Transcribing...";
                        
                        if (audioChunks.length === 0) {
                            chatInput.placeholder = "Ask anything";
                            return;
                        }
                        
                        const mimeType = options.mimeType || 'audio/webm';
                        const audioBlob = new Blob(audioChunks, { type: mimeType });
                        const formData = new FormData();
                        // Give it an extension matching the mime type
                        const filename = mimeType.includes('mp4') ? 'dictation.mp4' : 'dictation.webm';
                        formData.append("audio", audioBlob, filename);
                        
                        try {
                            const res = await fetch('/api/transcribe', {
                                method: 'POST',
                                body: formData
                            });
                            const data = await res.json();
                            if (data.text) {
                                chatInput.value += (chatInput.value ? ' ' : '') + data.text.trim();
                                if (typeof handleInputResize === 'function') handleInputResize();
                                
                                // Automatically send the message after dictation
                                if (!isGenerating && chatInput.value.trim() !== '') {
                                    handleSendMessage();
                                    setTimeout(handleInputResize, 10);
                                }
                            } else if (data.error) {
                                console.error("Dictation API error:", data.error);
                            }
                        } catch (err) {
                            console.error("Dictation network error:", err);
                        }
                        
                        chatInput.placeholder = "Ask anything";
                        stream.getTracks().forEach(track => track.stop());
                    };
                    
                    mediaRecorder.start();
                } catch (err) {
                    console.error("Microphone access error:", err);
                    isRecording = false;
                    dictationBtn.classList.remove('recording-active');
                    dictationBtn.style.color = '';
                    chatInput.placeholder = "Ask anything";
                    alert("Please allow microphone permissions to use dictation.");
                }
            } else {
                if (mediaRecorder && mediaRecorder.state !== "inactive") {
                    mediaRecorder.stop();
                } else {
                    // Fallback reset if it gets stuck
                    isRecording = false;
                    dictationBtn.classList.remove('recording-active');
                    dictationBtn.style.color = '';
                    chatInput.placeholder = "Ask anything";
                }
            }
        });
    } else if (dictationBtn) {
        dictationBtn.style.display = 'none';
    }

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

    window.removeSelectedFile = function(index) {
        window.selectedFiles.splice(index, 1);
        renderSelectedFiles();
    };

    function renderSelectedFiles() {
        if (window.selectedFiles.length === 0) {
            imagePreviewContainer.innerHTML = '';
            imagePreviewContainer.classList.remove('visible');
            return;
        }

        let html = '<div style="display: flex; gap: 8px; flex-wrap: wrap;">';
        window.selectedFiles.forEach((file, index) => {
            const isImage = file.type.startsWith('image/');
            if (isImage) {
                const objectUrl = URL.createObjectURL(file);
                html += `
                    <div style="position: relative; display: inline-block;">
                        <img src="${objectUrl}" alt="Preview" style="max-height: 60px; border-radius: 6px; border: 1px solid #33334a;">
                        <button class="remove-image-btn" onclick="window.removeSelectedFile(${index})" title="Remove image">✕</button>
                    </div>
                `;
            } else {
                html += `
                    <div style="position: relative; display: inline-block;">
                        <div class="file-preview-box" style="padding: 6px 10px;">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                <polyline points="14 2 14 8 20 8"></polyline>
                            </svg>
                            <span class="file-preview-name" style="font-size: 11px;">${escapeHtml(file.name)}</span>
                        </div>
                        <button class="remove-image-btn" onclick="window.removeSelectedFile(${index})" title="Remove file" style="top: -6px; right: -6px; width: 16px; height: 16px; font-size: 10px;">✕</button>
                    </div>
                `;
            }
        });
        html += '</div>';
        imagePreviewContainer.innerHTML = html;
        imagePreviewContainer.classList.add('visible');
    }

    function handleFilesSelect(files) {
        if (!files || files.length === 0) return;
        for (let i = 0; i < files.length; i++) {
            window.selectedFiles.push(files[i]);
        }
        renderSelectedFiles();
    }

    imageInput?.addEventListener('change', (e) => {
        handleFilesSelect(e.target.files);
        imageInput.value = ''; // Reset input so the same files can be selected again if removed
    });

    let dragTimeout;
    const dragOverlay = document.getElementById('inputDragOverlay');

    window.addEventListener('dragover', (e) => {
        e.preventDefault();
        
        let hasFiles = false;
        if (e.dataTransfer && e.dataTransfer.types) {
            for (let i = 0; i < e.dataTransfer.types.length; i++) {
                const type = e.dataTransfer.types[i];
                if (type === 'Files' || type === 'application/x-moz-file') {
                    hasFiles = true;
                    break;
                }
            }
        }
        
        if (hasFiles) {
            if (dragOverlay) dragOverlay.classList.add('active');
            clearTimeout(dragTimeout);
            dragTimeout = setTimeout(() => {
                if (dragOverlay) dragOverlay.classList.remove('active');
            }, 150);
        }
    });

    window.addEventListener('drop', (e) => {
        e.preventDefault();
        clearTimeout(dragTimeout);
        if (dragOverlay) dragOverlay.classList.remove('active');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFilesSelect(e.dataTransfer.files);
        }
    });

    function clearFileSelection() {
        window.selectedFiles = [];
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
