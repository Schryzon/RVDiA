/**
 * RVDiA Dashboard — Client-side logic
 * Fetches profile, inventory, stats from API and renders them.
 * Also handles the web chat widget.
 */

const LANG = window.__RVDIA_LANG__ || "en";

// ── Utilities ───────────────────────────────────────────────

function format_number(n) {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
    if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
    return n.toLocaleString();
}

function format_uptime(seconds) {
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

function animate_counter(el, target, duration = 1200) {
    const start = 0;
    const start_time = performance.now();
    const is_number = typeof target === "number";

    function step(now) {
        const elapsed = now - start_time;
        const progress = Math.min(elapsed / duration, 1);
        // ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);

        if (is_number) {
            el.textContent = format_number(Math.round(target * eased));
        }

        if (progress < 1) requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
}

function escape_html(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}


// ── Profile ─────────────────────────────────────────────────

async function fetch_profile() {
    const container = document.getElementById("profile-content");
    try {
        const resp = await fetch("/api/v1/user/profile");
        const data = await resp.json();

        if (!data.registered) {
            container.innerHTML = `<div class="profile-empty">
                <p>⚔️ ${LANG === "id" ? "Belum punya akun Re:Volution. Gunakan /game register di Discord!" : "No Re:Volution account. Use /game register in Discord!"}</p>
            </div>`;
            return;
        }

        const p = data.profile;
        const hp_pct = Math.round((p.hp / p.max_hp) * 100);
        const exp_pct = Math.round((p.exp / p.next_exp) * 100);

        const hp_color = hp_pct > 60 ? "var(--hp-high)" : hp_pct > 30 ? "var(--hp-mid)" : "var(--hp-low)";

        // premium badge
        if (p.premium_until) {
            const badge = document.getElementById("dash-premium-badge");
            if (badge && new Date(p.premium_until) > new Date()) {
                badge.style.display = "inline-block";
            }
        }

        const guild_html = data.guild
            ? `<div class="profile-guild">🏰 ${escape_html(data.guild.name)}</div>`
            : "";

        container.innerHTML = `
            <div class="profile-header-row">
                <span class="profile-name">${escape_html(p.name)}</span>
                <span class="profile-level">Lv. ${p.level}</span>
            </div>

            ${guild_html}

            <div class="bar-group">
                <div class="bar-label">
                    <span>HP</span>
                    <span>${p.hp} / ${p.max_hp}</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill hp-fill" style="width:${hp_pct}%; background:${hp_color};"></div>
                </div>
            </div>

            <div class="bar-group">
                <div class="bar-label">
                    <span>EXP</span>
                    <span>${p.exp} / ${p.next_exp}</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill exp-fill" style="width:${exp_pct}%;"></div>
                </div>
            </div>

            <div class="profile-stats-grid">
                <div class="profile-stat">
                    <span class="stat-icon">💰</span>
                    <span class="stat-num">${format_number(p.coins)}</span>
                    <span class="stat-name">${LANG === "id" ? "Koin" : "Coins"}</span>
                </div>
                <div class="profile-stat">
                    <span class="stat-icon">✨</span>
                    <span class="stat-num">${format_number(p.karma)}</span>
                    <span class="stat-name">Karma</span>
                </div>
                <div class="profile-stat">
                    <span class="stat-icon">⚔️</span>
                    <span class="stat-num">${p.attack}</span>
                    <span class="stat-name">ATK</span>
                </div>
                <div class="profile-stat">
                    <span class="stat-icon">🛡️</span>
                    <span class="stat-num">${p.defense}</span>
                    <span class="stat-name">DEF</span>
                </div>
                <div class="profile-stat">
                    <span class="stat-icon">💨</span>
                    <span class="stat-num">${p.agility}</span>
                    <span class="stat-name">AGI</span>
                </div>
            </div>
        `;

        // animate bars
        requestAnimationFrame(() => {
            container.querySelectorAll(".progress-fill").forEach(bar => {
                bar.style.transition = "width 1s cubic-bezier(0.22, 1, 0.36, 1)";
            });
        });

    } catch (err) {
        console.error("fetch_profile error:", err);
        container.innerHTML = `<div class="profile-empty"><p>Failed to load profile.</p></div>`;
    }
}


// ── Inventory ───────────────────────────────────────────────

async function fetch_inventory() {
    const container = document.getElementById("inventory-content");
    try {
        const resp = await fetch("/api/v1/user/inventory");
        const data = await resp.json();

        if (!data.registered) {
            container.innerHTML = `<div class="profile-empty"><p>${LANG === "id" ? "Belum terdaftar." : "Not registered."}</p></div>`;
            return;
        }

        const inv = data.inventory;
        const items = inv.items || {};
        const equipped = inv.equipments || [];
        const skills = inv.skills || {};

        const item_keys = Object.keys(items);
        const skill_keys = Object.keys(skills);

        if (item_keys.length === 0 && skill_keys.length === 0) {
            container.innerHTML = `<div class="profile-empty"><p>🎒 ${LANG === "id" ? "Inventori kosong." : "Inventory is empty."}</p></div>`;
            return;
        }

        let html = '<div class="inv-grid">';

        for (const [name, qty] of Object.entries(items)) {
            const is_equipped = equipped.includes(name);
            const cls = is_equipped ? "inv-item equipped" : "inv-item";
            html += `
                <div class="${cls}">
                    <span class="inv-item-name">${escape_html(name)}</span>
                    <span class="inv-item-qty">×${qty}</span>
                    ${is_equipped ? '<span class="inv-equipped-badge">E</span>' : ""}
                </div>
            `;
        }

        for (const [name, info] of Object.entries(skills)) {
            html += `
                <div class="inv-item skill-item">
                    <span class="inv-item-name">🔮 ${escape_html(name)}</span>
                </div>
            `;
        }

        html += "</div>";
        container.innerHTML = html;

    } catch (err) {
        console.error("fetch_inventory error:", err);
        container.innerHTML = `<div class="profile-empty"><p>Failed to load inventory.</p></div>`;
    }
}


// ── Stats ───────────────────────────────────────────────────

async function fetch_stats() {
    try {
        const resp = await fetch("/api/v1/stats");
        const data = await resp.json();

        animate_counter(document.getElementById("stat-servers"), data.servers);
        animate_counter(document.getElementById("stat-users"), data.users);
        animate_counter(document.getElementById("stat-memories"), data.memories);

        const uptime_el = document.getElementById("stat-uptime");
        uptime_el.textContent = format_uptime(data.uptime_seconds);
    } catch (err) {
        console.error("fetch_stats error:", err);
    }
}


// ── Web Chat ────────────────────────────────────────────────

function init_chat() {
    const toggle = document.getElementById("chat-toggle");
    const panel = document.getElementById("chat-panel");
    const close_btn = document.getElementById("chat-close");
    const input = document.getElementById("chat-input");
    const send_btn = document.getElementById("chat-send");
    const messages = document.getElementById("chat-messages");

    let is_open = false;
    let is_sending = false;

    function toggle_chat() {
        is_open = !is_open;
        panel.classList.toggle("open", is_open);
        toggle.classList.toggle("hidden", is_open);
        if (is_open) input.focus();
    }

    toggle.addEventListener("click", toggle_chat);
    close_btn.addEventListener("click", toggle_chat);

    function add_message(text, is_bot = false) {
        const bubble = document.createElement("div");
        bubble.className = is_bot ? "chat-bubble bot-bubble" : "chat-bubble user-bubble";

        const p = document.createElement("p");
        p.textContent = text;
        bubble.appendChild(p);

        messages.appendChild(bubble);
        messages.scrollTop = messages.scrollHeight;

        // animate in
        requestAnimationFrame(() => bubble.classList.add("visible"));

        return bubble;
    }

    function add_typing() {
        const bubble = document.createElement("div");
        bubble.className = "chat-bubble bot-bubble typing-bubble";
        bubble.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
        messages.appendChild(bubble);
        messages.scrollTop = messages.scrollHeight;
        requestAnimationFrame(() => bubble.classList.add("visible"));
        return bubble;
    }

    async function send_message() {
        const text = input.value.trim();
        if (!text || is_sending) return;

        is_sending = true;
        input.value = "";
        send_btn.disabled = true;

        add_message(text, false);
        const typing = add_typing();

        try {
            const resp = await fetch("/api/v1/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, lang: LANG }),
            });
            const data = await resp.json();

            typing.remove();

            if (data.error) {
                add_message(`⚠️ ${data.error}`, true);
            } else {
                add_message(data.response, true);
            }
        } catch (err) {
            typing.remove();
            add_message("⚠️ Connection error.", true);
        }

        is_sending = false;
        send_btn.disabled = false;
        input.focus();
    }

    send_btn.addEventListener("click", send_message);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            send_message();
        }
    });
}


// ── Init ────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    fetch_profile();
    fetch_inventory();
    fetch_stats();
    init_chat();
});
