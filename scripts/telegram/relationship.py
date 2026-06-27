import os
import json
from prisma import Json
from scripts.main import db
from scripts.ai.relationship import relationship_service
from scripts.utils.telegram import send_telegram_message, telegram_client
from scripts.utils.i18n import i18n

def setup(zora):
    @zora.command(["/bond", "/hubungan"])
    async def handle_bond(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang, thread_id=None, **_):
        virtual_id = -telegram_user_id

        # Subcommand router
        sub = args[0].lower() if args else None

        if sub == "start":
            existing = await relationship_service.get_relationship(virtual_id)
            if existing:
                msg = "Kamu sudah memulai hubungan dengan RVDiA! ❤️" if lang == "id" else "You have already started your bond with RVDiA! ❤️"
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            success = await relationship_service.start_relationship(virtual_id)
            if not success:
                msg = "Gagal memulai hubungan. Silakan coba beberapa saat lagi!" if lang == "id" else "Failed to start relationship. Please try again later!"
                return await send_telegram_message(chat_id, f"❌ {msg}", thread_id=thread_id)

            await relationship_service.add_affinity(virtual_id, 10)

            msg = (
                "🌸 <b>Ikatan Dimulai!</b>\n\n"
                "Kamu telah resmi menjalin ikatan dengan RVDiA!\n"
                "Dia tersenyum manis ke arahmu.\n\n"
                "<i>\"Halo manis! Mari kita saling mengenal satu sama lain lebih dekat ya~\"</i> 💖"
            ) if lang == "id" else (
                "🌸 <b>Bond Initiated!</b>\n\n"
                "You have officially started a bond with RVDiA!\n"
                "She smiles warmly at you.\n\n"
                "<i>\"Hello cutie! Let's get to know each other much better from now on~\"</i> 💖"
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        elif sub == "nickname":
            if len(args) < 3:
                msg = (
                    "Format salah! Gunakan:\n"
                    "• <code>/bond nickname user [panggilan]</code> (ubah panggilanmu)\n"
                    "• <code>/bond nickname rvdia [panggilan]</code> (ubah panggilan dia)"
                ) if lang == "id" else (
                    "Incorrect format! Use:\n"
                    "• <code>/bond nickname user [name]</code> (change how she calls you)\n"
                    "• <code>/bond nickname rvdia [name]</code> (change how you call her)"
                )
                return await send_telegram_message(chat_id, msg, thread_id=thread_id)

            target = args[1].lower()
            new_nick = " ".join(args[2:])
            
            if target not in ["user", "rvdia"]:
                msg = "Target tidak valid! Gunakan 'user' atau 'rvdia'." if lang == "id" else "Invalid target! Use 'user' or 'rvdia'."
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            if len(new_nick) > 15:
                msg = "Nama panggilan maksimal 15 karakter! ❌" if lang == "id" else "Nickname cannot exceed 15 characters! ❌"
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            rel = await relationship_service.get_relationship(virtual_id)
            if not rel:
                msg = "Kamu harus memulai hubungan dengan <code>/bond start</code> terlebih dahulu! 🌸" if lang == "id" else "You must start your bond with <code>/bond start</code> first! 🌸"
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            update_field = 'userNickname' if target == "user" else 'rvdiaNickname'
            await db.relationship.update(
                where={'userId': virtual_id},
                data={update_field: new_nick}
            )

            msg = (
                f"✅ Panggilan berhasil diubah! Sekarang aku akan memanggilmu <b>{new_nick}</b>."
                if target == "user" else
                f"✅ Panggilan berhasil diubah! Panggilanmu untukku sekarang adalah <b>{new_nick}</b>."
            ) if lang == "id" else (
                f"✅ Nickname updated! I will now call you <b>{new_nick}</b>."
                if target == "user" else
                f"✅ Nickname updated! Your nickname for me is now <b>{new_nick}</b>."
            )
            return await send_telegram_message(chat_id, msg, thread_id=thread_id)

        elif sub == "gift":
            rel = await relationship_service.get_relationship(virtual_id)
            if not rel:
                msg = "Kamu harus memulai hubungan dengan <code>/bond start</code> terlebih dahulu! 🌸" if lang == "id" else "You must start your bond with <code>/bond start</code> first! 🌸"
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            # Fetch inventory
            inventory = await db.inventory.find_unique(where={'userId': virtual_id})
            if not inventory or not isinstance(inventory.items, list):
                msg = "Kamu tidak memiliki item di inventarismu! 🎒" if lang == "id" else "You don't have any items in your inventory! 🎒"
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            consumables = [it for it in inventory.items if it.get('type') == 'Consumable' and it.get('owned', 0) > 0]
            if not consumables:
                msg = "Kamu tidak memiliki barang konsumsi (Consumable) untuk dihadiahkan! 🎒" if lang == "id" else "You don't have any consumable items to gift! 🎒"
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            # Build inline keyboard buttons
            keyboard = []
            for it in consumables[:25]:
                keyboard.append([{"text": f"🎁 {it['name']} (x{it['owned']})", "callback_data": f"bond_gift:{it['_id']}:{telegram_user_id}"}])

            prompt = "Pilih item untuk dihadiahkan kepada RVDiA:" if lang == "id" else "Choose an item to gift to RVDiA:"
            return await send_telegram_message(chat_id, prompt, thread_id=thread_id, reply_markup={"inline_keyboard": keyboard})

        elif sub == "reset":
            rel = await relationship_service.get_relationship(virtual_id)
            if not rel:
                msg = "Kamu belum memulai hubungan dengan RVDiA! 🌸" if lang == "id" else "You haven't started your bond with RVDiA yet! 🌸"
                return await send_telegram_message(chat_id, f"⚠️ {msg}", thread_id=thread_id)

            keyboard = [[
                {"text": "Ya, Reset Hubungan" if lang == "id" else "Yes, Reset Bond", "callback_data": f"bond_confirm_reset:{telegram_user_id}"},
                {"text": "Batal" if lang == "id" else "Cancel", "callback_data": f"bond_cancel_reset:{telegram_user_id}"}
            ]]

            prompt = (
                "Apakah kamu yakin ingin me-reset hubungan dengan RVDiA?\n"
                "Tingkat hubungan dan kedekatanmu dengannya akan dihapus secara permanen! (Chat memori tidak terpengaruh) 🥺"
            ) if lang == "id" else (
                "Are you sure you want to reset your relationship with RVDiA?\n"
                "Your stage and affinity progress will be permanently deleted! (Chat memory will not be affected) 🥺"
            )
            return await send_telegram_message(chat_id, prompt, thread_id=thread_id, reply_markup={"inline_keyboard": keyboard})

        else:
            # Default: Show bond info card
            rel = await relationship_service.get_relationship(virtual_id)
            if not rel:
                title = "💖 Hubungan dengan RVDiA" if lang == "id" else "💖 Bond with RVDiA"
                desc = (
                    f"<b>{title}</b>\n━━━━━━━━━━━━━━━━━━━\n"
                    "Kamu belum memulai hubungan dengan RVDiA!\n"
                    "Ketik <code>/bond start</code> untuk mulai mengobrol dekat dan menjalin ikatan dengannya! 🌸"
                ) if lang == "id" else (
                    f"<b>{title}</b>\n━━━━━━━━━━━━━━━━━━━\n"
                    "You haven't started your bond with RVDiA yet!\n"
                    "Type <code>/bond start</code> to begin chatting closely and building a bond with her! 🌸"
                )
                return await send_telegram_message(chat_id, desc, thread_id=thread_id)

            affinity = rel.affinity
            stage = rel.stage
            stage_label = relationship_service.get_stage_label(stage, lang)
            stage_desc = relationship_service.get_stage_description(stage, lang)
            bar, threshold = relationship_service.get_progress_bar(affinity, stage)

            user_nick = rel.userNickname or full_name
            rvdia_nick = rel.rvdiaNickname or "RVDiA"

            title = f"💝 Hubunganmu dengan {rvdia_nick}" if lang == "id" else f"💝 Your Bond with {rvdia_nick}"
            
            lines = [
                f"<b>{title}</b>",
                "━━━━━━━━━━━━━━━━━━━",
                f"👤 <b>Tingkat Hubungan:</b> {stage_label}",
                f"📈 <b>Affinity:</b> <code>{affinity}/{threshold}</code>",
                f"<code>{bar}</code>\n",
                f"<i>\"{stage_desc}\"</i>\n",
                f"🗣️ <b>Nama Panggilan:</b>",
                f"• Panggilanmu untuk dia: <b>{rvdia_nick}</b>",
                f"• Panggilan dia untukmu: <b>{user_nick}</b>"
            ]

            if stage == "lover" and rel.anniversary:
                anniv_str = rel.anniversary.strftime("%d %B %Y")
                anniv_lbl = "💍 Hari Jadi" if lang == "id" else "💍 Anniversary"
                lines.append(f"\n{anniv_lbl}: Kalian resmi pacaran sejak <b>{anniv_str}</b>! 💕" if lang == "id" else f"\n{anniv_lbl}: You officially became lovers on <b>{anniv_str}</b>! 💕")

            return await send_telegram_message(chat_id, "\n".join(lines), thread_id=thread_id)

    @zora.callback_query("bond_gift:")
    async def handle_bond_gift_callback(zora_bot, chat_id, message_id, cq_id, telegram_user_id, username, full_name, data, lang):
        # Format: bond_gift:item_id:original_user_id
        parts = data.split(":")
        if len(parts) < 3:
            return
        
        item_id = parts[1]
        owner_id = int(parts[2])

        if telegram_user_id != owner_id:
            msg = "Ini bukan interaksi Anda! ❌" if lang == "id" else "This is not your interaction! ❌"
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id, text=msg)
            return

        virtual_id = -telegram_user_id

        # Load shop.json
        try:
            shop_path = os.path.join(os.path.dirname(__file__), "../../src/game/shop.json")
            with open(shop_path, 'r', encoding='utf-8') as f:
                shop_items = json.load(f)
        except Exception:
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id, text="Error loading shop!")
            return

        matched = next((item for item in shop_items if item["_id"] == item_id), None)
        if not matched:
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id, text="Invalid item!")
            return

        # Retrieve inventory
        inventory = await db.inventory.find_unique(where={'userId': virtual_id})
        if not inventory or not isinstance(inventory.items, list):
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id, text="Inventory not found!")
            return

        user_items = inventory.items
        item_index = -1
        for idx, it in enumerate(user_items):
            if it.get('_id') == item_id:
                item_index = idx
                break

        if item_index == -1 or user_items[item_index].get('owned', 0) <= 0:
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id, text="You don't own this item!")
            return

        # Decrement quantity
        user_items[item_index]['owned'] -= 1
        if user_items[item_index]['owned'] <= 0:
            user_items.pop(item_index)

        # Save inventory
        await db.inventory.update(
            where={'userId': virtual_id},
            data={'items': Json(user_items)}
        )

        # Calculate affinity reward
        cost = matched.get('cost', 0)
        if cost <= 100:
            affinity_gain = 8
        elif cost <= 500:
            affinity_gain = 18
        else:
            affinity_gain = 35

        if matched.get('paywith') == "Karma":
            affinity_gain = matched.get('cost', 0) * 2

        new_affinity, new_stage, shifted = await relationship_service.add_affinity(virtual_id, affinity_gain)

        if lang == "id":
            res_text = (
                f"🎁 <b>Hadiah untuk RVDiA</b>\n\n"
                f"RVDiA tersenyum lebar saat kamu memberikan <b>{matched['name']}</b>.\n"
                f"<i>\"Aaaaah! Makasih banyak ya, sayangku! Aku suka banget hadiahnya!~\"</i>\n\n"
                f"📈 <b>+{affinity_gain} Affinity</b> (Total: <code>{new_affinity}/1000</code>)"
            )
            if shifted:
                res_text += f"\n\n🌸 <b>Hubungan meningkat!</b> Tingkat saat ini: <b>{relationship_service.get_stage_label(new_stage, 'id')}</b>"
        else:
            res_text = (
                f"🎁 <b>Gift for RVDiA</b>\n\n"
                f"RVDiA smiles brightly as you hand her the <b>{matched['name']}</b>.\n"
                f"<i>\"Aaaaah! Thank you so much, sweetie! I absolutely love this gift!~\"</i>\n\n"
                f"📈 <b>+{affinity_gain} Affinity</b> (Total: <code>{new_affinity}/1000</code>)"
            )
            if shifted:
                res_text += f"\n\n🌸 <b>Relationship stage upgraded!</b> Current Stage: <b>{relationship_service.get_stage_label(new_stage, 'en')}</b>"

        if telegram_client:
            await telegram_client.edit_message_text(chat_id, message_id, res_text, reply_markup=None)
            await telegram_client.answer_callback_query(cq_id)

    @zora.callback_query("bond_confirm_reset:")
    async def handle_bond_confirm_reset(zora_bot, chat_id, message_id, cq_id, telegram_user_id, username, full_name, data, lang):
        owner_id = int(data.split(":")[1])
        if telegram_user_id != owner_id:
            msg = "Ini bukan interaksi Anda! ❌" if lang == "id" else "This is not your interaction! ❌"
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id, text=msg)
            return

        virtual_id = -telegram_user_id
        try:
            await db.relationship.delete(where={'userId': virtual_id})
            success_msg = (
                "✅ Hubunganmu dengan RVDiA telah direset. "
                "Kalian kembali menjadi orang asing... 🥺"
            ) if lang == "id" else (
                "✅ Your bond with RVDiA has been reset. "
                "You are strangers once again... 🥺"
            )
        except Exception as e:
            success_msg = f"❌ Gagal reset: {e}"

        if telegram_client:
            await telegram_client.edit_message_text(chat_id, message_id, success_msg, reply_markup=None)
            await telegram_client.answer_callback_query(cq_id)

    @zora.callback_query("bond_cancel_reset:")
    async def handle_bond_cancel_reset(zora_bot, chat_id, message_id, cq_id, telegram_user_id, username, full_name, data, lang):
        owner_id = int(data.split(":")[1])
        if telegram_user_id != owner_id:
            msg = "Ini bukan interaksi Anda! ❌" if lang == "id" else "This is not your interaction! ❌"
            if telegram_client:
                await telegram_client.answer_callback_query(cq_id, text=msg)
            return

        cancel_msg = "Pembatalan dilakukan." if lang == "id" else "Reset cancelled."
        if telegram_client:
            await telegram_client.edit_message_text(chat_id, message_id, cancel_msg, reply_markup=None)
            await telegram_client.answer_callback_query(cq_id)
