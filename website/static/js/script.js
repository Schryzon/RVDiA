const init = () => {
    // Mobile Menu Toggle
    const menuToggle = document.getElementById("mobile-menu");
    const navLinks = document.querySelector(".nav-links");

    if (menuToggle && navLinks) {
        menuToggle.addEventListener("click", () => {
            menuToggle.classList.toggle("is-active");
            navLinks.classList.toggle("active");
        });

        // Close menu when clicking a link
        const navItems = document.querySelectorAll(".nav-links a");
        navItems.forEach(item => {
            item.addEventListener("click", () => {
                menuToggle.classList.remove("is-active");
                navLinks.classList.remove("active");
            });
        });
    }

    const searchInput = document.getElementById("command-search");
    if (searchInput) {
        // Collapsible Logic
        const collapsibles = document.querySelectorAll(".command-card.collapsible");
        collapsibles.forEach(card => {
            card.addEventListener("click", () => {
                card.classList.toggle("active");
            });
        });

        // Search Logic
        searchInput.addEventListener("input", (e) => {
            const term = e.target.value.toLowerCase();
            const categories = document.querySelectorAll(".category-section");
            
            categories.forEach(category => {
                const cards = category.querySelectorAll(".command-card");
                let visibleCount = 0;
                
                cards.forEach(card => {
                    const name = card.querySelector(".command-name").innerText.toLowerCase();
                    const desc = card.querySelector(".command-desc").innerText.toLowerCase();
                    
                    // Also search in subcommands if they exist
                    const subcommandsText = Array.from(card.querySelectorAll(".subcommand-item"))
                        .map(sub => sub.innerText.toLowerCase())
                        .join(" ");
                    
                    if (name.includes(term) || desc.includes(term) || subcommandsText.includes(term)) {
                        card.style.display = "block";
                        visibleCount++;
                    } else {
                        card.style.display = "none";
                    }
                });
                
                // Hide category if no commands are visible
                if (visibleCount > 0) {
                    category.style.display = "block";
                } else {
                    category.style.display = "none";
                }
            });
        });
    }
};

document.addEventListener("DOMContentLoaded", () => {
    const loader = document.getElementById("page-loader");
    const loaderText = document.getElementById("loader-text");
    
    // Initial Fade Out
    setTimeout(() => {
        loader.classList.remove("active");
        document.body.classList.remove("loading");
    }, 500);

    init();

    // Intercept Links for Transitions
    document.addEventListener("click", async (e) => {
        const link = e.target.closest("a");
        if (!link) return;
        
        const url = link.getAttribute("href");
        const target = link.getAttribute("target");

        // Only handle internal links that aren't opening in new tab
        // Exclude dashboard/login (need their own JS) and API routes (OAuth redirects)
        const spa_exclude = ["/dashboard", "/login", "/api/"];
        const is_excluded = spa_exclude.some(prefix => url.startsWith(prefix));
        if (url && url.startsWith("/") && target !== "_blank" && !url.startsWith("/static") && !is_excluded) {
            e.preventDefault();
            
            // Start Animation
            document.body.classList.add("loading");
            loader.classList.add("active");
            loaderText.style.setProperty("--loading-progress", "30%");
            
            try {
                const response = await fetch(url);
                loaderText.style.setProperty("--loading-progress", "70%");
                const html = await response.text();
                
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, "text/html");
                
                const newContent = doc.getElementById("main-content").innerHTML;
                const newTitle = doc.title;
                
                // Smooth transition wait
                setTimeout(() => {
                    document.getElementById("main-content").innerHTML = newContent;
                    document.title = newTitle;
                    window.history.pushState({ html, title: newTitle }, "", url);
                    
                    loaderText.style.setProperty("--loading-progress", "100%");
                    
                    // Re-init logic
                    init();
                    
                    // Scroll to top
                    window.scrollTo(0, 0);

                    // End Animation
                    setTimeout(() => {
                        loader.classList.remove("active");
                        document.body.classList.remove("loading");
                        setTimeout(() => { loaderText.style.setProperty("--loading-progress", "0%"); }, 500);
                    }, 400);
                }, 600);
                
            } catch (err) {
                console.error("Transition failed:", err);
                window.location.href = url; // Fallback
            }
        }
    });

    // Handle Back/Forward
    window.addEventListener("popstate", (e) => {
        if (e.state) {
            const parser = new DOMParser();
            const doc = parser.parseFromString(e.state.html, "text/html");
            document.getElementById("main-content").innerHTML = doc.getElementById("main-content").innerHTML;
            document.title = e.state.title;
            init();
        } else {
            window.location.reload();
        }
    });
});
