/**
 * settings.js — Settings panel: Chat settings + Training panel
 * Works in the new Iris AI design language.
 */

(function () {
    // ── DOM refs ──────────────────────────────────────────────────────────
    const settingsBtn        = document.getElementById('settingsBtn');
    const settingsPanel      = document.getElementById('settingsPanel');
    const settingsOverlay    = document.getElementById('settingsOverlay');
    const closeSettingsBtn   = document.getElementById('closeSettingsBtn');

    // Main tabs
    const stabBtns           = document.querySelectorAll('.stab-btn');
    const tabContents        = document.querySelectorAll('.settings-tab-content');

    // Training sub-tabs
    const trainingSubtabs    = document.querySelectorAll('.training-subtab');
    const tsubContents       = document.querySelectorAll('.tsub-content');

    // Chat settings fields
    const csFields = {
        max_new_tokens    : document.getElementById('cs_max_new_tokens'),
        temperature       : document.getElementById('cs_temperature'),
        top_p             : document.getElementById('cs_top_p'),
        top_k             : document.getElementById('cs_top_k'),
        repetition_penalty: document.getElementById('cs_repetition_penalty'),
    };

    const saveChatSettingsBtn = document.getElementById('saveChatSettingsBtn');

    // Training fields
    const trFields = {
        modelNameInput          : document.getElementById('modelNameInput'),
        checkpointInput         : document.getElementById('checkpointInput'),
        epochsInput             : document.getElementById('epochsInput'),
        lrInput                 : document.getElementById('lrInput'),
        bstSizeInput            : document.getElementById('bstSizeInput'),
        ddSizeInput             : document.getElementById('ddSizeInput'),
        mdDirInput              : document.getElementById('mdDirInput'),
        maxLengthInput          : document.getElementById('maxLengthInput'),
        batchSizeInput          : document.getElementById('batchSizeInput'),
        accumInput              : document.getElementById('accumInput'),
        weightDecayInput        : document.getElementById('weightDecayInput'),
        warmupRatioInput        : document.getElementById('warmupRatioInput'),
        sampleMaxNewTokensInput : document.getElementById('sampleMaxNewTokensInput'),
        deviceInput             : document.getElementById('deviceInput'),
        resumeInput             : document.getElementById('resumeInput'),
        keepBestOnlyInput       : document.getElementById('keepBestOnlyInput'),
        noBstInput              : document.getElementById('noBstInput'),
        noDdInput               : document.getElementById('noDdInput'),
        noMdInput               : document.getElementById('noMdInput'),
    };

    const startTrainingBtn = document.getElementById('startTrainingBtn');
    const stopTrainingBtn  = document.getElementById('stopTrainingBtn');
    const trainLogs        = document.getElementById('trainLogs');

    let logInterval = null;

    // ── Panel open / close ────────────────────────────────────────────────
    function openSettings() {
        // Populate chat settings from memory
        const s = window.getChatSettings ? window.getChatSettings() : {};
        if (csFields.max_new_tokens)     csFields.max_new_tokens.value     = s.max_new_tokens     ?? 200;
        if (csFields.temperature)        csFields.temperature.value        = s.temperature        ?? 0.6;
        if (csFields.top_p)              csFields.top_p.value              = s.top_p              ?? 0.9;
        if (csFields.top_k)              csFields.top_k.value              = s.top_k              ?? 40;
        if (csFields.repetition_penalty) csFields.repetition_penalty.value = s.repetition_penalty ?? 1.3;

        settingsPanel.classList.add('open');
        settingsOverlay.classList.add('visible');

        // Check training status when opening
        refreshTrainingStatus();
    }

    function closeSettings() {
        settingsPanel.classList.remove('open');
        settingsOverlay.classList.remove('visible');
        if (logInterval) {
            clearInterval(logInterval);
            logInterval = null;
        }
    }

    settingsBtn?.addEventListener('click', openSettings);
    closeSettingsBtn?.addEventListener('click', closeSettings);
    settingsOverlay?.addEventListener('click', closeSettings);

    // ── Main tab switching ────────────────────────────────────────────────
    stabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            stabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(`stab-content-${tab}`)?.classList.add('active');

            // When switching to training, refresh status and logs
            if (tab === 'training') {
                refreshTrainingStatus();
                fetchLogs();
            }
        });
    });

    // ── Training sub-tab switching ─────────────────────────────────────────
    trainingSubtabs.forEach(btn => {
        btn.addEventListener('click', () => {
            const tsub = btn.dataset.tsub;
            trainingSubtabs.forEach(b => b.classList.remove('active'));
            tsubContents.forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(`tsub-content-${tsub}`)?.classList.add('active');

            if (tsub === 'logs') fetchLogs();
        });
    });

    // ── Chat settings save ─────────────────────────────────────────────────
    saveChatSettingsBtn?.addEventListener('click', () => {
        const newSettings = {
            max_new_tokens    : parseInt(csFields.max_new_tokens?.value)     || 200,
            temperature       : parseFloat(csFields.temperature?.value)      || 0.6,
            top_p             : parseFloat(csFields.top_p?.value)            || 0.9,
            top_k             : parseInt(csFields.top_k?.value)              || 40,
            repetition_penalty: parseFloat(csFields.repetition_penalty?.value) || 1.3,
        };
        if (window.setChatSettings) window.setChatSettings(newSettings);
        localStorage.setItem('iris_chat_settings', JSON.stringify(newSettings));
        showToast('Chat settings saved');
    });

    // ── Training start/stop ────────────────────────────────────────────────
    startTrainingBtn?.addEventListener('click', startTraining);
    stopTrainingBtn?.addEventListener('click', stopTraining);

    async function startTraining() {
        const params = {
            model_name             : trFields.modelNameInput?.value          ?? 'microsoft/DialoGPT-medium',
            checkpoint             : trFields.checkpointInput?.value         ?? 'checkpoints/iris_ai_2b.pt',
            epochs                 : trFields.epochsInput?.value             ?? 5,
            lr                     : trFields.lrInput?.value                 ?? '3e-5',
            bst_size               : trFields.bstSizeInput?.value            ?? 10000,
            dd_size                : trFields.ddSizeInput?.value             ?? 30000,
            md_dir                 : trFields.mdDirInput?.value              ?? 'training',
            max_length             : trFields.maxLengthInput?.value          ?? 128,
            batch_size             : trFields.batchSizeInput?.value          ?? 4,
            accum                  : trFields.accumInput?.value              ?? 4,
            weight_decay           : trFields.weightDecayInput?.value        ?? 0.01,
            warmup_ratio           : trFields.warmupRatioInput?.value        ?? 0.05,
            sample_max_new_tokens  : trFields.sampleMaxNewTokensInput?.value ?? 50,
            device                 : trFields.deviceInput?.value             ?? 'auto',
            resume                 : trFields.resumeInput?.checked           ?? false,
            keep_best_only         : trFields.keepBestOnlyInput?.checked     ?? true,
            no_bst                 : trFields.noBstInput?.checked            ?? false,
            no_dd                  : trFields.noDdInput?.checked             ?? false,
            no_md                  : trFields.noMdInput?.checked             ?? false,
            chat_after_train       : false,
        };

        if (trainLogs) trainLogs.textContent = 'Starting training…\n';
        setTrainingRunning(true);

        // Switch to logs tab automatically
        switchToLogsTab();

        try {
            const res  = await fetch('/train', {
                method : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body   : JSON.stringify(params),
            });
            const data = await res.json();

            if (data.status === 'already_running' && trainLogs) {
                trainLogs.textContent = 'Training already running. Reconnecting to live logs…\n';
            }

            if (logInterval) clearInterval(logInterval);
            logInterval = setInterval(fetchLogs, 2000);
            await fetchLogs();
            await refreshTrainingStatus();
        } catch (e) {
            if (trainLogs) trainLogs.textContent += '\n[ERROR] Could not start training.\n';
            setTrainingRunning(false);
        }
    }

    async function stopTraining() {
        try {
            const res  = await fetch('/stop_train', { method: 'POST' });
            const data = await res.json();
            if (trainLogs) {
                trainLogs.textContent += data.status === 'stopped'
                    ? '\n[INFO] Training stopped by user.\n'
                    : '\n[INFO] No active training process.\n';
                trainLogs.scrollTop = trainLogs.scrollHeight;
            }
            if (logInterval) { clearInterval(logInterval); logInterval = null; }
            setTrainingRunning(false);
        } catch (e) {
            if (trainLogs) {
                trainLogs.textContent += '\n[ERROR] Failed to stop training.\n';
                trainLogs.scrollTop = trainLogs.scrollHeight;
            }
        }
    }

    async function fetchLogs() {
        try {
            const res  = await fetch('/train_logs');
            const data = await res.json();
            if (trainLogs && typeof data.logs === 'string' && data.logs !== trainLogs.textContent) {
                trainLogs.textContent = data.logs;
                trainLogs.scrollTop   = trainLogs.scrollHeight;
            }
        } catch (_) {}
    }

    async function refreshTrainingStatus() {
        try {
            const res  = await fetch('/train_status');
            const data = await res.json();
            if (data.running) {
                setTrainingRunning(true);
                if (!logInterval) logInterval = setInterval(fetchLogs, 2000);
            } else {
                setTrainingRunning(false);
                if (logInterval) { clearInterval(logInterval); logInterval = null; }
            }
        } catch (_) {}
    }

    function setTrainingRunning(running) {
        if (startTrainingBtn) startTrainingBtn.disabled = running;
        if (stopTrainingBtn)  stopTrainingBtn.disabled  = !running;
    }

    function switchToLogsTab() {
        trainingSubtabs.forEach(b => b.classList.remove('active'));
        tsubContents.forEach(c => c.classList.remove('active'));
        document.getElementById('tsub-logs')?.classList.add('active');
        document.getElementById('tsub-content-logs')?.classList.add('active');
    }

    // ── Toast notification ────────────────────────────────────────────────
    function showToast(message) {
        // Remove any existing toast
        const existing = document.getElementById('saveToast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.id = 'saveToast';
        toast.className = 'save-toast';
        toast.innerHTML = `<span class="save-toast-dot"></span>${message}`;
        document.body.appendChild(toast);

        // Trigger animation
        requestAnimationFrame(() => {
            requestAnimationFrame(() => toast.classList.add('visible'));
        });

        setTimeout(() => {
            toast.classList.remove('visible');
            setTimeout(() => toast.remove(), 300);
        }, 2200);
    }
})();
