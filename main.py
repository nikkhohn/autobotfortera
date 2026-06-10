"""
Telegram Auto-Bot — Main Orchestrator
Telethon (user account) use karta hai:
1. Channel A monitor karo — image + TeraBox URL dhundo
2. Image → Catbox.moe upload
3. TeraBox URL → TeraBox Bot → Video file
4. Video → Channel B forward
5. Video → Stream Bot forward → Stream link
6. Catbox link + Stream link → Channel C save
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

# ── Credentials (.env se) ─────────────────────────────────────
API_ID       = int(os.getenv("TG_API_ID"))
API_HASH     = os.getenv("TG_API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")  # Railway pe yeh use hoga

def parse_channel(val):
    """@username as-is, numeric ID as int."""
    if val and val.lstrip("-").isdigit():
        return int(val)
    return val

CHANNEL_A    = parse_channel(os.getenv("CHANNEL_A"))
CHANNEL_B    = parse_channel(os.getenv("CHANNEL_B"))
CHANNEL_C    = parse_channel(os.getenv("CHANNEL_C"))
TERA_BOT     = os.getenv("TERA_BOT")    # @username of TeraBox bot
STREAM_BOT   = os.getenv("STREAM_BOT")  # @username of Stream bot

# TeraBox URL pattern — sabhi domains cover karta hai
TERABOX_REGEX = re.compile(
    r"https?://(?:www\.)?(?:terabox|1024terabox|terafileshare|freeterabox|"
    r"4funbox|teraboxapp|mirrobox|nephobox|momerybox|tibibox|"
    r"gibibox|qrubox|jobespinas)\.(?:com|net|app)/[^\s]+",
    re.IGNORECASE
)

# ── Single Telethon User Client ───────────────────────────────
# Railway pe SESSION_STRING env variable se chalega
# Local pe pehli baar generate_session.py se string banao
session = StringSession(SESSION_STRING) if SESSION_STRING else StringSession()
client = TelegramClient(session, API_ID, API_HASH)


# ── Helper: TeraBox bot se video lo ──────────────────────────
async def get_video_from_tera_bot(tera_url: str):
    """
    TeraBox bot ko URL bhejo, video reply ka wait karo (max 3 min).
    Returns Telethon Message object ya None.
    """
    log.info(f"TeraBox bot ko URL bhej raha hun: {tera_url}")
    tera_entity = await client.get_entity(TERA_BOT)
    await client.send_message(tera_entity, tera_url)

    for attempt in range(36):  # 36 × 5s = 3 min
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


# ── Helper: Stream bot se link lo ────────────────────────────
async def get_stream_link_from_bot(video_msg) -> str | None:
    """
    Channel B pe forward kiye gaye video ko Stream bot ko bhi forward karo.
    Stream bot ka text reply (link) return karo.
    """
    log.info("Stream bot ko video forward kar raha hun...")
    stream_entity = await client.get_entity(STREAM_BOT)

    await client.forward_messages(
        entity=stream_entity,
        messages=video_msg,
    )

    for attempt in range(24):  # 24 × 5s = 2 min
        await asyncio.sleep(5)
        messages = await client.get_messages(stream_entity, limit=3)
        for msg in messages:
            if msg.text and ("http" in msg.text or "https" in msg.text):
                log.info(f"✅ Stream link mila: {msg.text.strip()}")
                return msg.text.strip()
        log.info(f"Stream bot ka wait kar raha hun... ({attempt + 1}/24)")

    log.error("❌ Stream bot ne time pe link nahi diya.")
    return None


# ── Main Event Handler ────────────────────────────────────────
@client.on(events.NewMessage(chats=CHANNEL_A))
async def handle_new_post(event):
    msg = event.message
    text = msg.text or msg.caption or ""

    # 1. TeraBox URL dhundo
    match = TERABOX_REGEX.search(text)
    if not match:
        log.info("TeraBox URL nahi mili, skip kar raha hun.")
        return

    tera_url = match.group(0)
    log.info(f"🔗 TeraBox URL mili: {tera_url}")

    # 2. Image catbox pe upload karo (parallel task)
    catbox_link = None
    if isinstance(msg.media, MessageMediaPhoto):
        log.info("📸 Image download kar raha hun...")
        img_bytes = await client.download_media(msg.media, bytes)
        log.info("⬆️ Catbox pe upload kar raha hun...")
        catbox_link = await upload_to_catbox(img_bytes, filename="cover.jpg")
        if catbox_link:
            log.info(f"✅ Catbox link: {catbox_link}")
        else:
            log.warning("⚠️ Catbox upload fail hua.")
    else:
        log.warning("⚠️ Is post mein image nahi hai.")

    # 3. TeraBox bot se video lo
    tera_video_msg = await get_video_from_tera_bot(tera_url)
    if not tera_video_msg:
        log.error("❌ Video nahi mila, abort kar raha hun.")
        return

    # 4. Video → Channel B forward karo
    log.info("📤 Channel B pe video forward kar raha hun...")
    channel_b_entity = await client.get_entity(CHANNEL_B)
    forwarded_msg = await client.forward_messages(
        entity=channel_b_entity,
        messages=tera_video_msg,
    )
    log.info(f"✅ Channel B pe forward hua — Message ID: {forwarded_msg.id}")

    # 5. Usi forwarded message ko Stream bot ko bhejo → link lo
    stream_link = await get_stream_link_from_bot(forwarded_msg)

    # 6. Catbox + Stream link → Channel C pe save karo
    log.info("💾 Channel C pe links save kar raha hun...")
    channel_c_entity = await client.get_entity(CHANNEL_C)

    lines = []
    if catbox_link:
        lines.append(f"🖼 **Cover:** {catbox_link}")
    if stream_link:
        lines.append(f"▶️ **Stream:** {stream_link}")

    # Channel B post ka direct link bhi add karo
    channel_b_full = await client.get_entity(CHANNEL_B)
    b_username = getattr(channel_b_full, "username", None)
    if b_username:
        lines.append(f"📁 **Post:** https://t.me/{b_username}/{forwarded_msg.id}")

    if not lines:
        log.error("❌ Koi link nahi bana, Channel C pe kuch nahi bheja.")
        return

    await client.send_message(channel_c_entity, "\n".join(lines), parse_mode="md")
    log.info("🎉 Done! Sab links Channel C pe save ho gaye.")


# ── Entry Point ───────────────────────────────────────────────
async def main():
    log.info("🚀 User bot start ho raha hai...")
    await client.start()
    log.info(f"✅ Channel A sun raha hun: {CHANNEL_A}")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
