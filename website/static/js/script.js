document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("command-search");
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            const term = e.target.value.toLowerCase();
            const cards = document.querySelectorAll(".command-card");
            
            cards.forEach(card => {
                const name = card.querySelector(".command-name").innerText.toLowerCase();
                const desc = card.querySelector(".command-desc").innerText.toLowerCase();
                const cat = card.querySelector(".command-category").innerText.toLowerCase();
                
                if (name.includes(term) || desc.includes(term) || cat.includes(term)) {
                    card.style.display = "block";
                } else {
                    card.style.display = "none";
                }
            });
        });
    }
});
