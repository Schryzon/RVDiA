import json
import urllib.parse

urls = {
    "Kamen Rider Kuuga (Ultimate)": "https://vignette.wikia.nocookie.net/kamenrider/images/b/bd/Kamen_Rider_Kuuga.jpg",
    "Kamen Rider Agito (Shining)": "https://vignette.wikia.nocookie.net/kamenrider/images/d/da/Agito_Kamen_Rider_Battride_War_Genesis.png",
    "Kamen Rider Ryuki (Survive)": "https://static.wikia.nocookie.net/kamenrider/images/b/b4/Ryuki_Survive_Module.png",
    "Kamen Rider Faiz (Blaster)": "https://static.wikia.nocookie.net/kamenrider/images/f/f6/Kamen_Rider_Faiz_-_Kamen_Rider_Battride_War_Genesis.png",
    "Kamen Rider Blade (King)": "https://static.wikia.nocookie.net/kamenrider/images/7/70/KRBl-Garrenking.png",
    "Kamen Rider Hibiki (Armed)": "https://vignette.wikia.nocookie.net/kamenrider/images/c/c3/Hibiki_Module.png",
    "Kamen Rider Kabuto (Hyper Form)": "https://static.wikia.nocookie.net/kamenrider/images/d/d5/Kabuto_Hyper_Battle.png",
    "Kamen Rider Den-O (Liner)": "https://static.wikia.nocookie.net/kamenrider/images/e/ef/Den-O_Trains.jpg",
    "Kamen Rider Kiva (Emperor)": "https://static.wikia.nocookie.net/kamenrider/images/c/c0/LastmomentsArc.jpg",
    "Kamen Rider Decade (Complete)": "https://static.wikia.nocookie.net/kamenrider/images/b/b9/Rider_Time_Decade_VS_Zi-O_Poster.jpg"
}

with open('src/game/enemies/bonus.json', 'r', encoding='utf-8') as f:
    enemies = json.load(f)

for enemy in enemies:
    name = enemy['name']
    if name in urls:
        encoded_url = urllib.parse.quote(urls[name])
        wsrv_url = f'https://wsrv.nl/?url={encoded_url}&w=512&h=512&fit=cover&a=attention'
        enemy['avatar'] = wsrv_url

with open('src/game/enemies/bonus.json', 'w', encoding='utf-8') as f:
    json.dump(enemies, f, indent=4)
