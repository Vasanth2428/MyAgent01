/**
 * ================================================================
 * RAG CONTROL CONSOLE — HUD Application Logic & Orchestrator
 * ================================================================
 */

const API_BASE = `${window.location.origin}`;

// Secure telemetry cache avoids injecting raw JSON into onclick attributes.
window.telemetryCache = {};

// ---- DOM References ----
const form                  = document.getElementById('comm-form');
const input                 = document.getElementById('comm-input');
const chatWindow            = document.getElementById('chat-window');
const logWindow             = document.getElementById('log-window');
const overflowLogWindow     = document.getElementById('overflow-log-window');
const inspectorWindow       = document.getElementById('inspector-window');
const reconWindow           = document.getElementById('recon-window');
const evictionWindow        = document.getElementById('eviction-window');
const btn                   = document.getElementById('comm-btn');
const stopBtn               = document.getElementById('stop-btn');
const sessionTag            = document.getElementById('session-tag');
const knowledgeCount        = document.getElementById('knowledge-count');
const engineModeSelect      = null;

// Stats Panel
const statQ    = document.getElementById('stat-q');
const statC    = document.getElementById('stat-c');
const statT    = document.getElementById('stat-t');
const statM    = document.getElementById('stat-m');
const statCpu  = document.getElementById('stat-cpu');
const statRam  = document.getElementById('stat-ram');
const statCtx  = document.getElementById('stat-ctx');

// Budget Controls
const contextLimitSlider      = document.getElementById('context-limit-slider');
const contextLimitSliderVal   = document.getElementById('context-limit-slider-val');
const tokenUsedVal            = document.getElementById('token-used-val');
const tokenLimitValReadout    = document.getElementById('token-limit-val-readout');
const tokenProgressFill       = document.getElementById('token-progress-fill');
const tokenPercentageText     = document.getElementById('token-percentage-text');
const overflowAlertBanner     = document.getElementById('overflow-alert-banner');
const overflowIndicatorDot     = document.getElementById('overflow-indicator-dot');
const headerBudgetReadout      = document.getElementById('header-budget-readout');

// Modal Elements
const telemetryModal          = document.getElementById('telemetry-modal');
const telemetryModalBody      = document.getElementById('telemetry-modal-body');

// ---- Session State Variables ----
let sid = localStorage.getItem('station_sid') || 'SID-' + Math.random().toString(36).substr(2, 6).toUpperCase();
localStorage.setItem('station_sid', sid);
sessionTag.textContent = `SID: ${sid}`;

let contextLimit = contextLimitSlider ? parseInt(contextLimitSlider.value) : 4096;
let abortController = null;
let renderFrame = null;
let pendingMarkdownTarget = null;
let pendingMarkdownText = "";

function setSubmitReady() {
    if (!btn || !input) return;
    btn.disabled = AppState.isGenerating || input.value.trim().length === 0;
}

function resizePromptInput() {
    if (!input) return;
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
}

function renderMarkdownSoon(container, text) {
    pendingMarkdownTarget = container;
    pendingMarkdownText = text;
    if (renderFrame) return;

    renderFrame = requestAnimationFrame(() => {
        renderFrame = null;
        if (!pendingMarkdownTarget) return;
        try {
            pendingMarkdownTarget.innerHTML = typeof marked !== 'undefined' ? marked.parse(pendingMarkdownText) : escapeHtml(pendingMarkdownText);
        } catch (e) {
            pendingMarkdownTarget.textContent = pendingMarkdownText;
        }
        applyPostFormatting(pendingMarkdownTarget);
    });
}

// ---- Explicit App State Model ----
const AppState = {
    get sid() { return sid; },
    get contextLimit() { return contextLimit; },
    get isGenerating() { return abortController !== null; },
    get abortController() { return abortController; },
    
    updateContextLimit(val) {
        contextLimit = val;
        if (contextLimitSliderVal) contextLimitSliderVal.textContent = val;
        if (tokenLimitValReadout) tokenLimitValReadout.textContent = val;
        const currentUsed = tokenUsedVal ? (parseInt(tokenUsedVal.textContent) || 0) : 0;
        updateProgressBar(currentUsed, val, currentUsed > val);
    },
    
    setGenerating(generating, controller = null) {
        abortController = controller;
        setSubmitReady();
        if (btn) {
            const label = btn.querySelector('span');
            if (label) label.textContent = generating ? 'RUNNING' : 'ASK';
        }
        if (stopBtn) stopBtn.style.display = generating ? 'inline-block' : 'none';
        addLog(generating ? "System transitioned to state: GENERATING" : "System transitioned to state: IDLE", "STATE");
    }
};

if (input) {
    input.addEventListener('input', () => {
        resizePromptInput();
        setSubmitReady();
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!AppState.isGenerating && input.value.trim()) {
                form.requestSubmit();
            }
        }
    });
}

// ---- Slider & Preset Listeners ----
if (contextLimitSlider) {
    contextLimitSlider.addEventListener('input', (e) => {
        AppState.updateContextLimit(parseInt(e.target.value));
    });
}

// ---- Reset Session Listener ----
const resetSessionBtn = document.getElementById('reset-session-btn');
if (resetSessionBtn) {
    resetSessionBtn.addEventListener('click', () => {
        if (confirm("Reset conversation and start a new session?")) {
            localStorage.removeItem('station_sid');
            sid = 'SID-' + Math.random().toString(36).substr(2, 6).toUpperCase();
            localStorage.setItem('station_sid', sid);
            sessionTag.textContent = `SID: ${sid}`;
            chatWindow.innerHTML = '';
            addLog("Conversation session reset. New session initialized.", "SYSTEM");
            refreshGlobalStats();
        }
    });
}

// ---- Telemetry Inspect Event Delegation ----
if (chatWindow) {
    chatWindow.addEventListener('click', (e) => {
        const btn = e.target.closest('.telemetry-inspect-btn');
        if (btn) {
            const key = btn.dataset.telemetryKey;
            if (key && typeof viewTelemetryDetails === 'function') {
                viewTelemetryDetails(key);
            }
        }
    });
}

// ---- Modal Close Listener ----
const modalCloseBtn = document.querySelector('.modal-close');
if (modalCloseBtn) {
    modalCloseBtn.addEventListener('click', () => {
        if (typeof closeTelemetryModal === 'function') {
            closeTelemetryModal();
        }
    });
}

document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        // Toggle active style
        document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        const val = parseInt(btn.dataset.val);
        contextLimitSlider.value = val;
        AppState.updateContextLimit(val);
        addLog(`Context window boundary adjusted to ${val} tokens via preset.`, 'SYSTEM');
    });
});

// ---- Tab Navigation ----
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const targetTab = btn.dataset.tab;
        
        // Update active tab button
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        // Update active tab panel
        document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
        document.getElementById(`tab-${targetTab}`).classList.add('active');
    });
});

