"""
Telegram Bot + Telethon UserBot
User @Bot ko message kare → Telethon (user account) process kare → Bot reply kare
"""

import asyncio
import re
import os
import logging
import time
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from dotenv import load_dotenv
from catbox import upload_to_catbox
import httpx

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

TERA_BOT   = os.getenv("TERA_BOT")
STREAM_BOT = os.getenv("STREAM_BOT")

def parse_channel(val):
    if val and val.lstrip("-").isdigit():
        return int(val)
    return val

CHANNEL_B = parse_channel(os.getenv("CHANNEL_B"))

# TeraBox sabhi domains
TERABOX_REGEX = re.compile(
    r"https?://(?:www\.)?(?:terabox|1024terabox|terafileshare|freeterabox|"
    r"4funbox|teraboxapp|mirrobox|nephobox|momerybox|tibibox|gibibox|qrubox|"
    r"jobespinas|teraboxlink|teraboxshare|mirrorbox)\.(?:com|net|app)/[^\s]+",
    re.IGNORECASE
)

# ── Clients ───────────────────────────────────────────────────
# Telethon user account — processing ke liye
user_client = TelegramClient(
    StringSession(SESSION_STRING) if SESSION_STRING else StringSession(),
    API_ID, API_HASH
)
# Bot client — users se baat karne ke liye
bot_client = TelegramClient(
    "bot_session", API_ID, API_HASH
)

# Pending requests store
user_pending = {}  # chat_id: {"image": bytes, "tera_url": str}


# ── Bot se reply karne ka helper ──────────────────────────────
async def bot_reply(chat_id: int, text: str):
    await bot_client.send_message(chat_id, text, parse_mode="md")


# ── TeraBox bot se video lo ───────────────────────────────────
async def get_video_from_tera_bot(tera_url: str):
    log.info(f"TeraBox bot ko URL bhej raha hun: {tera_url}")
    tera_entity = await user_client.get_entity(TERA_BOT)
    await user_client.send_message(tera_entity, tera_url)

    for attempt in range(36):
        await asyncio.sleep(5)
        messages = await user_client.get_messages(tera_entity, limit=5)
        for msg in messages:
            if msg.media and isinstance(msg.media, MessageMediaDocument):
                mime = getattr(msg.media.document, "mime_type", "")
                if "video" in mime or "octet-stream" in mime:
                    log.info("✅ TeraBox bot se video mil gaya!")
                    return msg
        log.info(f"TeraBox bot ka wait... ({attempt + 1}/36)")

    log.error("❌ TeraBox bot ne time pe video nahi diya.")
    return None


# ── Stream bot se link lo ─────────────────────────────────────
async def get_stream_link(video_msg) -> str | None:
    log.info("Stream bot ko forward kar raha hun...")
    stream_entity = await user_client.get_entity(STREAM_BOT)
    await user_client.forward_messages(entity=stream_entity, messages=video_msg)

    for attempt in range(24):
        await asyncio.sleep(5)
        messages = await user_client.get_messages(stream_entity, limit=3)
        for msg in messages:
            if msg.text and "http" in msg.text:
                log.info("✅ Stream link mila!")
                return msg.text.strip()
        log.info(f"Stream bot ka wait... ({attempt + 1}/24)")

    log.error("❌ Stream bot ne link nahi diya.")
    return None


