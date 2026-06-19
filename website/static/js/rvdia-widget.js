(function() {
    // Prevent double initialization
    if (window.RVDiAWidgetInitialized) return;
    window.RVDiAWidgetInitialized = true;

    // 1. Configuration
    const script = document.currentScript || Array.from(document.querySelectorAll('script')).find(s => s.src.includes('rvdia-widget.js'));
    const lang = (script && script.getAttribute('data-lang')) || 'id';
    const apiBase = (script && script.getAttribute('data-api-url')) || window.location.origin;

    // 2. Local Storage Session & History
    let sessionId = localStorage.getItem('rvdia_widget_session_id');
    if (!sessionId) {
        sessionId = 'rvdia_' + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
        localStorage.setItem('rvdia_widget_session_id', sessionId);
    }

    const historyKey = `rvdia_chat_history_${sessionId}`;
    let chatHistory = [];
    try {
        const stored = localStorage.getItem(historyKey);
        if (stored) {
            chatHistory = JSON.parse(stored);
        }
    } catch (e) {
        console.error("Failed to parse chat history:", e);
    }

    // 3. I18n strings
    const strings = {
        id: {
            title: "RVDiA 🌸",
            status: "Sedang menggambar 🎨🎮",
            greeting: "Halo! Aku RVDiA, digital artist & gamer. Ada yang bisa kubantu hari ini? 🌸✨",
            placeholder: "Ketik pesan...",
            error: "Gagal mengirim pesan. Coba lagi ya! 💫"
        },
        en: {
            title: "RVDiA 🌸",
            status: "Drawing & gaming 🎨🎮",
            greeting: "Hello! I'm RVDiA, a digital artist & gamer. How can I help you today? 🌸✨",
            placeholder: "Type a message...",
            error: "Failed to send message. Please try again! 💫"
        }
    };

    const t = strings[lang] || strings['id'];

    // 4. Inject Styles
    const style = document.createElement('style');
    style.innerHTML = `
        .rvdia-widget-wrapper {
            position: fixed;
            bottom: 30px;
            right: 30px;
            z-index: 999999;
            font-family: 'Outfit', 'Inter', system-ui, -apple-system, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: flex-end;
        }

        /* Launcher Button */
        .rvdia-widget-launcher {
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: rgba(11, 15, 25, 0.85);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border: 2px solid #86273d;
            cursor: pointer;
            box-shadow: 0 8px 32px rgba(134, 39, 61, 0.3), inset 0 0 10px rgba(134, 39, 61, 0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.3s, border-color 0.3s;
            position: relative;
        }

        .rvdia-widget-launcher::before {
            content: '';
            position: absolute;
            top: -4px;
            left: -4px;
            right: -4px;
            bottom: -4px;
            border-radius: 50%;
            border: 2px solid rgba(134, 39, 61, 0.4);
            animation: rvdia-pulse 2s infinite;
            pointer-events: none;
        }

        .rvdia-widget-launcher:hover {
            transform: scale(1.1) rotate(5deg);
            border-color: #ef4444;
            box-shadow: 0 8px 32px rgba(239, 68, 68, 0.5), inset 0 0 10px rgba(239, 68, 68, 0.3);
        }

        .rvdia-widget-launcher:active {
            transform: scale(0.95);
        }

        .rvdia-widget-launcher svg {
            width: 100%;
            height: 100%;
            border-radius: 50%;
        }

        /* Chat Panel */
        .rvdia-widget-panel {
            width: 380px;
            height: 550px;
            max-height: calc(100vh - 120px);
            border-radius: 20px;
            background: rgba(11, 15, 25, 0.82);
            backdrop-filter: blur(25px);
            -webkit-backdrop-filter: blur(25px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5), 0 0 40px rgba(134, 39, 61, 0.15);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            margin-bottom: 20px;
            transform: translateY(20px) scale(0.95);
            opacity: 0;
            pointer-events: none;
            transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.1), opacity 0.3s;
            transform-origin: bottom right;
        }

        .rvdia-widget-panel.active {
            transform: translateY(0) scale(1);
            opacity: 1;
            pointer-events: auto;
        }

        /* Header */
        .rvdia-widget-header {
            padding: 16px 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(255, 255, 255, 0.02);
        }

        .rvdia-widget-header-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .rvdia-widget-header-avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            border: 1.5px solid #86273d;
            overflow: hidden;
        }

        .rvdia-widget-header-avatar svg {
            width: 100%;
            height: 100%;
        }

        .rvdia-widget-header-info {
            display: flex;
            flex-direction: column;
        }

        .rvdia-widget-header-name {
            font-size: 15px;
            font-weight: 800;
            color: #ffffff;
            text-shadow: 0 0 8px rgba(134, 39, 61, 0.5);
            line-height: 1.2;
        }

        .rvdia-widget-header-status {
            font-size: 11px;
            color: #a8a29e;
            display: flex;
            align-items: center;
            gap: 5px;
            margin-top: 2px;
        }

        .rvdia-widget-header-status::before {
            content: '';
            display: inline-block;
            width: 6px;
            height: 6px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 8px #10b981;
        }

        .rvdia-widget-header-close {
            background: transparent;
            border: none;
            color: rgba(255, 255, 255, 0.4);
            cursor: pointer;
            padding: 4px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: color 0.2s, background-color 0.2s;
        }

        .rvdia-widget-header-close:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.05);
        }

        /* Messages Area */
        .rvdia-widget-messages {
            flex-grow: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        /* Scrollbar */
        .rvdia-widget-messages::-webkit-scrollbar {
            width: 5px;
        }
        .rvdia-widget-messages::-webkit-scrollbar-track {
            background: transparent;
        }
        .rvdia-widget-messages::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 99px;
        }
        .rvdia-widget-messages::-webkit-scrollbar-thumb:hover {
            background: rgba(134, 39, 61, 0.5);
        }

        /* Chat Bubbles */
        .rvdia-widget-msg {
            max-width: 80%;
            padding: 12px 16px;
            font-size: 13.5px;
            line-height: 1.5;
            animation: rvdia-slide-in 0.25s cubic-bezier(0.175, 0.885, 0.32, 1) forwards;
            word-wrap: break-word;
            white-space: pre-wrap;
        }

        .rvdia-widget-msg-model {
            align-self: flex-start;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            color: #e2e8f0;
            border-radius: 18px 18px 18px 2px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }

        .rvdia-widget-msg-user {
            align-self: flex-end;
            background: linear-gradient(135deg, #86273d 0%, #a83b53 100%);
            color: #ffffff;
            border-radius: 18px 18px 2px 18px;
            box-shadow: 0 4px 12px rgba(134, 39, 61, 0.2);
        }

        .rvdia-widget-msg-model p {
            margin: 0 0 8px 0;
        }
        .rvdia-widget-msg-model p:last-child {
            margin-bottom: 0;
        }

        .rvdia-widget-msg-image {
            max-width: 100%;
            border-radius: 8px;
            margin-top: 8px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            display: block;
        }

        /* Input Area */
        .rvdia-widget-input-area {
            padding: 16px 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(255, 255, 255, 0.01);
        }

        .rvdia-widget-input {
            flex-grow: 1;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            color: #ffffff;
            padding: 12px 16px;
            font-size: 13.5px;
            outline: none;
            transition: border-color 0.2s, background-color 0.2s;
        }

        .rvdia-widget-input:focus {
            border-color: rgba(134, 39, 61, 0.8);
            background: rgba(255, 255, 255, 0.05);
        }

        .rvdia-widget-input::placeholder {
            color: rgba(255, 255, 255, 0.3);
        }

        .rvdia-widget-send {
            width: 42px;
            height: 42px;
            border-radius: 10px;
            background: linear-gradient(135deg, #86273d 0%, #a83b53 100%);
            border: none;
            color: #ffffff;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.2s, opacity 0.2s;
            box-shadow: 0 4px 12px rgba(134, 39, 61, 0.3);
        }

        .rvdia-widget-send:hover {
            transform: scale(1.05);
            background: linear-gradient(135deg, #a83b53 0%, #c14b66 100%);
        }

        .rvdia-widget-send:active {
            transform: scale(0.95);
        }

        .rvdia-widget-send svg {
            width: 18px;
            height: 18px;
            fill: none;
            stroke: currentColor;
            stroke-width: 2.5;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        /* Typing Bouncing Indicator */
        .rvdia-widget-typing {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 14px 20px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 18px 18px 18px 2px;
            align-self: flex-start;
            animation: rvdia-slide-in 0.2s forwards;
        }

        .rvdia-widget-typing span {
            width: 6px;
            height: 6px;
            background: rgba(255, 255, 255, 0.5);
            border-radius: 50%;
            animation: rvdia-bounce 1.4s infinite ease-in-out both;
        }

        .rvdia-widget-typing span:nth-child(1) { animation-delay: -0.32s; }
        .rvdia-widget-typing span:nth-child(2) { animation-delay: -0.16s; }

        /* Animations */
        @keyframes rvdia-pulse {
            0% { transform: scale(1); opacity: 0.8; }
            50% { transform: scale(1.1); opacity: 0; }
            100% { transform: scale(1); opacity: 0; }
        }

        @keyframes rvdia-bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1.0); }
        }

        @keyframes rvdia-slide-in {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Responsive */
        @media (max-width: 480px) {
            .rvdia-widget-wrapper {
                bottom: 20px;
                right: 20px;
            }
            .rvdia-widget-panel {
                width: calc(100vw - 40px);
                height: 480px;
                bottom: 85px;
                right: 0;
            }
        }
    `;
    document.head.appendChild(style);

    // 5. Shared SVG Avatar Template
    const avatarSVG = `
        <svg viewBox="0 0 100 100">
            <defs>
                <linearGradient id="rvdia-avatar-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#86273d" />
                    <stop offset="100%" stop-color="#ef4444" />
                </linearGradient>
                <linearGradient id="rvdia-hair-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#ec4899" />
                    <stop offset="100%" stop-color="#f43f5e" />
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="48" fill="url(#rvdia-avatar-grad)" stroke="rgba(255,255,255,0.1)" stroke-width="2" />
            <path d="M25,55 C25,30 75,30 75,55 C75,75 25,75 25,55 Z" fill="url(#rvdia-hair-grad)" opacity="0.8" />
            <circle cx="50" cy="52" r="22" fill="#fed7aa" />
            <ellipse cx="42" cy="50" rx="2" ry="3.5" fill="#1e293b" />
            <ellipse cx="58" cy="50" rx="2" ry="3.5" fill="#1e293b" />
            <circle cx="38" cy="55" r="3" fill="#f43f5e" opacity="0.6" />
            <circle cx="62" cy="55" r="3" fill="#f43f5e" opacity="0.6" />
            <path d="M47,56 Q50,59 53,56" stroke="#1e293b" stroke-width="2" fill="none" stroke-linecap="round" />
            <path d="M26,45 C35,28 65,28 74,45 C70,38 60,35 50,37 C40,35 30,38 26,45 Z" fill="url(#rvdia-hair-grad)" />
            <path d="M30,33 L20,18 L32,25 Z" fill="#1e293b" />
            <path d="M70,33 L80,18 L68,25 Z" fill="#1e293b" />
            <path d="M30,33 A25,25 0 0,1 70,33" stroke="#1e293b" stroke-width="6" fill="none" />
            <rect x="23" y="44" width="7" height="15" rx="3.5" fill="#1e293b" />
            <rect x="70" y="44" width="7" height="15" rx="3.5" fill="#1e293b" />
        </svg>
    `;

    // 6. Build DOM Elements
    const wrapper = document.createElement('div');
    wrapper.className = 'rvdia-widget-wrapper';

    wrapper.innerHTML = `
        <div class="rvdia-widget-panel" id="rvdia-widget-panel">
            <div class="rvdia-widget-header">
                <div class="rvdia-widget-header-left">
                    <div class="rvdia-widget-header-avatar">
                        ${avatarSVG}
                    </div>
                    <div class="rvdia-widget-header-info">
                        <div class="rvdia-widget-header-name">${t.title}</div>
                        <div class="rvdia-widget-header-status">${t.status}</div>
                    </div>
                </div>
                <button class="rvdia-widget-header-close" id="rvdia-widget-close" aria-label="Close chat">
                    <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <div class="rvdia-widget-messages" id="rvdia-widget-messages"></div>
            <div class="rvdia-widget-input-area">
                <input type="text" class="rvdia-widget-input" id="rvdia-widget-input" placeholder="${t.placeholder}" maxlength="2000" />
                <button class="rvdia-widget-send" id="rvdia-widget-send" aria-label="Send message">
                    <svg viewBox="0 0 24 24">
                        <line x1="22" y1="2" x2="11" y2="13"></line>
                        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                    </svg>
                </button>
            </div>
        </div>
        <button class="rvdia-widget-launcher" id="rvdia-widget-launcher" aria-label="Open chat">
            ${avatarSVG}
        </button>
    `;

    document.body.appendChild(wrapper);

    // 7. Elements Selection
    const panel = wrapper.querySelector('#rvdia-widget-panel');
    const launcher = wrapper.querySelector('#rvdia-widget-launcher');
    const closeBtn = wrapper.querySelector('#rvdia-widget-close');
    const messagesContainer = wrapper.querySelector('#rvdia-widget-messages');
    const inputField = wrapper.querySelector('#rvdia-widget-input');
    const sendBtn = wrapper.querySelector('#rvdia-widget-send');

    // 8. Load & Render History or Greeting
    function appendMessage(role, text, imageUrl = null) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `rvdia-widget-msg rvdia-widget-msg-${role}`;
        
        let contentHtml = `<div>${escapeHtml(text)}</div>`;
        if (imageUrl) {
            contentHtml += `<img src="${imageUrl}" class="rvdia-widget-msg-image" alt="Embedded Image" />`;
        }
        msgDiv.innerHTML = contentHtml;
        messagesContainer.appendChild(msgDiv);
        scrollToBottom();
    }

    function renderHistory() {
        messagesContainer.innerHTML = '';
        if (chatHistory.length === 0) {
            appendMessage('model', t.greeting);
        } else {
            chatHistory.forEach(msg => {
                appendMessage(msg.role, msg.content, msg.imageUrl);
            });
        }
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function escapeHtml(text) {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // 9. Handle Messages POST
    let isTyping = false;
    let typingIndicator = null;

    function showTyping() {
        if (isTyping) return;
        isTyping = true;
        typingIndicator = document.createElement('div');
        typingIndicator.className = 'rvdia-widget-typing';
        typingIndicator.innerHTML = '<span></span><span></span><span></span>';
        messagesContainer.appendChild(typingIndicator);
        scrollToBottom();
    }

    function hideTyping() {
        if (!isTyping) return;
        isTyping = false;
        if (typingIndicator) {
            typingIndicator.remove();
            typingIndicator = null;
        }
    }

    async function handleSend() {
        const text = inputField.value.trim();
        if (!text || isTyping) return;

        inputField.value = '';
        appendMessage('user', text);
        
        // Save to local history
        chatHistory.push({ role: 'user', content: text });
        localStorage.setItem(historyKey, JSON.stringify(chatHistory));

        showTyping();

        try {
            const response = await fetch(`${apiBase}/api/v1/public/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    message: text,
                    lang: lang
                })
            });

            if (!response.ok) {
                throw new Error("API request failed");
            }

            const data = await response.json();
            hideTyping();

            const reply = data.response;
            const imageUrl = data.image_url;

            appendMessage('model', reply, imageUrl);
            chatHistory.push({ role: 'model', content: reply, imageUrl: imageUrl });
            localStorage.setItem(historyKey, JSON.stringify(chatHistory));

        } catch (err) {
            console.error("Widget chat API error:", err);
            hideTyping();
            appendMessage('model', t.error);
        }
    }

    // 10. Bind Event Listeners
    launcher.addEventListener('click', () => {
        panel.classList.toggle('active');
        if (panel.classList.contains('active')) {
            scrollToBottom();
            inputField.focus();
        }
    });

    closeBtn.addEventListener('click', () => {
        panel.classList.remove('active');
    });

    sendBtn.addEventListener('click', handleSend);
    inputField.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            handleSend();
        }
    });

    // 11. Initial Run
    renderHistory();
})();