// ---- Evicted Content Renderer ----
function renderEvictedContent(evictedData) {
    const container = document.getElementById('evicted-content-window');
    if (!evictedData || (!evictedData.memory_evicted && !evictedData.documents_evicted)) {
        container.innerHTML = '<div class="evicted-placeholder">No content evicted yet. Overflow events will appear here.</div>';
        return;
    }
    
    let html = '';
    
    // Memory evicted
    if (evictedData.memory_evicted && evictedData.memory_evicted.length > 0) {
        html += '<div class="evicted-section"><div class="evicted-section-title">MEMORY TURNS EVICTED</div>';
        evictedData.memory_evicted.forEach(item => {
            html += `<div class="evicted-item memory-evicted">
                <div class="evicted-header">
                    <span class="evicted-badge memory-badge">${item.role}</span>
                    <span class="evicted-tokens">${item.tokens} TKN</span>
                </div>
                <div class="evicted-text">${escapeHtml(item.text)}</div>
            </div>`;
        });
        html += '</div>';
    }
    
    // Documents evicted
    if (evictedData.documents_evicted && evictedData.documents_evicted.length > 0) {
        html += '<div class="evicted-section"><div class="evicted-section-title">DOCUMENT SEGMENTS EVICTED</div>';
        evictedData.documents_evicted.forEach(item => {
            html += `<div class="evicted-item doc-evicted">
                <div class="evicted-header">
                    <span class="evicted-badge doc-badge">DROPPED</span>
                    <span class="evicted-score">SCORE: ${item.score}</span>
                    <span class="evicted-tokens">${item.tokens} TKN</span>
                </div>
                <div class="evicted-text">${escapeHtml(item.text)}</div>
                <div class="evicted-source">SRC: ${escapeHtml(item.source || 'unknown')}</div>
            </div>`;
        });
        html += '</div>';
    }
    
    container.innerHTML = html;
}

// ---- Progress Bar Sizer ----
function updateProgressBar(used, limit, isBreached) {
    const percent = Math.min(100, Math.round((used / limit) * 100));
    if (tokenProgressFill) {
        tokenProgressFill.style.width = `${percent}%`;
        // Clear status classes
        tokenProgressFill.classList.remove('warn', 'breached');
        if (isBreached) {
            tokenProgressFill.classList.add('breached');
        } else if (percent > 85) {
            tokenProgressFill.classList.add('warn');
        }
    }
    if (tokenPercentageText) {
        tokenPercentageText.textContent = `${percent}% of window occupied`;
    }
    if (headerBudgetReadout) {
        headerBudgetReadout.textContent = `${used} / ${limit}`;
    }
}

// ---- System Log Helpers ----
function addLog(msg, type = 'INFO') {
    const time = new Date().toLocaleTimeString('en-GB', { hour12: false });
    const entry = document.createElement('div');
    entry.className = `log-entry log-type-${type}`;
    const timeSpan = document.createElement('span');
    timeSpan.className = 'log-time';
    timeSpan.textContent = `[${time}]`;
    const typeSpan = document.createElement('span');
    typeSpan.className = 'log-type';
    typeSpan.textContent = type;
    entry.appendChild(timeSpan);
    entry.appendChild(typeSpan);
    entry.appendChild(document.createTextNode(` ${msg}`));
    logWindow.appendChild(entry);
    logWindow.scrollTop = logWindow.scrollHeight;
}

