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

        const raw_items = Array.isArray(items) ? items : Object.entries(items).map(([name, qty]) => ({ name, owned: qty, _id: name }));
        const raw_equipped = Array.isArray(equipped) ? equipped.map(x => typeof x === 'object' ? x._id : x) : [];
        const raw_skills = Array.isArray(skills) ? skills : Object.entries(skills).map(([name, info]) => ({ name }));

        if (raw_items.length === 0 && raw_skills.length === 0) {
            container.innerHTML = `<div class="profile-empty"><p>🎒 ${LANG === "id" ? "Inventori kosong." : "Inventory is empty."}</p></div>`;
            return;
        }

        let html = '<div class="inv-grid">';

        for (const item of raw_items) {
            const item_id = item._id || item.name;
            const is_equipped = raw_equipped.includes(item_id);
            const is_equippable = item_id.startsWith("1-");
            
            const cls = is_equipped ? "inv-item equipped cursor-pointer" : is_equippable ? "inv-item cursor-pointer hover:border-accent/40" : "inv-item";
            const qty = item.owned || item.qty || 1;
            const display_name = item.name;

            html += `
                <div class="${cls}" data-item-id="${escape_html(item_id)}" data-equippable="${is_equippable}">
                    <span class="inv-item-name">${escape_html(display_name)}</span>
                    <span class="inv-item-qty">×${qty}</span>
                    ${is_equipped ? '<span class="inv-equipped-badge">E</span>' : ""}
                </div>
            `;
        }

        for (const skill of raw_skills) {
            const skill_name = skill.name;
            html += `
                <div class="inv-item skill-item">
                    <span class="inv-item-name">🔮 ${escape_html(skill_name)}</span>
                </div>
            `;
        }

        html += "</div>";
        container.innerHTML = html;

        // Add click event listeners to equippable items
        container.querySelectorAll(".inv-item[data-equippable='true']").forEach(el => {
            el.addEventListener("click", async () => {
                const itemId = el.getAttribute("data-item-id");
                await equip_item(itemId);
            });
        });

    } catch (err) {
        console.error("fetch_inventory error:", err);
        container.innerHTML = `<div class="profile-empty"><p>Failed to load inventory.</p></div>`;
    }
}


// ── RPG Actions ──────────────────────────────────────────────

async function equip_item(itemId) {
    const status_el = document.getElementById("action-status-msg");
    if (!status_el) return;
    status_el.textContent = LANG === "id" ? "Memproses perlengkapan..." : "Processing equipment...";
    status_el.style.color = "#94a3b8";

    try {
        const resp = await fetch("/api/v1/user/equip", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ item_id: itemId })
        });
        const data = await resp.json();

        if (data.error) {
            status_el.textContent = `❌ ${data.error}`;
            status_el.style.color = "#ef4444";
        } else {
            const action_msg = data.action === "equip" 
                ? (LANG === "id" ? `Berhasil memasang ${data.item_name}!` : `Successfully equipped ${data.item_name}!`)
                : (LANG === "id" ? `Berhasil melepas ${data.item_name}!` : `Successfully unequipped ${data.item_name}!`);
            status_el.textContent = `✅ ${action_msg}`;
            status_el.style.color = "#10b981";

            await fetch_profile();
            await fetch_inventory();
        }
    } catch (err) {
        status_el.textContent = "❌ Connection error.";
        status_el.style.color = "#ef4444";
    }

    setTimeout(() => {
        if (status_el.textContent.includes("✅") || status_el.textContent.includes("❌")) {
            status_el.textContent = "";
        }
    }, 4000);
}