# ── Full Pipeline ─────────────────────────────────────────────
async def process_request(chat_id: int, img_bytes: bytes | None, tera_url: str):
    await bot_reply(chat_id, "⏳ Processing shuru kar raha hun...")

    # 1. Image → Catbox
    catbox_link = None
    if img_bytes:
        await bot_reply(chat_id, "📸 Image catbox pe upload ho rahi hai...")
        catbox_link = await upload_to_catbox(img_bytes, filename="cover.jpg")
        if catbox_link:
            log.info(f"✅ Catbox: {catbox_link}")
        else:
            await bot_reply(chat_id, "⚠️ Catbox upload fail hua, aage badhta hun...")

    # 2. TeraBox → Video
    await bot_reply(chat_id, "🔗 TeraBox se video fetch ho rahi hai... (2-3 min lag sakte hain)")
    tera_video_msg = await get_video_from_tera_bot(tera_url)
    if not tera_video_msg:
        await bot_reply(chat_id, "❌ TeraBox se video nahi mila. Dobara try karo.")
        user_pending.pop(chat_id, None)
        return

    # 3. Stream link — TeraBox ki ORIGINAL video se (naya msg = naya link)
    await bot_reply(chat_id, "▶️ Stream link ban raha hai...")
    stream_link = await get_stream_link(tera_video_msg)

    # 4. Video → Channel B
    await bot_reply(chat_id, "📤 Video store ho rahi hai...")
    channel_b_entity = await user_client.get_entity(CHANNEL_B)
    await user_client.forward_messages(
        entity=channel_b_entity,
        messages=tera_video_msg,
    )
    log.info("✅ Channel B pe forward hua")

    # 5. User ko sirf 2 links
    lines = ["✅ **Done!**\n"]
    if catbox_link:
        lines.append(f"🖼 **Cover:**\n{catbox_link}")
    if stream_link:
        lines.append(f"▶️ **Stream:**\n{stream_link}")

    await bot_reply(chat_id, "\n\n".join(lines))
    log.info(f"🎉 Chat {chat_id} ka kaam done!")
    user_pending.pop(chat_id, None)


# ── Bot Event Handler ─────────────────────────────────────────
@bot_client.on(events.NewMessage(incoming=True))
async def handle_bot_message(event):
    msg = event.message
    chat_id = event.chat_id
    text = msg.text or msg.caption or ""

    # /start
    if text.strip() == "/start":
        await bot_reply(
            chat_id,
            "👋 **Welcome!**\n\n"
            "Mujhe **TeraBox link** bhejo (saath mein **image** bhi bhej sakte ho) "
            "aur main tumhe deta hun:\n\n"
            "🖼 Catbox image link\n"
            "▶️ Stream link\n\n"
            "**Supported domains:**\n"
            "`terabox.com, 1024terabox.com, teraboxapp.com,\n"
            "nephobox.com, mirrorbox.com, freeterabox.com,\n"
            "teraboxlink.com, 4funbox.com, terafileshare.com`\n\n"
            "💡 Image aur link ek saath ya alag alag bhej sakte ho!"
        )
        return

    # TeraBox URL check
    tera_match = TERABOX_REGEX.search(text)
    tera_url = tera_match.group(0) if tera_match else None

    # Image check
    has_image = isinstance(msg.media, MessageMediaPhoto)
    img_bytes = None
    if has_image:
        img_bytes = await bot_client.download_media(msg.media, bytes)

    # Pending mein store
    if chat_id not in user_pending:
        user_pending[chat_id] = {}

    if img_bytes:
        user_pending[chat_id]["image"] = img_bytes
    if tera_url:
        user_pending[chat_id]["tera_url"] = tera_url

    pending = user_pending[chat_id]

    # Dono available hain → process karo
    if "tera_url" in pending:
        asyncio.create_task(process_request(
            chat_id,
            pending.get("image"),
            pending["tera_url"]
        ))
    elif "image" in pending and "tera_url" not in pending:
        await bot_reply(chat_id, "✅ Image mil gayi! Ab **TeraBox link** bhejo.")
    else:
        await bot_reply(chat_id, "❓ TeraBox link nahi mili. Sahi link bhejo.")


# ── Entry Point ───────────────────────────────────────────────
async def main():
    log.info("🚀 Bot + UserBot start ho rahe hain...")
    await user_client.start()
    await bot_client.start(bot_token=BOT_TOKEN)

    me = await user_client.get_me()
    bot_me = await bot_client.get_me()
    log.info(f"✅ UserBot: {me.first_name} (@{me.username})")
    log.info(f"✅ Bot: @{bot_me.username}")
    log.info("⏳ Users ke messages ka wait kar raha hun...")

    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected(),
    )


if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            log.error(f"❌ Restarting after error: {e}")
            time.sleep(5)
