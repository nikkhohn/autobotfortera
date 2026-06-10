# Telegram Auto-Bot 🤖

Channel A pe image + TeraBox URL aaye → automatically process karo → Channel C pe links save karo.

## Flow
```
Channel A (source post)
    ↓
Image → Catbox.moe
TeraBox URL → TeraBox Bot → Video
    ↓
Video → Channel B (forward)
Video → Stream Bot → Stream Link
    ↓
Catbox Link + Stream Link → Channel C
```

## Setup

### Step 1 — Telegram API credentials lo
1. https://my.telegram.org pe jao
2. "API development tools" click karo
3. `API_ID` aur `API_HASH` copy karo

### Step 2 — .env file banao
```bash
cp .env.example .env
# Ab .env file mein apni values bharo
```

### Step 3 — Local test karo
```bash
pip install -r requirements.txt
python main.py
# Phone number dalo → OTP dalo → Login ho jaoge
# Session file ban jaayegi: userbot_session.session
```

### Step 4 — Railway pe deploy karo
1. https://railway.app pe jao → New Project → Deploy from GitHub
2. Apna repo connect karo
3. **Variables** tab mein saari `.env` values dalo:
   - `TG_API_ID`
   - `TG_API_HASH`
   - `CHANNEL_A`
   - `CHANNEL_B`
   - `CHANNEL_C`
   - `TERA_BOT`
   - `STREAM_BOT`
4. **Session file problem:** Railway pe pehli baar OTP nahi de sakte.
   → Pehle local pe ek baar `python main.py` chalao
   → `userbot_session.session` file ban jaayegi
   → Is file ko Railway pe upload karo (Volume mount ya base64 trick — neeche dekho)

### Session file Railway pe kaise daalo?

**Tarika (base64):**
```bash
# Local pe chalao:
python -c "import base64; print(base64.b64encode(open('userbot_session.session','rb').read()).decode())"
# Output copy karo → Railway mein SESSION_BASE64 variable mein daalo
```

Phir `main.py` ke top mein yeh add karo:
```python
import base64, os
b64 = os.getenv("SESSION_BASE64")
if b64:
    with open("userbot_session.session", "wb") as f:
        f.write(base64.b64decode(b64))
```

## Files
| File | Kaam |
|------|------|
| `main.py` | Main bot logic |
| `catbox.py` | Catbox.moe upload helper |
| `requirements.txt` | Python dependencies |
| `railway.toml` | Railway deploy config |
| `.env.example` | Environment variables template |

## Important Notes
- Bot ko **Channel A ka admin** banana zaroori hai (read access ke liye)
- Bot ko **Channel B aur C ka admin** banana zaroori hai (post karne ke liye)
- TeraBox bot aur Stream bot se **pehle khud ek baar baat karo** (start karo) taaki Telethon unhe access kar sake
