"""
Telegram Bot + Telethon UserBot
"""

import asyncio
import re
import os
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from dotenv import load_dotenv
from catbox import upload_to_catbox

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── Credentials ───────────────────────────────────────────────
API_ID         = int(os.getenv("TG_API_ID"))
API_HASH       = os.getenv("TG_API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
BOT_TOKEN      = os.getenv("BOT_TOKEN")
TERA_BOT       = os.getenv("TERA_BOT")
STREAM_BOT     = os.getenv("STREAM_BOT")

def parse_channel(val):
    if val and val.lstrip("-").isdigit():
        return int(val)
    return val

CHANNEL_B = parse_channel(os.getenv("CHANNEL_B"))

TERABOX_REGEX = re.compile(
    r"https?://(?:www\.)?(?:terabox|1024terabox|terafileshare|freeterabox|"
    r"4funbox|teraboxapp|mirrobox|nephobox|momerybox|tibibox|gibibox|qrubox|"
    r"jobespinas|teraboxlink|teraboxshare|mirrorbox)\.(?:com|net|app)/[^\s]+",
    re.IGNORECASE
)

# Pending requests
user_pending = {}


async def bot_reply(bot_client, chat_id: int, text: str):
    await bot_client.send_message(chat_id, text, parse_mode="md")


async def get_video_from_tera_bot(user_client, tera_lock, tera_url: str):
    """Lock ke andar TeraBox bot ko link bhejo — ek waqt pe sirf ek request."""
    async with tera_lock:
        log.info(f"TeraBox bot ko URL bhej raha hun: {tera_url}")
        tera_entity = await user_client.get_entity(TERA_BOT)

        # Pehle last message ID note karo
        old_msgs = await user_client.get_messages(tera_entity, limit=1)
        last_id = old_msgs[0].id if old_msgs else 0
        log.info(f"Last ID: {last_id}")

        await user_client.send_message(tera_entity, tera_url)

        # Sirf last_id ke baad wali nai video dhundo
        for attempt in range(36):
            await asyncio.sleep(5)
            new_msgs = await user_client.get_messages(tera_entity, min_id=last_id, limit=10)
            for msg in new_msgs:
                if msg.media and isinstance(msg.media, MessageMediaDocument):
                    mime = getattr(msg.media.document, "mime_type", "")
                    if "video" in mime or "octet-stream" in mime:
                        log.info(f"✅ Naya video mila! ID: {msg.id}")
                        return msg
            log.info(f"Wait... ({attempt + 1}/36)")

        log.error("❌ TeraBox bot ne video nahi diya.")
        return None


async def get_stream_link(user_client, video_msg) -> str | None:
    log.info("Stream bot ko forward kar raha hun...")
    stream_entity = await user_client.get_entity(STREAM_BOT)

    old_msgs = await user_client.get_messages(stream_entity, limit=1)
    last_id = old_msgs[0].id if old_msgs else 0

    await user_client.forward_messages(entity=stream_entity, messages=video_msg)

    for attempt in range(24):
        await asyncio.sleep(5)
        new_msgs = await user_client.get_messages(stream_entity, min_id=last_id, limit=5)
        for msg in new_msgs:
            if msg.text and "http" in msg.text:
                log.info("✅ Stream link mila!")
                return msg.text.strip()
        log.info(f"Stream wait... ({attempt + 1}/24)")

    log.error("❌ Stream bot ne link nahi diya.")
    return None


async def process_request(bot_client, user_client, tera_lock, chat_id, img_bytes, tera_url):
    await bot_reply(bot_client, chat_id, "⏳ Processing shuru kar raha hun...")

    # 1. Catbox
    catbox_link = None
    if img_bytes:
        await bot_reply(bot_client, chat_id, "📸 Image upload ho rahi hai...")
        catbox_link = await upload_to_catbox(img_bytes, filename="cover.jpg")

    # 2. TeraBox → Video
    await bot_reply(bot_client, chat_id, "🔗 Video fetch ho rahi hai... (2-3 min lag sakte hain)")
    tera_video_msg = await get_video_from_tera_bot(user_client, tera_lock, tera_url)
    if not tera_video_msg:
        await bot_reply(bot_client, chat_id, "❌ Video nahi mila. Dobara try karo.")
        user_pending.pop(chat_id, None)
        return

    # 3. Stream link
    await bot_reply(bot_client, chat_id, "▶️ Stream link ban raha hai...")
    stream_link = await get_stream_link(user_client, tera_video_msg)

    # 4. Channel B pe store
    channel_b_entity = await user_client.get_entity(CHANNEL_B)
    await user_client.forward_messages(entity=channel_b_entity, messages=tera_video_msg)

    # 5. Sirf 2 links user ko
    lines = ["✅ **Done!**\n"]
    if catbox_link:
        lines.append(f"🖼 **Cover:**\n{catbox_link}")
    if stream_link:
        lines.append(f"▶️ **Stream:**\n{stream_link}")

    await bot_reply(bot_client, chat_id, "\n\n".join(lines))
    log.info(f"🎉 Done for {chat_id}")
    user_pending.pop(chat_id, None)


async def main():
    log.info("🚀 Bot + UserBot start ho rahe hain...")

    # Clients aur lock — sab ek hi event loop mein
    tera_lock = asyncio.Lock()

    user_client = TelegramClient(
        StringSession(SESSION_STRING) if SESSION_STRING else StringSession(),
        API_ID, API_HASH
    )
    bot_client = TelegramClient("bot_session", API_ID, API_HASH)

    @bot_client.on(events.NewMessage(incoming=True))
    async def handle_bot_message(event):
        msg = event.message
        chat_id = event.chat_id
        text = msg.text or msg.caption or ""

        if text.strip() == "/start":
            await bot_reply(
                bot_client, chat_id,
                "👋 **Welcome!**\n\n"
                "Mujhe **TeraBox link** bhejo (saath mein **image** bhi bhej sakte ho):\n\n"
                "🖼 Catbox image link milega\n"
                "▶️ Stream link milega\n\n"
                "💡 Image aur link ek saath ya alag alag bhej sakte ho!"
            )
            return

        tera_match = TERABOX_REGEX.search(text)
        tera_url = tera_match.group(0) if tera_match else None

        img_bytes = None
        if isinstance(msg.media, MessageMediaPhoto):
            img_bytes = await bot_client.download_media(msg.media, bytes)

        if chat_id not in user_pending:
            user_pending[chat_id] = {}

        if img_bytes:
            user_pending[chat_id]["image"] = img_bytes
        if tera_url:
            user_pending[chat_id]["tera_url"] = tera_url

        pending = user_pending[chat_id]

        if "tera_url" in pending:
            asyncio.create_task(process_request(
                bot_client, user_client, tera_lock,
                chat_id,
                pending.get("image"),
                pending["tera_url"]
            ))
        elif "image" in pending:
            await bot_reply(bot_client, chat_id, "✅ Image mil gayi! Ab **TeraBox link** bhejo.")
        else:
            await bot_reply(bot_client, chat_id, "❓ TeraBox link nahi mili. Sahi link bhejo.")


    await user_client.start()
    await bot_client.start(bot_token=BOT_TOKEN)

    me = await user_client.get_me()
    bot_me = await bot_client.get_me()
    log.info(f"✅ UserBot: {me.first_name} (@{me.username})")
    log.info(f"✅ Bot: @{bot_me.username}")
    log.info("⏳ Messages ka wait kar raha hun...")
    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected(),
    )


if __name__ == "__main__":
    asyncio.run(main())