// ---- Code Highlight & Copy-code Formatting ----
function applyPostFormatting(container) {
    if (typeof hljs !== 'undefined') {
        container.querySelectorAll('pre code').forEach((block) => {
            if (!block.classList.contains('hljs')) {
                hljs.highlightElement(block);
            }
        });
    }

    container.querySelectorAll('pre').forEach((preBlock) => {
        if (preBlock.querySelector('.copy-code-btn')) return;

        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'copy-code-btn';
        copyBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:12px;height:12px;vertical-align:middle;color:var(--text-secondary);">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span>Copy</span>
        `;
        
        copyBtn.addEventListener('click', () => {
            const codeBlock = preBlock.querySelector('code');
            const textToCopy = codeBlock ? codeBlock.innerText : preBlock.innerText;
            navigator.clipboard.writeText(textToCopy).then(() => {
                copyBtn.classList.add('copied');
                copyBtn.querySelector('span').textContent = 'Copied!';
                setTimeout(() => {
                    copyBtn.classList.remove('copied');
                    copyBtn.querySelector('span').textContent = 'Copy';
                }, 2000);
            }).catch(err => {
                console.error('Failed to copy text: ', err);
            });
        });
        
        preBlock.appendChild(copyBtn);
    });
}

// ---- Scratchpad Accordion Helpers ----
function initScratchpadAccordion(accordion) {
    const header = accordion.querySelector('.scratchpad-header');
    header.addEventListener('click', () => {
        accordion.classList.toggle('collapsed');
    });
}

function createScratchpadAccordion(container) {
    const accordion = document.createElement('div');
    accordion.className = 'scratchpad-accordion'; // expanded by default when thinking
    accordion.innerHTML = `
        <div class="scratchpad-header">
            <div class="scratchpad-title-group">
                <svg class="scratchpad-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px;vertical-align:middle;color:var(--accent-cyan);">
                    <circle cx="12" cy="12" r="10"></circle>
                    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
                    <line x1="12" y1="17" x2="12.01" y2="17"></line>
                </svg>
                <span>Agent Thinking Process</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span class="scratchpad-status thinking">Thinking</span>
                <svg class="scratchpad-chevron" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:12px;height:12px;vertical-align:middle;color:var(--text-secondary);">
                    <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
            </div>
        </div>
        <div class="scratchpad-content-wrapper">
            <div class="scratchpad-steps"></div>
        </div>
    `;
    
    initScratchpadAccordion(accordion);
    container.appendChild(accordion);
    return accordion;
}

function addScratchpadStep(accordion, stepData) {
    const stepsContainer = accordion.querySelector('.scratchpad-steps');
    if (!stepsContainer) return;
    
    const stepDiv = document.createElement('div');
    const event = stepData.event;
    
    const lifecycleEvents = {
        'planning': { className: 'planning', title: 'Planning' },
        'memory_retrieval': { className: 'memory-retrieval', title: 'Memory Retrieval' },
        'context_assembly': { className: 'context-assembly', title: 'Context Assembly' },
        'document_retrieval': { className: 'document-retrieval', title: 'Document Retrieval' },
        'web_traversal': { className: 'web-traversal', title: 'Web Traversal' },
        'summarization': { className: 'summarization', title: 'Summarization' },
        'inference': { className: 'inference', title: 'Inference' },
        'synthesis': { className: 'synthesis', title: 'Synthesis' }
    };
    
    if (event === 'thought') {
        stepDiv.className = 'scratchpad-step thought';
        stepDiv.innerHTML = `
            <div class="scratchpad-step-title">Thought</div>
            <div class="scratchpad-step-body">${escapeHtml(stepData.text)}</div>
        `;
    } else if (event === 'action') {
        stepDiv.className = 'scratchpad-step action';
        stepDiv.innerHTML = `
            <div class="scratchpad-step-title">Action</div>
            <div class="scratchpad-step-body">Executing tool: <strong>${escapeHtml(stepData.tool)}</strong> with input: <code>${escapeHtml(stepData.input)}</code></div>
        `;
    } else if (event === 'observation') {
        stepDiv.className = 'scratchpad-step observation';
        stepDiv.innerHTML = `
            <div class="scratchpad-step-title">Observation</div>
            <div class="scratchpad-step-body">${escapeHtml(stepData.output)}</div>
        `;
    } else if (lifecycleEvents[event]) {
        const info = lifecycleEvents[event];
        stepDiv.className = `scratchpad-step ${info.className}`;
        stepDiv.innerHTML = `
            <div class="scratchpad-step-title">${info.title}</div>
            <div class="scratchpad-step-body">${escapeHtml(stepData.text)}</div>
        `;
    } else {
        stepDiv.className = 'scratchpad-step';
        stepDiv.innerHTML = `
            <div class="scratchpad-step-title">${escapeHtml(event)}</div>
            <div class="scratchpad-step-body">${escapeHtml(stepData.text || '')}</div>
        `;
    }
    
    stepsContainer.appendChild(stepDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

// ---- Traversal Panel Render Helper ----
function addTraversalStep(step) {
    const traversalWindow = document.getElementById('traversal-window');
    if (!traversalWindow) return;
    
    const emptyDiv = traversalWindow.querySelector('.readout-empty');
    if (emptyDiv) {
        traversalWindow.innerHTML = '';
    }
    
    const item = document.createElement('div');
    if (step.type === 'search') {
        item.className = 'traversal-item type-search';
        const results = step.results || [];
        item.innerHTML = `
            <div class="traversal-header">
                <span class="traversal-badge badge-search">Search</span>
                <span>DuckDuckGo</span>
            </div>
            <div class="traversal-title">Query: "${escapeHtml(step.query)}"</div>
            <div class="traversal-details">Found ${results.length} results</div>
            <ul class="traversal-results-list">
                ${results.map(r => `
                    <li class="traversal-result-li">
                        <a class="traversal-link" href="${escapeHtml(r.url)}" target="_blank" rel="noopener noreferrer">
                            ${escapeHtml(r.title)}
                        </a>
                    </li>
                `).join('')}
            </ul>
        `;
    } else if (step.type === 'fetch' && step.status !== 'error') {
        item.className = 'traversal-item type-fetch';
        item.innerHTML = `
            <div class="traversal-header">
                <span class="traversal-badge badge-fetch">Fetch</span>
                <span>Page Fetch</span>
            </div>
            <div class="traversal-title">${escapeHtml(step.title || 'Page Content')}</div>
            <a class="traversal-link" href="${escapeHtml(step.url)}" target="_blank" rel="noopener noreferrer">
                ${escapeHtml(step.url)}
            </a>
            <div class="traversal-details">Status: Success | Size: ${step.length || 0} chars</div>
        `;
    } else if (step.type === 'fetch' || step.status === 'error') {
        item.className = 'traversal-item type-error';
        item.innerHTML = `
            <div class="traversal-header">
                <span class="traversal-badge badge-error">Error</span>
                <span>Fetch Failed</span>
            </div>
            <a class="traversal-link" href="${escapeHtml(step.url)}" target="_blank" rel="noopener noreferrer">
                ${escapeHtml(step.url)}
            </a>
            <div class="traversal-details" style="color: var(--accent-red);">${escapeHtml(step.error || 'Failed to retrieve page content')}</div>
        `;
    }
    
    traversalWindow.appendChild(item);
    traversalWindow.scrollTop = traversalWindow.scrollHeight;
    
    const activeRightBtn = document.querySelector('.tab-btn-right.active');
    if (!activeRightBtn || activeRightBtn.dataset.tabRight !== 'traversal') {
        const badge = document.getElementById('badge-traversal');
        if (badge) badge.classList.add('pulse');
    }
}

// ---- Reusable Sidebar Telemetry Synchronizer ----
function populateSidebarFromTelemetry(telemetryData) {
    if (!telemetryData) return;
    
    const query = telemetryData.query || '';
    const rawPrompt = telemetryData.raw_prompt || '';
    
    const overflow = telemetryData.overflow_telemetry || {
        overflow_occurred: telemetryData.overflow_occurred,
        limit: telemetryData.limit,
        initial_tokens: telemetryData.initial_tokens,
        final_tokens: telemetryData.final_tokens,
        steps: telemetryData.steps
    };
    
    const budget = telemetryData.budget_tracking || {};
    const traversalPath = telemetryData.traversal_path || [];
    const retrievedContext = telemetryData.retrieved_context || telemetryData.retrieved_contexts || [];
    const evictionLog = telemetryData.eviction_log || [];
    
    const limit = overflow.limit || contextLimit;
    const finalUsed = overflow.final_tokens || (budget.memory_tokens_used + (budget.document_tokens_used || 0) + 100);
    if (tokenUsedVal) tokenUsedVal.textContent = finalUsed;
    updateProgressBar(finalUsed, limit, finalUsed > limit);
    
    const reconWindow = document.getElementById('recon-window');
    if (reconWindow) {
        reconWindow.innerHTML = '';
        if (retrievedContext && retrievedContext.length > 0) {
            retrievedContext.forEach(hit => {
                const item = document.createElement('div');
                item.className = 'readout-item';
                item.innerHTML = `
                    ${escapeHtml(hit.text.substring(0, 180))}...
                    <div class="readout-meta">
                        <span>SCORE: ${hit.score !== undefined && hit.score !== null ? hit.score.toFixed(4) : 'N/A'}</span>
                        <span>SRC: ${escapeHtml(hit.source)}</span>
                    </div>
                `;
                reconWindow.appendChild(item);
            });
        } else {
            reconWindow.innerHTML = '<div class="readout-empty">No active retrieval context.</div>';
        }
    }
    
    const evictionWindow = document.getElementById('eviction-window');
    if (evictionWindow) {
        evictionWindow.innerHTML = '';
        if (evictionLog && evictionLog.length > 0) {
            const kept = evictionLog.filter(e => e.status === 'KEPT');
            const dropped = evictionLog.filter(e => e.status === 'DROPPED');
            const summary = document.createElement('div');
            summary.className = 'eviction-summary';
            summary.innerHTML = `<span class="eviction-kept-count">${kept.length} KEPT</span> <span class="eviction-dropped-count">${dropped.length} DROPPED</span>`;
            evictionWindow.appendChild(summary);

            evictionLog.forEach(entry => {
                const item = document.createElement('div');
                const isDropped = entry.status === 'DROPPED';
                item.className = `eviction-item ${isDropped ? 'eviction-dropped' : 'eviction-kept'}`;
                item.innerHTML = `
                    <div class="eviction-header">
                        <span class="eviction-badge ${isDropped ? 'badge-dropped' : 'badge-kept'}">${entry.status}</span>
                        <span class="eviction-score">${entry.score !== undefined && entry.score !== null ? 'SCORE: ' + entry.score : ''}</span>
                        <span class="eviction-tokens">${entry.tokens} TKN</span>
                    </div>
                    <div class="eviction-text">${escapeHtml(entry.text)}</div>
                    ${isDropped ? `<div class="eviction-reason">REASON: ${escapeHtml(entry.reason)}</div>` : ''}
                `;
                evictionWindow.appendChild(item);
            });
        } else {
            evictionWindow.innerHTML = '<div class="readout-empty">No segments evicted (content fit within budget).</div>';
        }
    }
    
    const traversalWindow = document.getElementById('traversal-window');
    if (traversalWindow) {
        traversalWindow.innerHTML = '';
        if (traversalPath && traversalPath.length > 0) {
            traversalPath.forEach(step => {
                const item = document.createElement('div');
                if (step.type === 'search') {
                    item.className = 'traversal-item type-search';
                    const results = step.results || [];
                    item.innerHTML = `
                        <div class="traversal-header">
                            <span class="traversal-badge badge-search">Search</span>
                            <span>DuckDuckGo</span>
                        </div>
                        <div class="traversal-title">Query: "${escapeHtml(step.query)}"</div>
                        <div class="traversal-details">Found ${results.length} results</div>
                        <ul class="traversal-results-list">
                            ${results.map(r => `
                                <li class="traversal-result-li">
                                    <a class="traversal-link" href="${escapeHtml(r.url)}" target="_blank" rel="noopener noreferrer">
                                        ${escapeHtml(r.title)}
                                    </a>
                                </li>
                            `).join('')}
                        </ul>
                    `;
                } else if (step.type === 'fetch' && step.status !== 'error') {
                    item.className = 'traversal-item type-fetch';
                    item.innerHTML = `
                        <div class="traversal-header">
                            <span class="traversal-badge badge-fetch">Fetch</span>
                            <span>Page Fetch</span>
                        </div>
                        <div class="traversal-title">${escapeHtml(step.title || 'Page Content')}</div>
                        <a class="traversal-link" href="${escapeHtml(step.url)}" target="_blank" rel="noopener noreferrer">
                            ${escapeHtml(step.url)}
                        </a>
                        <div class="traversal-details">Status: Success | Size: ${step.length || 0} chars</div>
                    `;
                } else if (step.type === 'fetch' || step.status === 'error') {
                    item.className = 'traversal-item type-error';
                    item.innerHTML = `
                        <div class="traversal-header">
                            <span class="traversal-badge badge-error">Error</span>
                            <span>Fetch Failed</span>
                        </div>
                        <a class="traversal-link" href="${escapeHtml(step.url)}" target="_blank" rel="noopener noreferrer">
                            ${escapeHtml(step.url)}
                        </a>
                        <div class="traversal-details" style="color: var(--accent-red);">${escapeHtml(step.error || 'Failed to retrieve page content')}</div>
                    `;
                }
                traversalWindow.appendChild(item);
            });
        } else {
            traversalWindow.innerHTML = '<div class="readout-empty">No web traversal data. Submit a query requiring web search/fetch.</div>';
        }
    }
    
    if (telemetryData.queries_handled !== undefined) {
        statQ.textContent = telemetryData.queries_handled;
    } else if (telemetryData.stats && telemetryData.stats.queries_handled !== undefined) {
        statQ.textContent = telemetryData.stats.queries_handled;
    }
    
    if (telemetryData.compression_ratio !== undefined) {
        statC.textContent = Math.round((1 - telemetryData.compression_ratio) * 100) + '%';
    } else if (telemetryData.stats && telemetryData.stats.compression_ratio !== undefined) {
        statC.textContent = Math.round((1 - telemetryData.stats.compression_ratio) * 100) + '%';
    }
    
    if (telemetryData.active_memories !== undefined) {
        statM.textContent = telemetryData.active_memories;
    } else if (telemetryData.stats && telemetryData.stats.active_memories !== undefined) {
        statM.textContent = telemetryData.stats.active_memories;
    }
    
    if (telemetryData.latency !== undefined) {
        statT.textContent = telemetryData.latency + 'ms';
    } else if (telemetryData.stats && telemetryData.stats.latency !== undefined) {
        statT.textContent = telemetryData.stats.latency + 'ms';
    }
    
    if (telemetryData.cpu_usage_percent !== undefined) {
        statCpu.textContent = Math.round(telemetryData.cpu_usage_percent) + '%';
    } else if (telemetryData.stats && telemetryData.stats.cpu_usage_percent !== undefined) {
        statCpu.textContent = Math.round(telemetryData.stats.cpu_usage_percent) + '%';
    }
    
    if (telemetryData.memory_usage_percent !== undefined) {
        statRam.textContent = Math.round(telemetryData.memory_usage_percent) + '%';
    } else if (telemetryData.stats && telemetryData.stats.memory_usage_percent !== undefined) {
        statRam.textContent = Math.round(telemetryData.stats.memory_usage_percent) + '%';
    }
    
    if (telemetryData.context_used_percent !== undefined) {
        statCtx.textContent = Math.round(telemetryData.context_used_percent) + '%';
    } else if (telemetryData.stats && telemetryData.stats.context_used_percent !== undefined) {
        statCtx.textContent = Math.round(telemetryData.stats.context_used_percent) + '%';
    }
    
    const finalData = {
        query: query,
        search_queries: (telemetryData.instantaneous_latency_ms ? telemetryData.instantaneous_latency_ms.search_queries : null) || 
                       (telemetryData.stats && telemetryData.stats.instantaneous_latency_ms ? telemetryData.stats.instantaneous_latency_ms.search_queries : null) || 
                       [query],
        hyde_doc: telemetryData.hyde_doc || (telemetryData.stats ? telemetryData.stats.hyde_doc : "N/A") || "N/A",
        raw_prompt: rawPrompt || "N/A",
        stats: telemetryData.stats || telemetryData
    };
    renderInspector(finalData);
}

// ---- Chat Bubble Renderer ----
function addMsg(text, type = 'ai', telemetryData = null) {
    const msg = document.createElement('div');
    msg.className = `message msg-${type}`;
    
    let formattedText = text;
    if (type === 'ai') {
        try { 
            formattedText = typeof marked !== 'undefined' ? marked.parse(text) : text; 
        } catch (e) { 
            formattedText = text; 
        }
    }
    
    // Create header
    const headerDiv = document.createElement('div');
    headerDiv.className = 'msg-header';
    headerDiv.textContent = type === 'user' ? 'USER_INPUT' : 'SYSTEM_OUTPUT';
    msg.appendChild(headerDiv);
    
    // Render scratchpad if AI turn and has agent_steps
    let parsedTelemetry = null;
    if (type === 'ai' && telemetryData) {
        parsedTelemetry = typeof telemetryData === 'string' ? JSON.parse(telemetryData) : telemetryData;
    }
    
    let agentSteps = null;
    if (parsedTelemetry) {
        if (parsedTelemetry.agent_steps) {
            agentSteps = parsedTelemetry.agent_steps;
        } else if (parsedTelemetry.telemetry && parsedTelemetry.telemetry.agent_steps) {
            agentSteps = parsedTelemetry.telemetry.agent_steps;
        }
    }
    
    if (type === 'ai' && agentSteps && agentSteps.length > 0) {
        const scratchpadContainer = document.createElement('div');
        scratchpadContainer.className = 'scratchpad-container';
        msg.appendChild(scratchpadContainer);
        
        const accordion = createScratchpadAccordion(scratchpadContainer);
        accordion.classList.add('collapsed'); // collapsed for history turns
        
        const statusSpan = accordion.querySelector('.scratchpad-status');
        if (statusSpan) {
            statusSpan.className = 'scratchpad-status completed';
            statusSpan.textContent = 'Completed';
        }
        
        agentSteps.forEach(step => {
            addScratchpadStep(accordion, step);
        });
    }
    
    // Create body
    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'msg-body';
    bodyDiv.innerHTML = formattedText;
    msg.appendChild(bodyDiv);
    
    // Post process formatting (highlighting/copy buttons)
    if (type === 'ai') {
        applyPostFormatting(bodyDiv);
    }
    
    // If AI Turn has telemetry, append footnote badge
    if (type === 'ai' && parsedTelemetry) {
        const telemetryObj = parsedTelemetry.telemetry || parsedTelemetry;
        const hasOverflow = telemetryObj.overflow_occurred === true;
        const finalTkn = telemetryObj.final_tokens || 'N/A';
        const limitVal = telemetryObj.limit || 'N/A';
        
        if (hasOverflow) {
            msg.classList.add('msg-overflow-recovered');
        }
        
        const cacheKey = 'tel_' + Math.random().toString(36).substr(2, 8);
        window.telemetryCache[cacheKey] = parsedTelemetry;
        
        const telemetryFooter = document.createElement('div');
        telemetryFooter.className = 'msg-telemetry';
        telemetryFooter.innerHTML = `
            <div class="telemetry-badges">
                <span class="badge-item ${hasOverflow ? 'recovered' : 'nominal'}">
                    ${hasOverflow ? 'RECOVERED' : 'NOMINAL'}
                </span>
                <span class="badge-item">LIMIT: ${limitVal} TKN</span>
                <span class="badge-item">FOOTPRINT: ${finalTkn} TKN</span>
            </div>
            <button class="telemetry-inspect-btn" data-telemetry-key="${cacheKey}">
                INSPECT
            </button>
        `;
        msg.appendChild(telemetryFooter);
    }
    
    chatWindow.appendChild(msg);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return msg;
}

// HTML Escaping Helper for Telemetry JSON Inject
function escapeHtml(str) {
    if (str === null || str === undefined) {
        return "";
    }
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// ---- Inspector Panels Renderer ----
function renderInspector(data) {
    const budget  = data.stats?.budget_tracking || {};
    const latency = data.stats?.instantaneous_latency_ms || {};

    inspectorWindow.innerHTML = `
        <div class="inspector-section">
            <div class="inspector-section-hdr">BUDGET ALLOCATION</div>
            <div class="inspector-section-body">
MEMORY OCCUPIED: ${budget.memory_tokens_used || 0} / ${budget.memory_tokens_limit || 0} TKN
KNOWLEDGE COMPRESSED: ${budget.document_tokens_used || 0} / ${budget.document_tokens_limit || 0} TKN
            </div>
        </div>
        <div class="inspector-section">
            <div class="inspector-section-hdr">PIPELINE TELEMETRY</div>
            <div class="inspector-section-body">
MODE: ${(data.stats?.mode || 'N/A').toUpperCase()}
HYBRID ALPHA: ${data.stats?.alpha || 0.5}
PEAK RE-RANK SCORE: ${data.stats?.reranker_peak_score || 0}
COMPRESSION RATIO: ${((data.stats?.compression_ratio || 0) * 100).toFixed(1)}%
EMBED GENERATION: ${latency.phase_2_embed_generation_ms || 0} ms
WEAVIATE SEARCH: ${latency.phase_2_weaviate_search_ms || 0} ms
HYDE GENERATION: ${latency.phase_1_5_hyde_ms || 0} ms
            </div>
        </div>
        <div class="inspector-section">
            <div class="inspector-section-hdr">LLM QUERY EXPANSIONS</div>
            <div class="inspector-section-body">${data.search_queries ? data.search_queries.map(q => `> ${q}`).join('\n') : 'N/A'}</div>
        </div>
        <div class="inspector-section">
            <div class="inspector-section-hdr">HYPOTHETICAL DOCUMENT (HyDE)</div>
            <div class="inspector-section-body">${data.hyde_doc || 'N/A'}</div>
        </div>
        <div class="inspector-section">
            <div class="inspector-section-hdr">RAW PROMPT INSPECTION</div>
            <div class="inspector-section-body" style="font-family: var(--font-mono); font-size: 0.65rem; max-height: 160px; overflow-y: auto; background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.03); white-space: pre-wrap; word-break: break-all;">${escapeHtml(data.raw_prompt || 'N/A')}</div>
        </div>
    `;
}

// ---- SSE Streaming Controller ----
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = input.value.trim();
    if (!query) return;

    input.value = '';
    resizePromptInput();
    setSubmitReady();
    addMsg(query, 'user');
    
    addLog(`Initiating streaming request (Mode: agentic | Limit: ${contextLimit} TKN)`, 'REQUEST');

    // Reset/Clear UI state for query run
    reconWindow.innerHTML = '';
    inspectorWindow.innerHTML = '<div class="inspector-placeholder">Awaiting telemetry stream...</div>';
    
    // Auto-select KNOWLEDGE tab on query submit
    document.querySelectorAll('.tab-btn-right').forEach(b => b.classList.remove('active'));
    const knowledgeTabBtn = document.querySelector('[data-tab-right="knowledge"]');
    if (knowledgeTabBtn) {
        knowledgeTabBtn.classList.add('active');
    }
    document.querySelectorAll('.tab-panel-right').forEach(panel => panel.classList.remove('active'));
    const knowledgeTabPanel = document.getElementById('tab-right-knowledge');
    if (knowledgeTabPanel) {
        knowledgeTabPanel.classList.add('active');
    }
    
    // Clear notification badges
    const badgeK = document.getElementById('badge-knowledge');
    const badgeE = document.getElementById('badge-evictions');
    if (badgeK) badgeK.classList.remove('pulse');
    if (badgeE) badgeE.classList.remove('pulse');

    // Clear and reset context overflow debugger
    if (overflowLogWindow) overflowLogWindow.innerHTML = '';
    if (overflowIndicatorDot) overflowIndicatorDot.className = 'indicator-dot nominal';
    if (overflowAlertBanner) {
        overflowAlertBanner.className = 'overflow-banner alert-nominal';
        overflowAlertBanner.textContent = 'SYSTEM RUNNING IN NOMINAL STATE';
    }

    const controller = new AbortController();
    AppState.setGenerating(true, controller);
    const startTime = Date.now();

    // Create placeholder AI message bubble
    const aiBubble = document.createElement('div');
    aiBubble.className = 'message msg-ai';
    aiBubble.innerHTML = `
        <div class="msg-header">SYSTEM_OUTPUT</div>
        <div class="scratchpad-container"></div>
        <div class="msg-body typing-cursor"></div>
    `;
    chatWindow.appendChild(aiBubble);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    
    const scratchpadContainer = aiBubble.querySelector('.scratchpad-container');
    const bodyContainer = aiBubble.querySelector('.msg-body');
    let accordion = null;
    let currentAgentSteps = [];
    let accumulatedText = "";

    try {
        const response = await fetch(`${API_BASE}/query_stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                question: query, 
                session_id: AppState.sid, 
                mode: "agentic",
                context_limit: AppState.contextLimit
            }),
            signal: AppState.abortController.signal
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Server Error");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop(); // Hold remaining partial line

            for (const line of lines) {
                const cleanLine = line.trim();
                if (!cleanLine.startsWith("data:")) continue;

                const jsonStr = cleanLine.substring(5).trim();
                if (!jsonStr) continue;

                let data;
                try {
                    data = JSON.parse(jsonStr);
                } catch (parseErr) {
                    console.error("SSE parse error", jsonStr, parseErr);
                    continue;
                }

                const isScratchpadEvent = ["thought", "action", "observation", "planning", "memory_retrieval", "context_assembly", "document_retrieval", "web_traversal", "summarization", "inference", "synthesis"].includes(data.event);
                if (isScratchpadEvent) {
                    if (!accordion) {
                        accordion = createScratchpadAccordion(scratchpadContainer);
                    }
                    addScratchpadStep(accordion, data);
                    currentAgentSteps.push(data);
                    
                    if (data.event === "thought") {
                        addLog(data.text, "THOUGHT");
                    } else if (data.event === "action") {
                        addLog(`Executing tool: ${data.tool}[${data.input}]`, "ACTION");
                    } else if (data.event === "observation") {
                        const outputText = data.output || data.text || "";
                        addLog(`Received tool observation (${outputText.length} chars)`, "OBSERVATION");
                    } else {
                        addLog(data.text || `Phase transition: ${data.event}`, data.event.toUpperCase());
                    }
                } else if (data.event === "web_traversal_step") {
                    addTraversalStep(data);
                }
                else if (data.event === "overflow_detected") {
                    // Trigger visual warning alerts
                    if (overflowIndicatorDot) overflowIndicatorDot.className = 'indicator-dot breached';
                    if (overflowAlertBanner) {
                        overflowAlertBanner.className = 'overflow-banner alert-breached';
                        overflowAlertBanner.innerHTML = `🚨 OVERFLOW DETECTED: Prompt (${data.initial} TKN) exceeds limit (${data.limit} TKN)`;
                    }
                    
                    if (tokenUsedVal) tokenUsedVal.textContent = data.initial;
                    updateProgressBar(data.initial, data.limit, true);
                    
                    addLog(`Context overflow detected! Size: ${data.initial} TKN. Limit: ${data.limit} TKN. Running recovery...`, "WARNING");
                }
                else if (data.event === "overflow_step") {
                    // Stream lines to overflow debugger terminal shell
                    const stepDiv = document.createElement('div');
                    stepDiv.className = 'overflow-step-line';
                    stepDiv.textContent = data.text;
                    
                    // Style lines based on contents
                    if (data.text) {
                        if (data.text.includes("🚨")) {
                            stepDiv.className += ' step-alarm';
                        } else if (data.text.includes("Phase 1")) {
                            stepDiv.className += ' step-phase1';
                        } else if (data.text.includes("Phase 2")) {
                            stepDiv.className += ' step-phase2';
                        } else if (data.text.includes("Phase 3")) {
                            stepDiv.className += ' step-phase3';
                        } else if (data.text.includes("✅")) {
                            stepDiv.className += ' step-success';
                        }
                    }
                    
                    if (overflowLogWindow) {
                        overflowLogWindow.appendChild(stepDiv);
                        overflowLogWindow.scrollTop = overflowLogWindow.scrollHeight;
                    }
                }
                else if (data.event === "answer_chunk") {
                    // Auto-collapse accordion when the final answer starts streaming
                    if (accordion && !accordion.classList.contains('collapsed')) {
                        accordion.classList.add('collapsed');
                        const statusSpan = accordion.querySelector('.scratchpad-status');
                        if (statusSpan) {
                            statusSpan.className = 'scratchpad-status completed';
                            statusSpan.textContent = 'Completed';
                        }
                    }
                    
                    accumulatedText += data.text;
                    renderMarkdownSoon(bodyContainer, accumulatedText);
                    chatWindow.scrollTop = chatWindow.scrollHeight;
                }
                else if (data.event === "error") {
                    throw new Error(data.message);
                }
                else if (data.event === "done") {
                    const latency = Date.now() - startTime;
                    addLog(`Processing complete: ${latency}ms`, 'SUCCESS');
                    bodyContainer.classList.remove('typing-cursor');
                    
                    // Final apply post formatting
                    if (renderFrame) {
                        cancelAnimationFrame(renderFrame);
                        renderFrame = null;
                    }
                    try {
                        bodyContainer.innerHTML = typeof marked !== 'undefined' ? marked.parse(accumulatedText) : escapeHtml(accumulatedText);
                    } catch (e) {
                        bodyContainer.textContent = accumulatedText;
                    }
                    applyPostFormatting(bodyContainer);

                    // Ensure accordion status is marked completed
                    if (accordion) {
                        accordion.classList.add('collapsed');
                        const statusSpan = accordion.querySelector('.scratchpad-status');
                        if (statusSpan) {
                            statusSpan.className = 'scratchpad-status completed';
                            statusSpan.textContent = 'Completed';
                        }
                    }

                    const stats = data.stats || {};
                    stats.query = query;
                    stats.latency = latency;

                    // Sync budget progress bar to final compiled values
                    const telemetry = stats.overflow_telemetry || {};
                    const budget = stats.budget_tracking || {};

                    // Add telemetry elements to the current chat bubble
                    if (telemetry && telemetry.limit) {
                        const hasOverflow = telemetry.overflow_occurred === true;
                        if (hasOverflow) {
                            aiBubble.classList.add('msg-overflow-recovered');
                        }
                        
                        const cacheKey = 'tel_' + Math.random().toString(36).substr(2, 8);
                        window.telemetryCache[cacheKey] = { 
                            telemetry: {
                                ...telemetry,
                                agent_steps: currentAgentSteps,
                                raw_prompt: stats.raw_prompt,
                                traversal_path: stats.traversal_path || [],
                                retrieved_context: stats.retrieved_context || [],
                                eviction_log: stats.eviction_log || []
                            }, 
                            budget, 
                            query 
                        };

                        const footerDiv = document.createElement('div');
                        footerDiv.className = 'msg-telemetry';
                        footerDiv.innerHTML = `
                            <div class="telemetry-badges">
                                <span class="badge-item ${hasOverflow ? 'recovered' : 'nominal'}">
                                    ${hasOverflow ? 'RECOVERED' : 'NOMINAL'}
                                </span>
                                <span class="badge-item">LIMIT: ${telemetry.limit} TKN</span>
                                <span class="badge-item">FOOTPRINT: ${telemetry.final_tokens} TKN</span>
                            </div>
                            <button class="telemetry-inspect-btn" data-telemetry-key="${cacheKey}">
                                INSPECT
                            </button>
                        `;
                        aiBubble.appendChild(footerDiv);
                    }

                    populateSidebarFromTelemetry(stats);
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            addLog(`Pipeline generation failure: ${err.message}`, "ERROR");
            bodyContainer.innerHTML = `<span style="color: var(--accent-red); font-weight: bold;">CRITICAL ERROR:</span> ${escapeHtml(err.message)}`;
            bodyContainer.classList.remove('typing-cursor');
        }
    } finally {
        AppState.setGenerating(false);
    }
});

