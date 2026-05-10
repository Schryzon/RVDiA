import os
import json
import urllib.request
import discord
from dotenv import load_dotenv
from PIL import Image
from ddgs import DDGS

load_dotenv()

def download_and_crop(url, name):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        filename = f'scratch/{name}.png'
        with urllib.request.urlopen(req) as response:
            with open(filename, 'wb') as f:
                f.write(response.read())
        
        # Crop 1:1 using Pillow
        with Image.open(filename) as img:
            width, height = img.size
            new_size = min(width, height)
            
            left = (width - new_size) / 2
            top = (height - new_size) / 2
            right = (width + new_size) / 2
            bottom = (height + new_size) / 2
            
            img_cropped = img.crop((left, top, right, bottom))
            img_cropped = img_cropped.resize((512, 512), Image.Resampling.LANCZOS)
            img_cropped.convert('RGB').save(filename, 'PNG')
            
        return filename
    except Exception as e:
        print(f'Failed to process {name}: {e}')
        return None

class UploadClient(discord.Client):
    async def on_ready(self):
        print(f'Logged on as {self.user}!')
        channel = self.get_channel(1121401627513983048) # Log channel from .env
        
        with open('src/game/enemies/bonus.json', 'r', encoding='utf-8') as f:
            enemies = json.load(f)
            
        ddgs = DDGS()
            
        for enemy in enemies:
            if enemy['name'] == 'Shiruto':
                continue
            
            print(f'Processing {enemy["name"]}...')
            query = f'{enemy["name"]} icon square'
            imgs = list(ddgs.images(query, max_results=3))
            
            if not imgs:
                query = f'{enemy["name"]} wallpaper'
                imgs = list(ddgs.images(query, max_results=3))
            
            if imgs:
                for img_data in imgs:
                    url = img_data['image']
                    filename = download_and_crop(url, enemy['name'].replace(' ', '_'))
                    if filename:
                        # Upload to discord
                        msg = await channel.send(file=discord.File(filename))
                        enemy['avatar'] = msg.attachments[0].url
                        print(f"Uploaded {enemy['name']}: {enemy['avatar']}")
                        os.remove(filename) # cleanup
                        break
                
        with open('src/game/enemies/bonus.json', 'w', encoding='utf-8') as f:
            json.dump(enemies, f, indent=4)
            
        print("Finished uploading!")
        await self.close()

intents = discord.Intents.default()
client = UploadClient(intents=intents)
client.run(os.environ.get('token'))