async function claim_daily() {
    const btn = document.getElementById("daily-btn");
    const status_el = document.getElementById("action-status-msg");
    if (!btn || !status_el) return;

    btn.disabled = true;
    status_el.textContent = LANG === "id" ? "Mengklaim hadiah harian..." : "Claiming daily reward...";
    status_el.style.color = "#94a3b8";

    try {
        const resp = await fetch("/api/v1/user/daily", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await resp.json();

        if (data.error) {
            status_el.textContent = `❌ ${data.error}`;
            status_el.style.color = "#ef4444";
        } else if (data.on_cooldown) {
            const next_claim = new Date(data.next_claim_timestamp * 1000).toLocaleTimeString();
            status_el.textContent = LANG === "id" 
                ? `⏳ Sudah diklaim! Bisa klaim lagi pada pukul ${next_claim}`
                : `⏳ Already claimed! Claim again at ${next_claim}`;
            status_el.style.color = "#f59e0b";
        } else {
            const r = data.rewards;
            status_el.textContent = LANG === "id"
                ? `🎁 Berhasil! Mendapatkan +${r.coins} Koin, +${r.karma} Karma, dan +${r.exp} EXP!`
                : `🎁 Success! Received +${r.coins} Coins, +${r.karma} Karma, and +${r.exp} EXP!`;
            status_el.style.color = "#10b981";

            if (data.leveled_up) {
                setTimeout(() => {
                    status_el.textContent = LANG === "id" ? "🔰 LEVEL UP! Selamat!" : "🔰 LEVEL UP! Congratulations!";
                    status_el.style.color = "#a855f7";
                }, 3000);
            }

            await fetch_profile();
        }
    } catch (err) {
        status_el.textContent = "❌ Connection error.";
        status_el.style.color = "#ef4444";
    }

    btn.disabled = false;
    setTimeout(() => {
        if (status_el.textContent.includes("🎁") || status_el.textContent.includes("⏳") || status_el.textContent.includes("❌")) {
            status_el.textContent = "";
        }
    }, 6000);
}

async function go_adventure() {
    const btn = document.getElementById("adventure-btn");
    const status_el = document.getElementById("action-status-msg");
    if (!btn || !status_el) return;

    btn.disabled = true;
    status_el.textContent = LANG === "id" ? "Menjelajahi dunia mimpi..." : "Exploring the dream world...";
    status_el.style.color = "#94a3b8";

    try {
        const resp = await fetch("/api/v1/user/adventure", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await resp.json();

        if (data.error) {
            status_el.textContent = `❌ ${data.error}`;
            status_el.style.color = "#ef4444";
        } else {
            const r = data.rewards;
            status_el.textContent = LANG === "id"
                ? `🧭 Petualangan berhasil! Mendapatkan +${r.coins} Koin dan +${r.exp} EXP!`
                : `🧭 Adventure success! Received +${r.coins} Coins and +${r.exp} EXP!`;
            status_el.style.color = "#10b981";

            await fetch_profile();
        }
    } catch (err) {
        status_el.textContent = "❌ Connection error.";
        status_el.style.color = "#ef4444";
    }

    btn.disabled = false;
    setTimeout(() => {
        if (status_el.textContent.includes("🧭") || status_el.textContent.includes("❌")) {
            status_el.textContent = "";
        }
    }, 5000);
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

// ── Shop ────────────────────────────────────────────────────

let shop_items_data = [];
let active_shop_filter = "all";

async function fetch_shop_items() {
    const container = document.getElementById("shop-items-container");
    if (!container) return;

    try {
        const resp = await fetch(`/api/v1/shop?lang=${LANG}`);
        const data = await resp.json();

        if (data.error) {
            container.innerHTML = `<div class="profile-empty"><p>❌ ${data.error}</p></div>`;
            return;
        }

        shop_items_data = data.items || [];
        render_shop_items();
    } catch (err) {
        console.error("fetch_shop_items error:", err);
        container.innerHTML = `<div class="profile-empty"><p>Failed to load shop items.</p></div>`;
    }
}

function render_shop_items() {
    const container = document.getElementById("shop-items-container");
    if (!container) return;

    const filtered = shop_items_data.filter(item => {
        if (active_shop_filter === "all") return true;
        return item.type === active_shop_filter;
    });

    if (filtered.length === 0) {
        container.innerHTML = `<div class="profile-empty"><p>${LANG === "id" ? "Tidak ada item dalam kategori ini." : "No items in this category."}</p></div>`;
        return;
    }

    const t = window.__RVDIA_I18N__ || {
        buy: "Buy",
        cost: "Cost",
        owned: "Owned",
        already_owned: "Already owned",
        type_consumable: "Consumable",
        type_equipment: "Equipment",
        type_skill: "Skill",
        koin: "Koin"
    };

    let html = `<div class="shop-grid w-full">`;

    for (const item of filtered) {
        const is_unstackable = item.type === "Skill" || item.type === "Equipment";
        const has_owned = is_unstackable && item.owned >= 1;
        
        let currency_label = item.paywith === "Koin" ? t.koin : "Karma";
        let type_label = t.type_consumable;
        if (item.type === "Equipment") type_label = t.type_equipment;
        else if (item.type === "Skill") type_label = t.type_skill;

        const is_karma = item.paywith !== "Koin";
        const theme_glow = is_karma 
            ? "hover:border-indigo-500/50 hover:shadow-[0_0_15px_rgba(99,102,241,0.15)]" 
            : "hover:border-accent/50 hover:shadow-[0_0_15px_rgba(255,200,0,0.15)]";

        html += `
            <div class="shop-item-card ${theme_glow}" id="shop-item-${item._id}">
                <div>
                    <span class="shop-item-type">${escape_html(type_label)}</span>
                    <h4 class="shop-item-name">${escape_html(item.name)}</h4>
                    <p class="shop-item-desc">${escape_html(item.desc || (LANG === "id" ? "Tidak ada deskripsi." : "No description."))}</p>
                </div>
                <div class="shop-item-footer">
                    <div class="shop-item-cost">
                        <span class="shop-cost-lbl">${escape_html(t.cost)}</span>
                        <span class="shop-cost-val font-mono">
                            ${is_karma ? "✨" : "💰"}
                            ${format_number(item.cost)}
                        </span>
                    </div>
                    <button class="shop-buy-btn ${is_karma ? "!bg-indigo-600 hover:!bg-indigo-500 !border-indigo-500/20" : ""}" 
                            data-item-id="${escape_html(item._id)}"
                            ${has_owned ? "disabled" : ""}>
                        ${has_owned ? escape_html(t.already_owned) : escape_html(t.buy)}
                        ${!is_unstackable ? ` (${escape_html(t.owned)}: ${item.owned})` : ""}
                    </button>
                </div>
            </div>
        `;
    }

    html += `</div>`;
    container.innerHTML = html;

    container.querySelectorAll(".shop-buy-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
            const itemId = btn.getAttribute("data-item-id");
            await buy_shop_item(itemId, btn);
        });
    });
}