// ---- Stop Request Button ----
if (stopBtn) {
    stopBtn.addEventListener('click', () => {
        if (AppState.abortController) {
            AppState.abortController.abort();
            addLog("Orchestration pipeline execution stopped by client request.", "WARNING");
            
            const cursorBubble = document.querySelector('.typing-cursor');
            if (cursorBubble) {
                cursorBubble.classList.remove('typing-cursor');
                cursorBubble.innerHTML += "<br><span style='color: var(--accent-amber); font-size: 0.75rem; font-weight: bold;'>[PIPELINE ABORTED]</span>";
            }
            AppState.setGenerating(false);
        }
    });
}

// ---- Telemetry Inspection Modal Logic ----
window.viewTelemetryDetails = function(keyOrTelemetry, budget, query) {
    // Support both cache-key lookups and direct object calls
    let telemetry = keyOrTelemetry;
    let cachedObj = null;
    if (typeof keyOrTelemetry === 'string' && window.telemetryCache[keyOrTelemetry]) {
        cachedObj = window.telemetryCache[keyOrTelemetry];
        telemetry = cachedObj.telemetry || cachedObj;
        budget = cachedObj.budget || budget;
        query = cachedObj.query || query;
    }
    if (!telemetry) return;
    
    // Fallback bounds
    budget = budget || telemetry.budget_tracking || {};
    query = query || telemetry.query || "User Query";
    
    // Sync the dashboards to this inspected turn's data
    populateSidebarFromTelemetry(cachedObj ? cachedObj.telemetry : telemetry);
    
    let stepsHtml = '';
    if (telemetry.steps && telemetry.steps.length > 0) {
        stepsHtml = `
            <div style="margin-top: 15px;">
                <h4 style="margin-bottom: 8px; color: var(--accent-amber);">STEP-BY-STEP RECOVERY LOGS</h4>
                <div class="modal-step-list">
                    ${telemetry.steps.map(step => `<div class="modal-step-item">${escapeHtml(step)}</div>`).join('')}
                </div>
            </div>
        `;
    } else {
        stepsHtml = `
            <div style="margin-top: 15px; color: var(--text-muted); font-style: italic; text-align: center;">
                No context overflow triggered for this turn. Context window remained safe.
            </div>
        `;
    }

    let promptHtml = '';
    if (telemetry.raw_prompt) {
        promptHtml = `
            <div style="margin-top: 15px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 10px;">
                <h4 style="margin-bottom: 8px; color: var(--accent-cyan); font-family: var(--font-brand);">COMPILED LLM PROMPT FOOTPRINT</h4>
                <div style="font-family: var(--font-mono); font-size: 0.65rem; max-height: 180px; overflow-y: auto; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.03); padding: 8px; white-space: pre-wrap; word-break: break-all; color: var(--text-secondary); border-radius: var(--radius-sm);">
                    ${escapeHtml(telemetry.raw_prompt)}
                </div>
            </div>
        `;
    }

    telemetryModalBody.innerHTML = `
        <div style="margin-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 8px;">
            <span style="color: var(--text-muted); font-size: 0.65rem; text-transform: uppercase;">QUERY TEXT:</span>
            <div style="font-weight: 500; color: #fff; margin-top: 2px;">"${escapeHtml(query)}"</div>
        </div>
        
        <table class="modal-meta-table">
            <tr>
                <td>OVERFLOW STATE</td>
                <td style="color: ${telemetry.overflow_occurred ? 'var(--accent-amber)' : 'var(--accent-green)'}">
                    ${telemetry.overflow_occurred ? 'RECOVERED (BREACH RESOLVED)' : 'NOMINAL (NO BREACH)'}
                </td>
            </tr>
            <tr>
                <td>EFFECTIVE LIMIT</td>
                <td>${telemetry.limit} TKN</td>
            </tr>
            <tr>
                <td>INITIAL FOOTPRINT</td>
                <td>${telemetry.initial_tokens} TKN</td>
            </tr>
            <tr>
                <td>SAFE COMPILED SIZE</td>
                <td style="color: var(--accent-cyan)">${telemetry.final_tokens} TKN</td>
            </tr>
            <tr>
                <td>CONVERSATION MEMORY</td>
                <td>${budget.memory_tokens_used || 0} TKN</td>
            </tr>
            <tr>
                <td>COMPRESSED DOCUMENTS</td>
                <td>${budget.document_tokens_used || 0} TKN</td>
            </tr>
        </table>
        
        ${stepsHtml}
        ${promptHtml}
    `;
    
    telemetryModal.classList.add('open');
};

