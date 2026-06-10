"""
Telegram Auto-Bot — Main Orchestrator
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

TERA_BOT   = os.getenv("TERA_BOT")
STREAM_BOT = os.getenv("STREAM_BOT")

def parse_channel(val):
    if val and val.lstrip("-").isdigit():
        return int(val)
    return val

CHANNEL_A = parse_channel(os.getenv("CHANNEL_A"))
CHANNEL_B = parse_channel(os.getenv("CHANNEL_B"))
CHANNEL_C = parse_channel(os.getenv("CHANNEL_C"))

TERABOX_REGEX = re.compile(
    r"https?://(?:www\.)?(?:terabox|1024terabox|terafileshare|freeterabox|"
    r"4funbox|teraboxapp|mirrobox|nephobox|momerybox|tibibox|"
    r"gibibox|qrubox|jobespinas)\.(?:com|net|app)/[^\s]+",
    re.IGNORECASE
)

session = StringSession(SESSION_STRING) if SESSION_STRING else StringSession()
client = TelegramClient(session, API_ID, API_HASH)


async def get_video_from_tera_bot(tera_url: str):
    log.info(f"TeraBox bot ko URL bhej raha hun: {tera_url}")
    tera_entity = await client.get_entity(TERA_BOT)
    await client.send_message(tera_entity, tera_url)

    for attempt in range(36):
        await asyncio.sleep(5)
        messages = await client.get_messages(tera_entity, limit=5)
        for msg in messages:
            if msg.media and isinstance(msg.media, MessageMediaDocument):
                mime = getattr(msg.media.document, "mime_type", "")
                if "video" in mime or "octet-stream" in mime:
                    log.info("✅ TeraBox bot se video mil gaya!")
                    return msg
        log.info(f"TeraBox bot ka wait kar raha hun... ({attempt + 1}/36)")

    log.error("❌ TeraBox bot ne time pe video nahi diya.")
    return None


async def get_stream_link_from_bot(video_msg) -> str | None:
    log.info("Stream bot ko video forward kar raha hun...")
    stream_entity = await client.get_entity(STREAM_BOT)

    await client.forward_messages(
        entity=stream_entity,
        messages=video_msg,
    )

    for attempt in range(24):
        await asyncio.sleep(5)
        messages = await client.get_messages(stream_entity, limit=3)
        for msg in messages:
            if msg.text and ("http" in msg.text or "https" in msg.text):
                log.info(f"✅ Stream link mila: {msg.text.strip()}")
                return msg.text.strip()
        log.info(f"Stream bot ka wait kar raha hun... ({attempt + 1}/24)")

    log.error("❌ Stream bot ne time pe link nahi diya.")
    return None


@client.on(events.NewMessage(chats=CHANNEL_A))
async def handle_new_post(event):
    msg = event.message
    text = msg.text or msg.caption or ""

    match = TERABOX_REGEX.search(text)
    if not match:
        log.info("TeraBox URL nahi mili, skip kar raha hun.")
        return

    tera_url = match.group(0)
    log.info(f"🔗 TeraBox URL mili: {tera_url}")

    catbox_link = None
    if isinstance(msg.media, MessageMediaPhoto):
        log.info("📸 Image download kar raha hun...")
        img_bytes = await client.download_media(msg.media, bytes)
        log.info("⬆️ Catbox pe upload kar raha hun...")
        catbox_link = await upload_to_catbox(img_bytes, filename="cover.jpg")
        if catbox_link:
            log.info(f"✅ Catbox link: {catbox_link}")
    else:
        log.warning("⚠️ Is post mein image nahi hai.")

    tera_video_msg = await get_video_from_tera_bot(tera_url)
    if not tera_video_msg:
        log.error("❌ Video nahi mila, abort kar raha hun.")
        return

    log.info("📤 Channel B pe video forward kar raha hun...")
    channel_b_entity = await client.get_entity(CHANNEL_B)
    forwarded_msg = await client.forward_messages(
        entity=channel_b_entity,
        messages=tera_video_msg,
    )
    log.info(f"✅ Channel B pe forward hua — Message ID: {forwarded_msg.id}")

    stream_link = await get_stream_link_from_bot(forwarded_msg)

    log.info("💾 Channel C pe links save kar raha hun...")
    channel_c_entity = await client.get_entity(CHANNEL_C)

    lines = []
    if catbox_link:
        lines.append(f"🖼 **Cover:** {catbox_link}")
    if stream_link:
        lines.append(f"▶️ **Stream:** {stream_link}")

    channel_b_full = await client.get_entity(CHANNEL_B)
    b_username = getattr(channel_b_full, "username", None)
    if b_username:
        lines.append(f"📁 **Post:** https://t.me/{b_username}/{forwarded_msg.id}")

    if not lines:
        log.error("❌ Koi link nahi bana.")
        return

    await client.send_message(channel_c_entity, "\n".join(lines), parse_mode="md")
    log.info("🎉 Done! Sab links Channel C pe save ho gaye.")


async def main():
    log.info("🚀 User bot start ho raha hai...")
    await client.start()
    log.info(f"✅ Channel A sun raha hun: {CHANNEL_A}")
    log.info("⏳ Messages ka wait kar raha hun... (bot running)")
    try:
        await client.run_until_disconnected()
    except Exception as e:
        log.error(f"❌ Bot crash hua: {e}")
        raise


if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            log.error(f"❌ Restarting after error: {e}")
            time.sleep(5)