async function buy_shop_item(itemId, btn) {
    const orig_text = btn.innerHTML;
    btn.disabled = true;
    btn.textContent = LANG === "id" ? "Memproses..." : "Buying...";

    const status_el = document.getElementById("action-status-msg");

    try {
        const resp = await fetch("/api/v1/shop/buy", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ item_id: itemId })
        });
        const data = await resp.json();

        if (data.error) {
            if (status_el) {
                status_el.textContent = `❌ ${data.error}`;
                status_el.style.color = "#ef4444";
            }
            btn.innerHTML = orig_text;
            btn.disabled = false;
        } else {
            btn.classList.remove("bg-accent", "bg-indigo-600");
            btn.classList.add("bg-emerald-600");
            btn.textContent = LANG === "id" ? "Berhasil! ✓" : "Bought! ✓";

            if (status_el) {
                const success_msg = LANG === "id" 
                    ? `Berhasil membeli ${data.item_name}!` 
                    : `Successfully purchased ${data.item_name}!`;
                status_el.textContent = `✅ ${success_msg}`;
                status_el.style.color = "#10b981";
            }

            await fetch_profile();
            await fetch_inventory();
            await fetch_shop_items();
        }
    } catch (err) {
        if (status_el) {
            status_el.textContent = "❌ Connection error.";
            status_el.style.color = "#ef4444";
        }
        btn.innerHTML = orig_text;
        btn.disabled = false;
    }

    setTimeout(() => {
        if (status_el && (status_el.textContent.includes("✅") || status_el.textContent.includes("❌"))) {
            status_el.textContent = "";
        }
    }, 4000);
}

function init_shop() {
    const filter_container = document.getElementById("shop-filters");
    if (!filter_container) return;

    filter_container.querySelectorAll(".shop-filter-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            filter_container.querySelectorAll(".shop-filter-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            active_shop_filter = btn.getAttribute("data-filter");
            render_shop_items();
        });
    });

    fetch_shop_items();
}


// ── Init ────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    fetch_profile();
    fetch_inventory();
    fetch_stats();
    init_chat();
    init_shop();

    const daily_btn = document.getElementById("daily-btn");
    const adventure_btn = document.getElementById("adventure-btn");
    if (daily_btn) daily_btn.addEventListener("click", claim_daily);
    if (adventure_btn) adventure_btn.addEventListener("click", go_adventure);
});