window.closeTelemetryModal = function() {
    telemetryModal.classList.remove('open');
};

// Close modal on click outside content card
telemetryModal.addEventListener('click', (e) => {
    if (e.target === telemetryModal) {
        closeTelemetryModal();
    }
});

// ---- File Upload API ----
const uploadTriggerBtn = document.getElementById('upload-trigger-btn');
if (uploadTriggerBtn) {
    uploadTriggerBtn.addEventListener('click', () => document.getElementById('file-in').click());
}
document.getElementById('file-in').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    const feedback = document.getElementById('up-msg');
    feedback.style.display = 'block';
    feedback.textContent = `Uploading: ${file.name}...`;
    addLog(`Initiating file injection: ${file.name}`, 'UPLOAD');
    
    const fd = new FormData();
    fd.append('file', file);
    
    try {
        const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: fd });
        if (res.ok) { 
            const data = await res.json();
            feedback.textContent = `Indexed successfully!`;
            addLog(`Injection completed: ${data.message}`, "SUCCESS"); 
            refreshGlobalStats(); 
        } else {
            const err = await res.json();
            feedback.textContent = `Upload failed.`;
            addLog(`Injection failed: ${err.detail || 'HTTP Error'}`, "ERROR");
        }
    } catch (e) { 
        feedback.textContent = `Communication error.`;
        addLog(`Injection communication error: ${e.message}`, "ERROR"); 
    }
    
    setTimeout(() => { feedback.style.display = 'none'; }, 4000);
});

