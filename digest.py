#!/usr/bin/env python3
"""
Saloni's Daily Digest
─────────────────────
Fetches RSS headlines, summarises them with Gemini AI, pulls live market
data, generates a beautiful HTML dashboard, and sends a quick email summary.

Usage:
    python digest.py           # full run
    python digest.py --no-email    # skip email
    python digest.py --no-browser  # skip opening browser
"""

import os
import re
import sys
import smtplib
import webbrowser
import datetime
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
import feedparser
import requests

# ── optional heavy imports ──────────────────────────────
try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from google import genai as genai_sdk
except ImportError:
    genai_sdk = None

# ══════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════
load_dotenv()

GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
GMAIL_USER         = os.getenv("GMAIL_USER", "salonidas.work@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL    = os.getenv("RECIPIENT_EMAIL", "salonidas.work@gmail.com")

OWNER_NAME    = "Saloni"
DIGEST_TITLE  = "Saloni's Daily Digest"
OUTPUT_HTML   = Path(__file__).parent / "dashboard.html"
GEMINI_MODEL  = "gemini-2.5-flash"

MAX_PER_FEED     = 5
MAX_PER_CATEGORY = 20

# default timeout for all HTTP requests
socket.setdefaulttimeout(12)
RSS_HEADERS = {"User-Agent": "SaloniDailyDigest/1.0 (+personal-news-aggregator)"}

# ══════════════════════════════════════════════════════════
# RSS FEEDS
# ══════════════════════════════════════════════════════════
RSS_FEEDS = {
    "finance": [
        ("CNBC",              "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("MarketWatch",       "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ("BBC Business",      "http://feeds.bbci.co.uk/news/business/rss.xml"),
        ("Guardian Business", "https://www.theguardian.com/uk/business/rss"),
        ("Economic Times",    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
        ("Pulse by Zerodha",  "https://pulse.zerodha.com/feed"),
        ("Financial Express", "https://www.financialexpress.com/market/feed/"),
        ("Yahoo Finance",     "https://finance.yahoo.com/news/rssindex"),
        ("Axios",             "https://api.axios.com/feed/"),
    ],
    "geopolitics": [
        ("NPR World",           "https://feeds.npr.org/1004/rss.xml"),
        ("Foreign Policy",      "https://foreignpolicy.com/feed/"),
        ("Deutsche Welle",      "https://rss.dw.com/xml/rss-en-world"),
        ("Times of India",      "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms"),
        ("The Hindu Intl",      "https://www.thehindu.com/news/international/feeder/default.rss"),
        ("Hindustan Times",     "https://www.hindustantimes.com/rss/world/rssfeed.xml"),
    ],
    "tech": [
        ("Hacker News",  "https://hnrss.org/frontpage"),
        ("TechCrunch",   "https://techcrunch.com/feed/"),
        ("The Verge",    "https://www.theverge.com/rss/index.xml"),
        ("Wired",        "https://www.wired.com/feed/rss"),
    ],
    "india": [
        ("Times of India",  "https://timesofindia.indiatimes.com/rssfeeds/1221656.cms"),
        ("The Hindu",       "https://www.thehindu.com/news/national/feeder/default.rss"),
        ("The Wire",        "https://thewire.in/rss"),
        ("Hindustan Times", "https://www.hindustantimes.com/rss/india/rssfeed.xml"),
    ],
}

# ══════════════════════════════════════════════════════════
# SPANISH LESSONS  — 15 themes, rotating by day of year
# ══════════════════════════════════════════════════════════
SPANISH_THEMES = [
    {
        "theme": "Greetings & Introductions",
        "roadmap": "A1 Beginner — Your very first steps. Master the art of saying hello and actually meaning it.",
        "phrases": [
            ("Hola, ¿cómo estás?",    "Hello, how are you?",          "OH-lah, KOH-moh es-TAHS"),
            ("Me llamo Saloni.",        "My name is Saloni.",           "Meh YAH-moh Saloni"),
            ("Mucho gusto.",            "Nice to meet you.",            "MOO-choh GOOS-toh"),
            ("¿De dónde eres?",        "Where are you from?",          "Deh DON-deh EH-rehs"),
            ("Soy de la India.",        "I am from India.",             "Soy deh lah EEN-dyah"),
        ],
    },
    {
        "theme": "Café & Food",
        "roadmap": "A1 Beginner — Survive your first tapas bar. The phrases that actually matter.",
        "phrases": [
            ("Un café solo, por favor.",   "A black coffee, please.",        "Oon kah-FEH SOH-loh, por fah-VOR"),
            ("¿Qué recomiendas?",          "What do you recommend?",         "Keh reh-koh-MYEHN-dahs"),
            ("La cuenta, por favor.",      "The bill, please.",              "Lah KWEHN-tah, por fah-VOR"),
            ("Está delicioso.",            "It's delicious.",                "Es-TAH deh-lee-SYOH-soh"),
            ("¿Hay algo vegetariano?",     "Is there anything vegetarian?",  "Ay AL-goh beh-heh-tah-RYAH-noh"),
        ],
    },
    {
        "theme": "Travel & Directions",
        "roadmap": "A2 Elementary — Navigate airports, metros, and cobblestone streets with confidence.",
        "phrases": [
            ("¿Dónde está el aeropuerto?",  "Where is the airport?",          "DON-deh es-TAH el ah-eh-ro-PWER-toh"),
            ("Gira a la izquierda.",         "Turn left.",                     "HEE-rah ah lah ees-KYEHR-dah"),
            ("¿Cuánto cuesta el billete?",   "How much is the ticket?",        "KWAHN-toh KWES-tah el bee-YEH-teh"),
            ("Quiero ir a Barcelona.",       "I want to go to Barcelona.",     "KYEH-roh eer ah Bar-seh-LOH-nah"),
            ("Me he perdido.",               "I'm lost.",                      "Meh eh pehr-DEE-doh"),
        ],
    },
    {
        "theme": "Work & Business",
        "roadmap": "A2 Elementary — Spanish for the professional world. Meetings, deadlines, small talk.",
        "phrases": [
            ("Tengo una reunión.",          "I have a meeting.",             "TEHN-goh OO-nah reh-oo-NYOHN"),
            ("¿Cuál es el plazo?",          "What's the deadline?",          "Kwahl es el PLAH-soh"),
            ("Trabajo desde casa.",         "I work from home.",             "Trah-BAH-hoh DES-deh KAH-sah"),
            ("Necesito más tiempo.",        "I need more time.",             "Neh-seh-SEE-toh mahs TYEHM-poh"),
            ("El proyecto va bien.",        "The project is going well.",    "El pro-YEHK-toh bah BYEHN"),
        ],
    },
    {
        "theme": "Finance & Markets",
        "roadmap": "B1 Intermediate — Discuss money and markets in Spanish. Handy for global finance conversations.",
        "phrases": [
            ("Las acciones han subido.",          "Stocks have gone up.",             "Lahs ak-SYOH-nehs ahn soo-BEE-doh"),
            ("¿Cuál es el tipo de cambio?",       "What's the exchange rate?",        "Kwahl es el TEE-poh deh KAHM-byoh"),
            ("Quiero invertir a largo plazo.",    "I want to invest long-term.",      "KYEH-roh een-vehr-TEER ah LAR-goh PLAH-soh"),
            ("El mercado está volátil.",          "The market is volatile.",          "El mehr-KAH-doh es-TAH boh-LAH-teel"),
            ("Ahorra para el futuro.",            "Save for the future.",             "Ah-OH-rrah PAH-rah el foo-TOO-roh"),
        ],
    },
    {
        "theme": "Technology & Innovation",
        "roadmap": "B1 Intermediate — Tech vocabulary for the digital age. Impress Spanish engineers at conferences.",
        "phrases": [
            ("¿Tienes WiFi?",                        "Do you have WiFi?",                    "TYEH-nehs WEE-fee"),
            ("La batería está baja.",                "The battery is low.",                  "Lah bah-teh-REE-ah es-TAH BAH-hah"),
            ("¿Puedes enviarme el enlace?",          "Can you send me the link?",            "PWEH-dehs en-BYAR-meh el en-LAH-seh"),
            ("La IA está cambiando todo.",           "AI is changing everything.",           "Lah ee-AH es-TAH kahm-BYAHN-doh TOH-doh"),
            ("Necesito actualizar el software.",     "I need to update the software.",       "Neh-seh-SEE-toh ak-too-ah-lee-SAR el SOFT-wehr"),
        ],
    },
    {
        "theme": "Emotions & Wellbeing",
        "roadmap": "B1 Intermediate — Express your inner world in Spanish. Essential for genuine human connection.",
        "phrases": [
            ("Estoy muy emocionada.",         "I'm very excited.",                   "Es-TOY mwee eh-moh-syoh-NAH-dah"),
            ("Me siento abrumada.",           "I feel overwhelmed.",                 "Meh SYEHN-toh ah-broo-MAH-dah"),
            ("Necesito un descanso.",         "I need a break.",                     "Neh-seh-SEE-toh oon des-KAHN-soh"),
            ("Todo va a salir bien.",         "Everything is going to work out.",    "TOH-doh bah ah sah-LEER BYEHN"),
            ("Me alegra mucho verte.",        "I'm so glad to see you.",             "Meh ah-LEH-grah MOO-choh BEHR-teh"),
        ],
    },
    {
        "theme": "Current Events & News",
        "roadmap": "B2 Upper Intermediate — Discuss global affairs. Read El País, watch Telemundo, debate boldly.",
        "phrases": [
            ("¿Has leído las noticias hoy?",            "Have you read the news today?",          "Ahs leh-EE-doh lahs noh-TEE-syahs oy"),
            ("El mundo está cambiando rápidamente.",    "The world is changing rapidly.",         "El MOON-doh es-TAH kahm-BYAHN-doh RAH-pee-dah-MEHN-teh"),
            ("La situación es preocupante.",             "The situation is worrying.",             "Lah see-twah-SYOHN es preh-oh-koo-PAHN-teh"),
            ("Hay que estar bien informado.",            "One must stay well-informed.",           "Ay keh es-TAR byehn een-for-MAH-doh"),
            ("¿Cuál es tu opinión sobre esto?",         "What's your opinion on this?",           "Kwahl es too oh-pee-NYOHN SOH-breh ES-toh"),
        ],
    },
    {
        "theme": "Shopping & Negotiation",
        "roadmap": "B2 Upper Intermediate — Haggle, browse, and splurge in Spanish markets. Works equally well in LATAM.",
        "phrases": [
            ("¿Cuánto cuesta esto?",                                    "How much does this cost?",         "KWAHN-toh KWES-tah ES-toh"),
            ("Es demasiado caro. ¿Me puede hacer un descuento?",       "It's too expensive. Can you give me a discount?",  "Es deh-mah-SYAH-doh KAH-roh. Meh PWEH-deh ah-SER oon des-KWEHN-toh"),
            ("Me lo llevo.",                                            "I'll take it.",                    "Meh loh YEH-boh"),
            ("¿Aceptan tarjeta de crédito?",                           "Do you accept credit card?",       "Ah-SEP-tahn tar-HEH-tah deh KREH-dee-toh"),
            ("¿Hay algo en oferta?",                                    "Is anything on sale?",             "Ay AL-goh en oh-FEHR-tah"),
        ],
    },
    {
        "theme": "Culture & Arts",
        "roadmap": "B2 Upper Intermediate — Discuss cinema, literature, music. Connect with the soul of Spanish culture.",
        "phrases": [
            ("¿Has visto alguna película española?",    "Have you seen any Spanish films?",     "Ahs BEES-toh AL-goo-nah peh-LEE-koo-lah es-pah-NYOH-lah"),
            ("Me encanta la literatura en castellano.", "I love literature in Spanish.",        "Meh en-KAHN-tah lah lee-teh-rah-TOO-rah en kas-teh-YAH-noh"),
            ("El Prado es impresionante.",              "The Prado is impressive.",             "El PRAH-doh es eem-preh-syoh-NAHN-teh"),
            ("La música me transporta.",                "Music transports me.",                 "Lah MOO-see-kah meh trans-POR-tah"),
            ("García Márquez es mi autor favorito.",   "García Márquez is my favourite.",      "Gar-SEE-ah MAR-kes es mee ow-TOR fah-boh-REE-toh"),
        ],
    },
    {
        "theme": "Health & Lifestyle",
        "roadmap": "C1 Advanced — Medical vocabulary and lifestyle conversations. Vital for living or travelling abroad.",
        "phrases": [
            ("Necesito ver a un especialista.",                  "I need to see a specialist.",      "Neh-seh-SEE-toh behr ah oon es-peh-syah-LEES-tah"),
            ("Tengo una intolerancia alimentaria.",              "I have a food intolerance.",       "TEHN-goh OO-nah een-toh-leh-RAHN-syah ah-lee-mehn-TAH-ryah"),
            ("Hago yoga por las mañanas.",                      "I do yoga in the mornings.",       "AH-goh YOH-gah por lahs mah-NYAH-nahs"),
            ("El equilibrio trabajo-vida es clave.",             "Work-life balance is key.",        "El eh-kee-LEE-bryoh trah-BAH-hoh-BEE-dah es KLAH-beh"),
            ("Duermo ocho horas cada noche.",                    "I sleep eight hours every night.", "DWEHR-moh OH-choh OH-rahs KAH-dah NOH-cheh"),
        ],
    },
    {
        "theme": "Philosophy & Deep Conversations",
        "roadmap": "C1 Advanced — Existential Spanish. For those late-night conversations that actually matter.",
        "phrases": [
            ("¿En qué consiste una buena vida?",     "What does a good life consist of?",   "En keh kohn-SEES-teh OO-nah BWEH-nah BEE-dah"),
            ("La felicidad no se compra.",           "Happiness cannot be bought.",         "Lah feh-lee-see-DAHD noh seh KOHM-prah"),
            ("Todo cambia, nada permanece.",         "Everything changes, nothing remains.", "TOH-doh KAHM-byah, NAH-dah pehr-mah-NEH-seh"),
            ("El conocimiento es poder.",            "Knowledge is power.",                 "El koh-noh-SYEHN-toh es poh-DEHR"),
            ("Vivir es arriesgarse.",                "To live is to take risks.",           "Bee-BEER es ah-ryehs-GAR-seh"),
        ],
    },
    {
        "theme": "Weather & Nature",
        "roadmap": "C1 Advanced — Describe the natural world. Read Lorca, write postcards, appreciate the sublime.",
        "phrases": [
            ("El cielo está cubierto de nubarrones.", "The sky is covered in storm clouds.",     "El SYEH-loh es-TAH koo-BYEHR-toh deh noo-bah-ROH-nehs"),
            ("Hace un calor sofocante.",              "It's sweltering hot.",                    "AH-seh oon kah-LOR soh-foh-KAHN-teh"),
            ("El amanecer es espectacular.",          "The sunrise is spectacular.",             "El ah-mah-neh-SEHR es es-pek-tah-koo-LAR"),
            ("Disfruto los paseos por la naturaleza.","I enjoy walks in nature.",               "Dees-FROO-toh lohs pah-SEH-ohs por lah nah-too-RAH-leh-sah"),
            ("La lluvia tiene algo de melancólico.",  "Rain has something melancholic about it.","Lah YOO-byah TYEH-neh AL-goh deh meh-lahn-KOH-lee-koh"),
        ],
    },
    {
        "theme": "Relationships & Social Life",
        "roadmap": "C1 Advanced — The language of connection. Friendship, love, and everything in between.",
        "phrases": [
            ("Eres la persona más importante en mi vida.", "You're the most important person in my life.", "EH-rehs lah pehr-SOH-nah mahs eem-por-TAHN-teh en mee BEE-dah"),
            ("Hay que cuidar las amistades.",              "One must nurture friendships.",               "Ay keh kwee-DAR lahs ah-mees-TAH-dehs"),
            ("¿Quedamos para tomar algo mañana?",          "Shall we meet for drinks tomorrow?",          "Keh-DAH-mohs PAH-rah toh-MAR AL-goh mah-NYAH-nah"),
            ("Me has inspirado mucho.",                    "You've inspired me a lot.",                   "Meh ahs een-spee-RAH-doh MOO-choh"),
            ("Te deseo todo lo mejor.",                   "I wish you all the best.",                    "Teh deh-SEH-oh TOH-doh loh meh-HOR"),
        ],
    },
    {
        "theme": "Ambition & Future",
        "roadmap": "C2 Mastery — Articulate your biggest dreams and boldest visions in flawless español. You've arrived.",
        "phrases": [
            ("Tengo grandes planes para el futuro.",               "I have big plans for the future.",            "TEHN-goh GRAHN-dehs PLAH-nehs PAH-rah el foo-TOO-roh"),
            ("Nunca es demasiado tarde para empezar.",             "It's never too late to start.",               "NOON-kah es deh-mah-SYAH-doh TAR-deh PAH-rah em-peh-SAR"),
            ("Estoy construyendo algo significativo.",             "I am building something meaningful.",         "Es-TOY kohn-stroo-YEHN-doh AL-goh seeg-nee-fee-KAH-tee-boh"),
            ("El éxito es el resultado del esfuerzo sostenido.",  "Success is the result of sustained effort.",  "El EK-see-toh es el reh-soul-TAH-doh del es-FWEHR-soh sohs-teh-NEE-doh"),
            ("Cada día me acerco más a mis metas.",               "Each day I get closer to my goals.",          "KAH-dah DEE-ah meh ah-SEHR-koh mahs ah mees MEH-tahs"),
        ],
    },
]

# ══════════════════════════════════════════════════════════
# TERMINAL LOGGING
# ══════════════════════════════════════════════════════════
def log(msg, symbol="▸"):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"  {symbol}  [{ts}]  {msg}")

def log_section(title):
    print(f"\n{'─' * 62}")
    print(f"  {title}")
    print(f"{'─' * 62}")

# ══════════════════════════════════════════════════════════
# RSS FETCHING
# ══════════════════════════════════════════════════════════
def fetch_rss_articles():
    """Fetch articles from all RSS feeds, grouped by category."""
    all_articles = {}
    for category, feeds in RSS_FEEDS.items():
        log_section(f"RSS › {category.upper()}")
        cat_articles = []
        for source, url in feeds:
            try:
                resp = requests.get(url, headers=RSS_HEADERS, timeout=12)
                feed = feedparser.parse(resp.content)
                count = 0
                for entry in feed.entries[:MAX_PER_FEED]:
                    title   = entry.get("title", "").strip()
                    summary = entry.get("summary", entry.get("description", "")).strip()
                    summary = re.sub(r"<[^>]+>", "", summary)[:300]
                    link    = entry.get("link", "")
                    if title:
                        cat_articles.append({
                            "source": source,
                            "title":  title,
                            "summary": summary,
                            "link":   link,
                        })
                        count += 1
                log(f"{source}: {count} articles")
            except Exception as exc:
                log(f"{source}: failed — {exc}", "✗")
        all_articles[category] = cat_articles[:MAX_PER_CATEGORY]
        log(f"Total {category}: {len(all_articles[category])} articles", "✓")
    return all_articles

# ══════════════════════════════════════════════════════════
# MARKET DATA
# ══════════════════════════════════════════════════════════
def fetch_market_data():
    """Fetch Nifty 50, Sensex, S&P 500 (Yahoo Finance) and Bitcoin (CoinGecko)."""
    log_section("MARKET DATA")
    markets = {}

    def get_yahoo(symbol, label):
        try:
            if yf is None:
                raise ImportError("yfinance not installed")
            ticker = yf.Ticker(symbol)
            hist   = ticker.history(period="5d")
            if len(hist) >= 2:
                price      = float(hist["Close"].iloc[-1])
                prev       = float(hist["Close"].iloc[-2])
                chg        = price - prev
                chg_pct    = (chg / prev) * 100
                return {
                    "label": label, "symbol": symbol,
                    "price": f"{price:,.2f}", "change": chg_pct,
                    "change_str": f"{chg_pct:+.2f}%",
                    "up": chg_pct >= 0, "error": False,
                }
            raise ValueError("Not enough history")
        except Exception as exc:
            log(f"{label} failed — {exc}", "✗")
            return {"label": label, "symbol": symbol, "price": "N/A", "change": 0, "error": True}

    markets["nifty"]  = get_yahoo("^NSEI",  "Nifty 50")
    markets["sensex"] = get_yahoo("^BSESN", "Sensex")
    markets["sp500"]  = get_yahoo("^GSPC",  "S&P 500")

    # Bitcoin via CoinGecko free API
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd", "include_24hr_change": "true"},
            timeout=10,
        )
        data      = resp.json()
        btc_price = data["bitcoin"]["usd"]
        btc_chg   = data["bitcoin"]["usd_24h_change"]
        markets["bitcoin"] = {
            "label": "Bitcoin", "symbol": "BTC",
            "price": f"{btc_price:,.0f}", "prefix": "$",
            "change": btc_chg, "change_str": f"{btc_chg:+.2f}%",
            "up": btc_chg >= 0, "error": False,
        }
        log(f"Bitcoin: ${btc_price:,.0f} ({btc_chg:+.2f}%)")
    except Exception as exc:
        log(f"Bitcoin failed — {exc}", "✗")
        markets["bitcoin"] = {"label": "Bitcoin", "symbol": "BTC", "price": "N/A", "change": 0, "error": True}

    for key in ("nifty", "sensex", "sp500"):
        m = markets[key]
        if not m["error"]:
            log(f"{m['label']}: {m['price']} ({m['change_str']})")

    return markets

# ══════════════════════════════════════════════════════════
# GEMINI AI DIGEST
# ══════════════════════════════════════════════════════════
_SECTION_LABELS = {
    "finance":    "FINANCE & MARKETS",
    "geopolitics":"GEOPOLITICS & WORLD AFFAIRS",
    "tech":       "TECHNOLOGY",
    "india":      "INDIA",
}

_GEMINI_PROMPT = """\
You are a sharp, witty friend who actually reads the news — someone who went to business school,
studied international relations, worked at a tech startup, and genuinely cares about the world.
You're writing {owner}'s personal morning digest. Be smart, opinionated, occasionally funny.
No hedging. No corporate-speak. Write like you're messaging your most brilliant friend.

Use EXACTLY these section headers (on their own line, with the ### markers):

### MONEY TALK ###
### WORLD LORE ###
### TECH TEA ###
### INDIA LOW-DOWN ###
### SPEED ROUND ###

Guidelines per section:
- MONEY TALK: 4-5 finance/market stories. What do they mean for Indian investors, global markets,
  everyday life? Connect the dots between stories.
- WORLD LORE: 4-5 geopolitical stories. Name the players, explain the stakes, take a clear view.
- TECH TEA: 3-4 tech stories. Be skeptical of hype. Highlight genuine signal vs. PR noise.
- INDIA LOW-DOWN: 4-5 India stories across politics, business, culture, or society. Speak plainly.
- SPEED ROUND: 7-8 punchy one-liners on remaining stories. Each starts with a relevant emoji,
  one story per line, max 30 words each.

Use markdown freely: **bold** for key terms, bullet points for lists. Each main section should be
200-300 words. Speed Round is bullets only.

Today's articles:
{articles}"""

def _build_article_text(all_articles):
    blocks = []
    for cat, articles in all_articles.items():
        blocks.append(f"\n\n{'=' * 52}")
        blocks.append(f"CATEGORY: {_SECTION_LABELS.get(cat, cat.upper())}")
        blocks.append("=" * 52)
        for i, a in enumerate(articles, 1):
            blocks.append(f"\n[{i}] [{a['source']}] {a['title']}")
            if a.get("summary"):
                blocks.append(f"    {a['summary'][:220]}")
    return "\n".join(blocks)

def _placeholder_digest():
    return """\
### MONEY TALK ###
**Your Gemini API key isn't configured yet** — but the RSS feeds are live and pulling fresh headlines!
Add `GEMINI_API_KEY` to your `.env` file to unlock the full AI digest.

- Get a free key at **https://aistudio.google.com**
- Copy `.env.example` to `.env` and fill in your key
- Re-run `python digest.py`

Markets are moving (check the ticker above), news is flowing, and your digest is almost ready.

### WORLD LORE ###
**The world isn't waiting** — your RSS feeds are pulling from NPR World, Foreign Policy, Deutsche Welle,
The Hindu, and Hindustan Times right now. Once your Gemini key is in place, you'll get sharp, opinionated
analysis of everything that matters geopolitically.

### TECH TEA ###
**Hacker News, TechCrunch, The Verge, and Wired** are all in the pipeline. Your AI tech commentator
is one `.env` setting away from separating genuine breakthroughs from the usual hype cycle.

### INDIA LOW-DOWN ###
**Times of India, The Hindu, The Wire, and Hindustan Times** are feeding in. India-specific context
and commentary will flow once Gemini is configured.

### SPEED ROUND ###
🔑 Get your free Gemini API key at aistudio.google.com
📝 Copy .env.example → .env and add your key
🚀 Re-run python digest.py to get the full experience
📰 All RSS feeds are live — headlines are fresh
📈 Market data is pulled from Yahoo Finance + CoinGecko
🇪🇸 Your Spanish lesson below is already rotating daily
☕ In the meantime, the dashboard looks beautiful regardless"""

def get_ai_digest(all_articles):
    """Send articles to Gemini and return the raw digest text."""
    log_section("GEMINI AI DIGEST")

    if not GEMINI_API_KEY:
        log("GEMINI_API_KEY not set — using placeholder content.", "!")
        return _placeholder_digest()

    if genai_sdk is None:
        log("google-genai not installed — using placeholder.", "!")
        return _placeholder_digest()

    article_text = _build_article_text(all_articles)
    prompt       = _GEMINI_PROMPT.format(owner=OWNER_NAME, articles=article_text)

    try:
        client   = genai_sdk.Client(api_key=GEMINI_API_KEY)
        log(f"Sending {len(article_text):,} chars to {GEMINI_MODEL}…")
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        digest   = response.text
        log(f"Received {len(digest):,} chars from Gemini", "✓")
        return digest
    except Exception as exc:
        log(f"Gemini request failed — {exc}", "✗")
        return _placeholder_digest()

# ══════════════════════════════════════════════════════════
# SECTION PARSER
# ══════════════════════════════════════════════════════════
_SECTION_KEYS = {
    "MONEY TALK":     "money",
    "WORLD LORE":     "world",
    "TECH TEA":       "tech",
    "INDIA LOW-DOWN": "india",
    "SPEED ROUND":    "speed",
}

def parse_sections(digest_text):
    sections = {v: "" for v in _SECTION_KEYS.values()}
    pattern  = r"###\s*(" + "|".join(re.escape(k) for k in _SECTION_KEYS) + r")\s*###"
    parts    = re.split(pattern, digest_text)
    i = 1
    while i < len(parts) - 1:
        key  = parts[i].strip()
        body = parts[i + 1].strip()
        slug = _SECTION_KEYS.get(key)
        if slug:
            sections[slug] = body
        i += 2
    return sections

# ══════════════════════════════════════════════════════════
# SPANISH LESSON
# ══════════════════════════════════════════════════════════
def get_spanish_lesson():
    day_of_year = datetime.datetime.now().timetuple().tm_yday
    idx         = (day_of_year - 1) % len(SPANISH_THEMES)
    lesson      = dict(SPANISH_THEMES[idx])
    lesson["index"] = idx + 1
    lesson["total"] = len(SPANISH_THEMES)
    return lesson

# ══════════════════════════════════════════════════════════
# MARKDOWN → HTML  (minimal subset)
# ══════════════════════════════════════════════════════════
def md_to_html(text):
    if not text:
        return "<p><em>Content unavailable.</em></p>"

    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*",     r"<strong>\1</strong>",          text)
    text = re.sub(r"\*([^*\n]+?)\*",    r"<em>\1</em>",                  text)

    lines  = text.split("\n")
    output = []
    in_ul  = False

    for line in lines:
        s = line.strip()
        if not s:
            if in_ul:
                output.append("</ul>")
                in_ul = False
            output.append('<div class="spacer"></div>')
            continue
        if s.startswith(("- ", "• ", "* ")):
            if not in_ul:
                output.append('<ul class="digest-list">')
                in_ul = True
            output.append(f"  <li>{s[2:].strip()}</li>")
        elif re.match(r"^#{1,3}\s", s):
            if in_ul:
                output.append("</ul>")
                in_ul = False
            heading = re.sub(r"^#{1,3}\s+", "", s)
            output.append(f'<h4 class="inline-heading">{heading}</h4>')
        else:
            if in_ul:
                output.append("</ul>")
                in_ul = False
            output.append(f"<p>{s}</p>")

    if in_ul:
        output.append("</ul>")
    return "\n".join(output)

def speed_to_html(text):
    if not text:
        return "<p><em>Speed round unavailable.</em></p>"
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    items = []
    for line in lines:
        if line.startswith(("- ", "• ", "* ")):
            line = line[2:].strip()
        if line:
            items.append(f'<div class="speed-item">{line}</div>')
    return "\n".join(items) if items else "<p><em>No speed items found.</em></p>"

# ══════════════════════════════════════════════════════════
# HTML BUILDER
# ══════════════════════════════════════════════════════════
def _market_card(m, default_prefix=""):
    label  = m.get("label", "")
    if m.get("error"):
        return f"""<div class="market-card">
          <div class="market-label">{label}</div>
          <div class="market-price">N/A</div>
          <div class="market-change neutral">—</div>
        </div>"""
    color  = "gain" if m.get("up", True) else "loss"
    arrow  = "▲" if m.get("up", True) else "▼"
    prefix = m.get("prefix", default_prefix)
    return f"""<div class="market-card">
          <div class="market-label">{label}</div>
          <div class="market-price">{prefix}{m['price']}</div>
          <div class="market-change {color}">{arrow} {m.get('change_str', '')}</div>
        </div>"""

def _section_card(icon, title, slug, card_class, sections):
    body = md_to_html(sections.get(slug, ""))
    return f"""<div class="section-card {card_class}">
          <div class="section-header">
            <span class="section-icon">{icon}</span>
            <h2 class="section-title">{title}</h2>
          </div>
          <div class="section-body">{body}</div>
        </div>"""

def build_html(sections, markets, spanish, all_articles):
    now      = datetime.datetime.now()
    date_str = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%H:%M")

    ticker_html = (
        _market_card(markets.get("nifty",   {"label": "Nifty 50",  "error": True})) +
        _market_card(markets.get("sensex",  {"label": "Sensex",    "error": True})) +
        _market_card(markets.get("sp500",   {"label": "S&P 500",   "error": True})) +
        _market_card(markets.get("bitcoin", {"label": "Bitcoin",   "error": True}))
    )

    # Spanish phrases table rows
    phrase_rows = ""
    for phrase, meaning, pron in spanish["phrases"]:
        phrase_rows += f"""<tr>
              <td class="es-phrase">{phrase}</td>
              <td class="es-meaning">{meaning}</td>
              <td class="es-pron">{pron}</td>
            </tr>"""

    # Footer source credits
    all_sources = sorted({a["source"] for arts in all_articles.values() for a in arts})
    sources_txt = " · ".join(all_sources)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{DIGEST_TITLE} — {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400;1,600&family=Jost:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:         #0c0508;
    --bg-card:    #160b0e;
    --bg-card2:   #1e1014;
    --burgundy:   #7b1a2d;
    --burg-mid:   #9e2238;
    --burg-lite:  #c4365a;
    --gold:       #c9a552;
    --gold-lite:  #e0c07a;
    --cream:      #f0e8d8;
    --cream-dim:  #b0a088;
    --cream-sub:  #7a6e5e;
    --gain:       #5dbf8a;
    --loss:       #e05c5c;
    --neutral:    #888;
    --border:     rgba(201,165,82,0.16);
    --glow:       rgba(123,26,45,0.3);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--cream);
    font-family: 'Jost', sans-serif;
    font-weight: 300;
    line-height: 1.75;
    min-height: 100vh;
  }}

  /* ── HEADER ─────────────────────────────── */
  .site-header {{
    background: linear-gradient(135deg, #0c0508 0%, #1a0810 45%, #0f0307 100%);
    border-bottom: 1px solid var(--border);
    padding: 2.5rem 4rem 2rem;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    position: relative;
    overflow: hidden;
  }}
  .site-header::before {{
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 15% 60%, rgba(123,26,45,0.18) 0%, transparent 55%);
    pointer-events: none;
  }}
  .header-left {{ position: relative; }}
  .header-eyebrow {{
    font-size: 0.68rem;
    font-weight: 500;
    letter-spacing: 0.38em;
    text-transform: uppercase;
    color: var(--gold);
    margin-bottom: 0.5rem;
  }}
  .header-title {{
    font-family: 'Playfair Display', serif;
    font-size: clamp(2rem, 5vw, 3.4rem);
    font-weight: 700;
    color: var(--cream);
    line-height: 1.1;
    letter-spacing: -0.02em;
  }}
  .header-title span {{ color: var(--burg-lite); font-style: italic; }}
  .header-tagline {{
    font-size: 0.84rem;
    color: var(--cream-dim);
    margin-top: 0.55rem;
    font-style: italic;
  }}
  .header-right {{ text-align: right; position: relative; }}
  .header-date {{
    font-family: 'Playfair Display', serif;
    font-size: 1rem;
    color: var(--cream-dim);
    font-style: italic;
  }}
  .header-time {{
    font-size: 0.72rem;
    color: var(--cream-sub);
    margin-top: 0.3rem;
    letter-spacing: 0.12em;
  }}

  /* ── MARKET TICKER ───────────────────────── */
  .ticker-bar {{
    background: var(--bg-card);
    border-bottom: 1px solid var(--border);
    padding: 1.1rem 4rem;
    display: flex;
    gap: 1.2rem;
    flex-wrap: wrap;
    align-items: center;
  }}
  .ticker-label {{
    font-size: 0.64rem;
    font-weight: 600;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--cream-sub);
    margin-right: 0.5rem;
  }}
  .market-card {{
    display: flex;
    flex-direction: column;
    gap: 0.08rem;
    padding: 0.55rem 1.1rem;
    background: var(--bg-card2);
    border: 1px solid var(--border);
    border-radius: 4px;
    min-width: 108px;
  }}
  .market-label  {{ font-size: 0.63rem; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--cream-sub); }}
  .market-price  {{ font-family: 'Playfair Display', serif; font-size: 1.05rem; color: var(--cream); }}
  .market-change {{ font-size: 0.73rem; font-weight: 500; }}
  .market-change.gain    {{ color: var(--gain); }}
  .market-change.loss    {{ color: var(--loss); }}
  .market-change.neutral {{ color: var(--neutral); }}

  /* ── MAIN LAYOUT ─────────────────────────── */
  .main-wrap {{
    max-width: 1400px;
    margin: 0 auto;
    padding: 3rem 4rem;
  }}
  .section-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2rem;
    margin-bottom: 2rem;
  }}
  @media (max-width: 900px) {{
    .section-grid {{ grid-template-columns: 1fr; }}
    .site-header, .ticker-bar, .main-wrap {{ padding-left: 1.5rem; padding-right: 1.5rem; }}
  }}

  /* ── SECTION CARDS ───────────────────────── */
  .section-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    transition: box-shadow 0.3s ease;
  }}
  .section-card:hover {{ box-shadow: 0 8px 40px var(--glow); }}

  .card-finance .section-header {{ background: linear-gradient(135deg, #091a0e, #0e2314); border-bottom-color: rgba(93,191,138,0.18); }}
  .card-world .section-header   {{ background: linear-gradient(135deg, #090e1a, #0d1222); border-bottom-color: rgba(93,138,220,0.18); }}
  .card-tech .section-header    {{ background: linear-gradient(135deg, #18100a, #22160a); border-bottom-color: rgba(220,180,93,0.2);  }}
  .card-india .section-header   {{ background: linear-gradient(135deg, #1a0a0a, #220a0a); border-bottom-color: rgba(224,92,92,0.2);   }}

  .section-header {{
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.2rem 1.7rem;
    border-bottom: 1px solid var(--border);
  }}
  .section-icon  {{ font-size: 1.15rem; }}
  .section-title {{
    font-family: 'Playfair Display', serif;
    font-size: 1.05rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--cream);
  }}
  .section-body {{
    padding: 1.7rem;
    font-size: 0.9rem;
    color: var(--cream-dim);
    line-height: 1.82;
  }}
  .section-body p {{ margin-bottom: 0.85rem; }}
  .section-body p:last-child {{ margin-bottom: 0; }}
  .section-body strong {{ color: var(--cream); font-weight: 600; }}
  .section-body em {{ color: var(--gold-lite); font-style: italic; }}
  .section-body .spacer {{ height: 0.4rem; }}
  .digest-list {{ padding-left: 1.1rem; margin: 0.5rem 0 0.85rem; }}
  .digest-list li {{ margin-bottom: 0.35rem; }}
  .inline-heading {{
    font-family: 'Playfair Display', serif;
    font-size: 0.88rem;
    font-weight: 600;
    color: var(--cream);
    margin: 1rem 0 0.35rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}

  /* ── SPEED ROUND ─────────────────────────── */
  .speed-section {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 2rem;
  }}
  .speed-header {{
    background: linear-gradient(135deg, #120a18, #18102a);
    border-bottom: 1px solid rgba(196,54,90,0.18);
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.2rem 1.7rem;
  }}
  .speed-body {{ padding: 1.4rem 1.7rem; }}
  .speed-item {{
    padding: 0.58rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.045);
    font-size: 0.88rem;
    color: var(--cream-dim);
    line-height: 1.65;
  }}
  .speed-item:last-child {{ border-bottom: none; }}
  .speed-item strong {{ color: var(--cream); }}

  /* ── SPANISH SECTION ─────────────────────── */
  .spanish-section {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 2rem;
  }}
  .spanish-header {{
    background: linear-gradient(135deg, #0a100f, #0c1714);
    border-bottom: 1px solid rgba(201,165,82,0.15);
    padding: 1.2rem 1.7rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.8rem;
  }}
  .spanish-title-group {{ display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }}
  .spanish-badge {{
    font-size: 0.63rem;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--gold);
    background: rgba(201,165,82,0.1);
    border: 1px solid rgba(201,165,82,0.2);
    padding: 0.22rem 0.65rem;
    border-radius: 3px;
  }}
  .spanish-counter {{ font-size: 0.72rem; color: var(--cream-sub); }}
  .spanish-body {{ padding: 1.7rem; }}
  .spanish-roadmap {{
    font-size: 0.82rem;
    color: var(--gold);
    background: rgba(201,165,82,0.07);
    border-left: 3px solid var(--gold);
    padding: 0.65rem 1rem;
    border-radius: 0 4px 4px 0;
    margin-bottom: 1.5rem;
    font-style: italic;
  }}
  .phrase-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.87rem;
  }}
  .phrase-table th {{
    text-align: left;
    font-size: 0.63rem;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--cream-sub);
    padding: 0 0 0.7rem;
    border-bottom: 1px solid var(--border);
  }}
  .phrase-table tr {{ border-bottom: 1px solid rgba(255,255,255,0.04); }}
  .phrase-table tr:last-child {{ border-bottom: none; }}
  .es-phrase  {{
    font-family: 'Playfair Display', serif;
    font-style: italic;
    color: var(--cream);
    padding: 0.7rem 1.2rem 0.7rem 0;
    font-size: 0.95rem;
    vertical-align: top;
    width: 35%;
  }}
  .es-meaning {{
    color: var(--cream-dim);
    padding: 0.7rem 1.2rem 0.7rem 0;
    vertical-align: top;
    width: 35%;
  }}
  .es-pron {{
    color: var(--gold);
    font-size: 0.78rem;
    padding: 0.7rem 0;
    vertical-align: top;
    width: 30%;
    font-style: italic;
  }}

  /* ── FOOTER ──────────────────────────────── */
  .site-footer {{
    border-top: 1px solid var(--border);
    padding: 1.8rem 4rem;
    text-align: center;
    color: var(--cream-sub);
    font-size: 0.73rem;
    line-height: 1.9;
  }}
  .footer-sources {{ max-width: 900px; margin: 0 auto 0.4rem; }}
  .footer-tag {{
    font-family: 'Playfair Display', serif;
    font-style: italic;
    color: var(--cream-dim);
    font-size: 0.78rem;
  }}

  /* ── SCROLLBAR ───────────────────────────── */
  ::-webkit-scrollbar {{ width: 5px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--burgundy); border-radius: 3px; }}
</style>
</head>
<body>

<!-- HEADER -->
<header class="site-header">
  <div class="header-left">
    <p class="header-eyebrow">Your morning brief</p>
    <h1 class="header-title">{OWNER_NAME}'s <span>Daily</span> Digest</h1>
    <p class="header-tagline">Served sharp. No fluff. Just the world as it is.</p>
  </div>
  <div class="header-right">
    <div class="header-date">{date_str}</div>
    <div class="header-time">Generated at {time_str}</div>
  </div>
</header>

<!-- MARKET TICKER -->
<div class="ticker-bar">
  <div class="ticker-label">Markets</div>
  {ticker_html}
</div>

<!-- MAIN CONTENT -->
<main class="main-wrap">

  <div class="section-grid">
    {_section_card("$",  "Money Talk",      "money", "card-finance", sections)}
    {_section_card("🌐", "World Lore",      "world", "card-world",   sections)}
  </div>

  <div class="section-grid">
    {_section_card("⚡", "Tech Tea",        "tech",  "card-tech",    sections)}
    {_section_card("🇮🇳", "India Low-Down", "india", "card-india",   sections)}
  </div>

  <!-- SPEED ROUND -->
  <div class="speed-section">
    <div class="speed-header">
      <span class="section-icon">⚡</span>
      <h2 class="section-title">Speed Round</h2>
    </div>
    <div class="speed-body">
      {speed_to_html(sections.get("speed", ""))}
    </div>
  </div>

  <!-- SPANISH LESSON -->
  <div class="spanish-section">
    <div class="spanish-header">
      <div class="spanish-title-group">
        <span class="section-icon">🇪🇸</span>
        <h2 class="section-title">Hoy Aprenderás Español</h2>
        <div class="spanish-badge">{spanish['theme']}</div>
      </div>
      <div class="spanish-counter">Theme {spanish['index']} of {spanish['total']}</div>
    </div>
    <div class="spanish-body">
      <div class="spanish-roadmap">📍 {spanish['roadmap']}</div>
      <table class="phrase-table">
        <thead>
          <tr>
            <th>En español</th>
            <th>In English</th>
            <th>Pronunciation guide</th>
          </tr>
        </thead>
        <tbody>
          {phrase_rows}
        </tbody>
      </table>
    </div>
  </div>

</main>

<!-- FOOTER -->
<footer class="site-footer">
  <div class="footer-sources">Sources · {sources_txt}</div>
  <div class="footer-tag">"{DIGEST_TITLE}" — stay curious, stay sharp.</div>
</footer>

</body>
</html>"""
    return html

# ══════════════════════════════════════════════════════════
# EMAIL SENDER
# ══════════════════════════════════════════════════════════
def send_email(sections, markets, date_str):
    log_section("EMAIL")
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        log("Gmail credentials missing — skipping email. Set GMAIL_USER and GMAIL_APP_PASSWORD in .env", "!")
        return False

    def strip_md(text, limit=500):
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
        text = text.strip()
        return (text[:limit].rsplit(" ", 1)[0] + "…") if len(text) > limit else text

    def mfmt(key, label):
        m = markets.get(key, {})
        if m.get("error"):
            return f"{label}: N/A"
        pfx = m.get("prefix", "")
        return f"{label}: {pfx}{m['price']} ({m.get('change_str', '?')})"

    def mcolor(key):
        m = markets.get(key, {})
        return "#5dbf8a" if m.get("up") else "#e05c5c"

    subj = f"{DIGEST_TITLE} — {date_str}"

    # ── plain text ──
    body_text = f"""{DIGEST_TITLE}
{date_str}
{'=' * 52}

MARKETS
{mfmt('nifty',   'Nifty 50')}
{mfmt('sensex',  'Sensex')}
{mfmt('sp500',   'S&P 500')}
{mfmt('bitcoin', 'Bitcoin')}

{'=' * 52}
MONEY TALK
{strip_md(sections.get('money', ''), 500)}

{'=' * 52}
WORLD LORE
{strip_md(sections.get('world', ''), 500)}

{'=' * 52}
TECH TEA
{strip_md(sections.get('tech', ''), 400)}

{'=' * 52}
INDIA LOW-DOWN
{strip_md(sections.get('india', ''), 400)}

{'=' * 52}
SPEED ROUND
{strip_md(sections.get('speed', ''), 500)}

{'=' * 52}
Stay curious, {OWNER_NAME}.
"""

    # ── HTML email ──
    def mrow(key, label):
        m = markets.get(key, {})
        pfx  = m.get("prefix", "")
        price = f"{pfx}{m.get('price', 'N/A')}"
        chg   = m.get("change_str", "")
        col   = mcolor(key) if not m.get("error") else "#888"
        return f"""<tr>
          <td style="padding:.28rem .9rem .28rem 0;font-size:.83rem;color:#b0a088;">{label}</td>
          <td style="font-weight:600;font-size:.9rem;">{price}</td>
          <td style="color:{col};font-size:.83rem;">{chg}</td>
        </tr>"""

    def section_blk(icon, title, slug, accent):
        content = strip_md(sections.get(slug, ""), 480)
        return f"""<div style="margin-bottom:1.4rem;">
          <h3 style="font-size:.88rem;color:{accent};text-transform:uppercase;letter-spacing:.1em;
                     border-bottom:1px solid rgba(255,255,255,.07);padding-bottom:.45rem;margin-bottom:.7rem;">
            {icon} {title}</h3>
          <p style="font-size:.86rem;color:#b0a088;line-height:1.72;">{content}</p>
        </div>"""

    body_html = f"""<html><body style="font-family:Georgia,serif;background:#0c0508;color:#f0e8d8;
        max-width:600px;margin:0 auto;padding:2rem;">
  <h2 style="color:#c9a552;font-size:1.35rem;margin-bottom:.25rem;">{DIGEST_TITLE}</h2>
  <p style="color:#7a6e5e;font-size:.82rem;margin-bottom:1.5rem;font-style:italic;">{date_str}</p>

  <div style="background:#160b0e;border:1px solid rgba(201,165,82,.18);border-radius:6px;
              padding:.9rem 1.3rem;margin-bottom:1.5rem;">
    <p style="font-size:.62rem;letter-spacing:.2em;text-transform:uppercase;color:#7a6e5e;margin-bottom:.7rem;">
      Markets</p>
    <table style="width:100%;border-collapse:collapse;">
      {mrow('nifty',   'Nifty 50')}
      {mrow('sensex',  'Sensex')}
      {mrow('sp500',   'S&P 500')}
      {mrow('bitcoin', 'Bitcoin')}
    </table>
  </div>

  {section_blk('$',   'Money Talk',      'money', '#5dbf8a')}
  {section_blk('🌐',  'World Lore',      'world', '#5d8adc')}
  {section_blk('⚡',  'Tech Tea',        'tech',  '#c9a552')}
  {section_blk('🇮🇳', 'India Low-Down',  'india', '#e05c5c')}

  <div style="margin-bottom:1.4rem;">
    <h3 style="font-size:.88rem;color:#c4365a;text-transform:uppercase;letter-spacing:.1em;
               border-bottom:1px solid rgba(255,255,255,.07);padding-bottom:.45rem;margin-bottom:.7rem;">
      ⚡ Speed Round</h3>
    <p style="font-size:.84rem;color:#b0a088;line-height:2.1;">
      {strip_md(sections.get('speed',''), 500).replace(chr(10),'<br>')}
    </p>
  </div>

  <p style="font-size:.76rem;color:#3a2e22;text-align:center;margin-top:2rem;font-style:italic;">
    Stay curious, {OWNER_NAME}.</p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subj
    msg["From"]    = GMAIL_USER
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, RECIPIENT_EMAIL, msg.as_string())
        log(f"Email sent → {RECIPIENT_EMAIL}", "✓")
        return True
    except Exception as exc:
        log(f"Email failed — {exc}", "✗")
        return False

# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════
def main():
    skip_email   = "--no-email"   in sys.argv
    skip_browser = "--no-browser" in sys.argv

    print(f"\n{'═' * 62}")
    print(f"  {DIGEST_TITLE}")
    print(f"  {datetime.datetime.now().strftime('%A, %d %B %Y — %H:%M')}")
    print(f"{'═' * 62}")

    # 1 — RSS
    all_articles = fetch_rss_articles()

    # 2 — Markets
    markets = fetch_market_data()

    # 3 — AI Digest
    digest_text = get_ai_digest(all_articles)
    sections    = parse_sections(digest_text)

    # 4 — Spanish lesson
    spanish = get_spanish_lesson()
    log_section(f"SPANISH › Theme {spanish['index']}: {spanish['theme']}")
    log(spanish["roadmap"])

    # 5 — Build HTML
    log_section("BUILDING HTML DASHBOARD")
    html = build_html(sections, markets, spanish, all_articles)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    log(f"Saved → {OUTPUT_HTML}", "✓")

    # 6 — Email
    if skip_email:
        log("Email skipped (--no-email flag)", "!")
    else:
        date_str = datetime.datetime.now().strftime("%A, %d %B %Y")
        send_email(sections, markets, date_str)

    # 7 — Open browser
    if skip_browser:
        log("Browser skipped (--no-browser flag)", "!")
    else:
        log_section("OPENING DASHBOARD")
        webbrowser.open(OUTPUT_HTML.as_uri())
        log("Dashboard opened in browser", "✓")

    print(f"\n{'═' * 62}")
    print(f"  Done!  →  {OUTPUT_HTML}")
    print(f"{'═' * 62}\n")


if __name__ == "__main__":
    main()