// ---- Right Sidebar Tab Navigation ----
document.querySelectorAll('.tab-btn-right').forEach(btn => {
    btn.addEventListener('click', () => {
        const targetTab = btn.dataset.tabRight;
        
        // Update active tab button
        document.querySelectorAll('.tab-btn-right').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        // Update active tab panel
        document.querySelectorAll('.tab-panel-right').forEach(panel => panel.classList.remove('active'));
        const panel = document.getElementById(`tab-right-${targetTab}`);
        if (panel) panel.classList.add('active');
        
        // Clear badge dot on click
        const badge = document.getElementById(`badge-${targetTab}`);
        if (badge) badge.classList.remove('pulse');
    });
});

// ---- Budget Dropdown Logic ----
const budgetDropdownContainer = document.querySelector('.budget-dropdown-container');
const budgetDropdownTrigger = document.getElementById('budget-dropdown-trigger');
const budgetDropdownMenu = document.getElementById('budget-dropdown-menu');

if (budgetDropdownTrigger && budgetDropdownMenu) {
    budgetDropdownTrigger.addEventListener('click', (e) => {
        e.stopPropagation();
        budgetDropdownContainer.classList.toggle('open');
        budgetDropdownMenu.classList.toggle('open');
    });
    
    document.addEventListener('click', (e) => {
        if (budgetDropdownContainer && budgetDropdownContainer.classList.contains('open') && !budgetDropdownContainer.contains(e.target)) {
            budgetDropdownContainer.classList.remove('open');
            budgetDropdownMenu.classList.remove('open');
        }
    });
}

// ---- Background Polling ----
async function refreshGlobalStats() {
    try {
        const res = await fetch(`${API_BASE}/stats`);
        const data = await res.json();
        statQ.textContent = data.queries_handled || 0;
        statC.textContent = Math.round((1 - data.avg_compression) * 100) + '%';
        if (data.document_count !== undefined) {
            knowledgeCount.textContent = data.document_count;
        }
        if (data.cpu_usage_percent !== undefined)      statCpu.textContent = Math.round(data.cpu_usage_percent) + '%';
        if (data.memory_usage_percent !== undefined)   statRam.textContent = Math.round(data.memory_usage_percent) + '%';
    } catch (e) {}
}

// ---- Thread Restoration (Database history load) ----
async function loadHistory() {
    try {
        addLog("Restoring session conversation thread...", "SYSTEM");
        const res = await fetch(`${API_BASE}/history/${sid}`);
        if (!res.ok) {
            // Session may be corrupted — clear it and generate a fresh SID
            addLog(`Session rejected by server (HTTP ${res.status}). Resetting session.`, "WARNING");
            localStorage.removeItem('station_sid');
            sid = 'SID-' + Math.random().toString(36).substr(2, 6).toUpperCase();
            localStorage.setItem('station_sid', sid);
            sessionTag.textContent = `SID: ${sid}`;
            return;
        }
        
        const history = await res.json();
        chatWindow.innerHTML = '';
        
        if (history && history.length > 0) {
            let turnsRestored = 0;
            let lastAssistantTelemetry = null;
            // Loop in pairs or reconstruct footer if assistant has telemetry
            for (let i = 0; i < history.length; i++) {
                const item = history[i];
                const uiRole = item.role === 'assistant' ? 'ai' : 'user';
                
                // If it is user, just render normally
                if (uiRole === 'user') {
                    addMsg(item.text, 'user');
                } else {
                    // It is assistant, pass along database saved telemetry
                    addMsg(item.text, 'ai', item.telemetry);
                    turnsRestored++;
                    
                    if (item.telemetry) {
                        try {
                            lastAssistantTelemetry = typeof item.telemetry === 'string' ? JSON.parse(item.telemetry) : item.telemetry;
                        } catch (e) {
                            console.error("Failed to parse telemetry for item", e);
                        }
                    }
                }
            }
            
            if (lastAssistantTelemetry) {
                populateSidebarFromTelemetry(lastAssistantTelemetry);
            }
            
            addLog(`Restored ${history.length} turns (${turnsRestored} stats-footer records).`, "SUCCESS");
        }
    } catch (e) {
        console.error(e);
        addLog("Failed to restore session history. Resetting session.", "WARNING");
        // Self-heal: clear corrupt session and regenerate
        localStorage.removeItem('station_sid');
        sid = 'SID-' + Math.random().toString(36).substr(2, 6).toUpperCase();
        localStorage.setItem('station_sid', sid);
        sessionTag.textContent = `SID: ${sid}`;
    }
}

// ---- Sidebar Toggles ----
const toggleLeftBtn = document.getElementById('toggle-left-sidebar');
const toggleRightBtn = document.getElementById('toggle-right-sidebar');
const mainGrid = document.querySelector('.main-grid');

if (mainGrid) {
    if (localStorage.getItem('rag_left_collapsed') === 'true') {
        mainGrid.classList.add('left-collapsed');
    }
    if (localStorage.getItem('rag_right_collapsed') === 'true') {
        mainGrid.classList.add('right-collapsed');
    }
}

if (toggleLeftBtn && mainGrid) {
    toggleLeftBtn.addEventListener('click', () => {
        mainGrid.classList.toggle('left-collapsed');
        localStorage.setItem('rag_left_collapsed', mainGrid.classList.contains('left-collapsed'));
        const icon = mainGrid.classList.contains('left-collapsed') ? 
            '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="3" x2="9" y2="21"></line><polyline points="13 8 17 12 13 16"></polyline></svg>' : 
            '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="3" x2="9" y2="21"></line></svg>';
        toggleLeftBtn.innerHTML = icon;
    });
}

if (toggleRightBtn && mainGrid) {
    toggleRightBtn.addEventListener('click', () => {
        mainGrid.classList.toggle('right-collapsed');
        localStorage.setItem('rag_right_collapsed', mainGrid.classList.contains('right-collapsed'));
        const icon = mainGrid.classList.contains('right-collapsed') ? 
            '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="15" y1="3" x2="15" y2="21"></line><polyline points="11 8 7 12 11 16"></polyline></svg>' : 
            '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="15" y1="3" x2="15" y2="21"></line></svg>';
        toggleRightBtn.innerHTML = icon;
    });
}

// Initializers
setInterval(refreshGlobalStats, 15000);
refreshGlobalStats();
loadHistory();
if (contextLimitSlider) AppState.updateContextLimit(parseInt(contextLimitSlider.value));
resizePromptInput();
setSubmitReady();
