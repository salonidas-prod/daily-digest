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
GITHUB_TOKEN       = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO        = os.getenv("GITHUB_REPO", "salonidas-prod/daily-digest")

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
# SPANISH LESSONS  — 30 daily sets, Duolingo-style rotating vocab
# Each set: type label + 5 items (es, en, example, pron)
# ══════════════════════════════════════════════════════════
SPANISH_LESSONS = [
    # A1→B1 progressive curriculum — 30 daily lessons building from absolute zero
    # Lesson 1: First words ever
    {"type": "A1 · First Hello",
     "items": [
        ("Hola",          "Hello",          "¡Hola! ¿Cómo estás?",            "OH-lah"),
        ("Buenos días",   "Good morning",   "Buenos días, ¿cómo estás?",      "BWEH-nohs DEE-ahs"),
        ("Buenas tardes", "Good afternoon", "Buenas tardes, señorita.",        "BWEH-nahs TAR-dehs"),
        ("Buenas noches", "Good evening",   "Buenas noches, hasta mañana.",    "BWEH-nahs NOH-chehs"),
        ("Adiós",         "Goodbye",        "¡Adiós! Hasta pronto.",           "ah-DYOHS"),
    ]},
    # Lesson 2: What's your name?
    {"type": "A1 · Your Name",
     "items": [
        ("¿Cómo te llamas?", "What's your name?",  "¿Cómo te llamas tú?",          "KOH-moh teh YAH-mahs"),
        ("Me llamo…",        "My name is…",         "Me llamo Saloni.",              "meh YAH-moh"),
        ("¿Y tú?",           "And you?",            "Me llamo Ana. ¿Y tú?",          "ee TOO"),
        ("Mucho gusto.",     "Nice to meet you.",   "Mucho gusto, me llamo Carlos.", "MOO-choh GOOS-toh"),
        ("Encantada.",       "Delighted. (f)",      "Encantada de conocerte.",       "en-kahn-TAH-dah"),
    ]},
    # Lesson 3: Who are you?
    {"type": "A1 · Who Are You?",
     "items": [
        ("¿Quién eres?",   "Who are you?",       "¿Quién eres tú?",               "KYEHN EH-rehs"),
        ("¿Quién es él?",  "Who is he?",         "¿Quién es él? Es mi amigo.",    "KYEHN es EL"),
        ("¿Quién es ella?","Who is she?",         "¿Quién es ella? Es mi hermana.","KYEHN es EH-yah"),
        ("Él es…",         "He is…",             "Él es mi profesor.",            "el es"),
        ("Ella es…",       "She is…",            "Ella es mi madre.",             "EH-yah es"),
    ]},
    # Lesson 4: How are you?
    {"type": "A1 · How Are You?",
     "items": [
        ("¿Cómo estás?",  "How are you?",   "¡Hola! ¿Cómo estás?",           "KOH-moh es-TAHS"),
        ("Estoy bien.",   "I'm fine.",      "Estoy bien, gracias.",           "es-TOY byehn"),
        ("Estoy mal.",    "I'm not well.",  "Hoy estoy un poco mal.",         "es-TOY mahl"),
        ("Más o menos.",  "So-so.",         "¿Cómo estás? Más o menos.",      "mahs oh MEH-nohs"),
        ("¿Y tú?",        "And you?",       "Estoy bien. ¿Y tú?",             "ee TOO"),
    ]},
    # Lesson 5: Please, thank you, sorry
    {"type": "A1 · Please & Thank You",
     "items": [
        ("Por favor",   "Please",          "Un café, por favor.",            "por fah-VOR"),
        ("Gracias",     "Thank you",       "Muchas gracias.",                "GRAH-syahs"),
        ("De nada",     "You're welcome",  "— Gracias. — ¡De nada!",        "deh NAH-dah"),
        ("Lo siento",   "I'm sorry",       "Lo siento mucho.",               "loh SYEHN-toh"),
        ("Perdón",      "Excuse me",       "Perdón, ¿dónde está el baño?",  "pehr-DOHN"),
    ]},
    # Lesson 6: Yes, no, basics
    {"type": "A1 · Yes & No",
     "items": [
        ("Sí",          "Yes",             "Sí, quiero.",                    "see"),
        ("No",          "No",              "No, gracias.",                   "noh"),
        ("Claro",       "Of course",       "¡Claro que sí!",                 "KLAH-roh"),
        ("No sé",       "I don't know",    "No sé dónde está.",              "noh seh"),
        ("No entiendo", "I don't understand","No entiendo, ¿puede repetir?", "noh en-TYEHN-doh"),
    ]},
    # Lesson 7: Numbers 1–5
    {"type": "A1 · Numbers 1–5",
     "items": [
        ("uno",    "one",   "Tengo un hermano.",          "OO-noh"),
        ("dos",    "two",   "Son las dos de la tarde.",   "dohs"),
        ("tres",   "three", "Necesito tres cosas.",       "trehs"),
        ("cuatro", "four",  "Hay cuatro personas aquí.",  "KWAH-troh"),
        ("cinco",  "five",  "Son las cinco en punto.",    "SEEN-koh"),
    ]},
    # Lesson 8: Numbers 6–10
    {"type": "A1 · Numbers 6–10",
     "items": [
        ("seis",  "six",   "Tengo seis libros.",          "sehees"),
        ("siete", "seven", "Hay siete días en la semana.","SYEH-teh"),
        ("ocho",  "eight", "Son las ocho de la mañana.", "OH-choh"),
        ("nueve", "nine",  "Dormí nueve horas.",          "NWEH-beh"),
        ("diez",  "ten",   "Tengo diez dedos.",           "dyehs"),
    ]},
    # Lesson 9: Where are you from?
    {"type": "A1 · Where Are You From?",
     "items": [
        ("¿De dónde eres?", "Where are you from?",  "¿De dónde eres tú?",           "deh DON-deh EH-rehs"),
        ("Soy de India.",   "I'm from India.",      "Soy de India, de Mumbai.",      "soy deh EEN-dyah"),
        ("¿Dónde vives?",   "Where do you live?",   "¿Dónde vives ahora?",           "DON-deh BEE-behs"),
        ("Vivo en…",        "I live in…",           "Vivo en Mumbai.",               "BEE-boh en"),
        ("¿Hablas español?","Do you speak Spanish?","¿Hablas español o inglés?",     "AH-blahs es-pah-NYOL"),
    ]},
    # Lesson 10: Days Monday–Friday
    {"type": "A1 · Days of the Week I",
     "items": [
        ("lunes",     "Monday",    "El lunes tengo clase.",         "LOO-nehs"),
        ("martes",    "Tuesday",   "Los martes voy al gimnasio.",   "MAR-tehs"),
        ("miércoles", "Wednesday", "Los miércoles como fuera.",     "MYEHR-koh-lehs"),
        ("jueves",    "Thursday",  "El jueves hay reunión.",        "HWEH-behs"),
        ("viernes",   "Friday",    "¡Hoy es viernes! ¡Yay!",       "BYEHR-nehs"),
    ]},
    # Lesson 11: Days + today/yesterday/tomorrow
    {"type": "A1 · Days of the Week II",
     "items": [
        ("sábado",  "Saturday",   "El sábado salgo con amigos.",   "SAH-bah-doh"),
        ("domingo", "Sunday",     "El domingo descanso.",          "doh-MEEN-goh"),
        ("hoy",     "today",      "Hoy es lunes.",                 "oy"),
        ("mañana",  "tomorrow",   "Mañana tengo examen.",          "mah-NYAH-nah"),
        ("ayer",    "yesterday",  "Ayer llovió mucho.",            "ah-YEHR"),
    ]},
    # Lesson 12: Basic colours
    {"type": "A1 · Colours",
     "items": [
        ("rojo",     "red",     "El tomate es rojo.",          "ROH-hoh"),
        ("azul",     "blue",    "El cielo es azul.",           "ah-SOOL"),
        ("verde",    "green",   "La hierba es verde.",         "BEHR-deh"),
        ("amarillo", "yellow",  "El sol es amarillo.",         "ah-mah-REE-yoh"),
        ("negro",    "black",   "Llevo una camisa negra.",     "NEH-groh"),
    ]},
    # Lesson 13: Family
    {"type": "A1 · Family",
     "items": [
        ("la madre",   "mother",    "Mi madre cocina muy bien.",     "lah MAH-dreh"),
        ("el padre",   "father",    "Mi padre trabaja mucho.",       "el PAH-dreh"),
        ("el hermano", "brother",   "Tengo un hermano mayor.",       "el ehr-MAH-noh"),
        ("la hermana", "sister",    "Mi hermana vive en Delhi.",     "lah ehr-MAH-nah"),
        ("la familia", "the family","Mi familia es muy grande.",     "lah fah-MEE-lyah"),
    ]},
    # Lesson 14: Common objects
    {"type": "A1 · Everyday Things",
     "items": [
        ("la casa",  "the house", "Mi casa es pequeña pero bonita.", "lah KAH-sah"),
        ("el libro", "the book",  "Estoy leyendo un libro.",         "el LEE-broh"),
        ("el agua",  "water",     "Quiero agua, por favor.",         "el AH-gwah"),
        ("la mesa",  "the table", "La mesa está en la cocina.",      "lah MEH-sah"),
        ("la silla", "the chair", "¿Puedo sentarme en esta silla?",  "lah SEE-yah"),
    ]},
    # Lesson 15: SER — to be (permanent)
    {"type": "A1 · 'To Be' — ser",
     "items": [
        ("Soy",    "I am",      "Soy estudiante.",             "soy"),
        ("Eres",   "You are",   "Eres muy simpática.",         "EH-rehs"),
        ("Es",     "He/She is", "Ella es mi profesora.",       "es"),
        ("Somos",  "We are",    "Somos de India.",             "SOH-mohs"),
        ("Son",    "They are",  "Son las tres de la tarde.",   "sohn"),
    ]},
    # Lesson 16: ESTAR — to be (temporary/location)
    {"type": "A1 · 'To Be' — estar",
     "items": [
        ("Estoy",   "I am",      "Estoy en Mumbai.",           "es-TOY"),
        ("Estás",   "You are",   "¿Cómo estás?",              "es-TAHS"),
        ("Está",    "He/She is", "Él está cansado.",           "es-TAH"),
        ("Estamos", "We are",    "Estamos en el café.",        "es-TAH-mohs"),
        ("Están",   "They are",  "¿Dónde están mis llaves?",  "es-TAHN"),
    ]},
    # Lesson 17: Question words
    {"type": "A1 · Question Words",
     "items": [
        ("¿Qué?",     "What?",  "¿Qué quieres comer?",        "keh"),
        ("¿Dónde?",   "Where?", "¿Dónde está el baño?",       "DON-deh"),
        ("¿Cuándo?",  "When?",  "¿Cuándo llega el tren?",     "KWAHN-doh"),
        ("¿Por qué?", "Why?",   "¿Por qué estás triste?",     "por KEH"),
        ("¿Cómo?",    "How?",   "¿Cómo se dice 'train'?",     "KOH-moh"),
    ]},
    # Lesson 18: I want / I need / I have
    {"type": "A1 · I Want & I Need",
     "items": [
        ("Quiero…",    "I want…",   "Quiero un café, por favor.",  "KYEH-roh"),
        ("Necesito…",  "I need…",   "Necesito ayuda.",             "neh-seh-SEE-toh"),
        ("Tengo…",     "I have…",   "Tengo hambre.",               "TEHN-goh"),
        ("No tengo…",  "I don't have…","No tengo dinero.",         "noh TEHN-goh"),
        ("¿Tienes…?",  "Do you have…?","¿Tienes un bolígrafo?",    "TYEH-nehs"),
    ]},
    # Lesson 19: Café & food basics
    {"type": "A1 · At the Café",
     "items": [
        ("el café",     "coffee",          "Un café con leche, por favor.",     "el kah-FEH"),
        ("el té",       "tea",             "Quiero un té verde.",               "el teh"),
        ("el pan",      "bread",           "¿Me da pan, por favor?",            "el pahn"),
        ("la leche",    "milk",            "¿Tiene leche de avena?",            "lah LEH-cheh"),
        ("La cuenta.",  "The bill.",       "La cuenta, cuando pueda.",          "lah KWEHN-tah"),
    ]},
    # Lesson 20: Simple verbs go/come/eat
    {"type": "A1 · Simple Verbs",
     "items": [
        ("voy / vas",   "I go / you go",   "Voy al trabajo.",                "boy / bahs"),
        ("vengo / vienes","I come/you come","¿Vienes a la fiesta?",           "BEHN-goh / BYEH-nehs"),
        ("como / comes","I eat / you eat",  "Como pizza los viernes.",        "KOH-moh / KOH-mehs"),
        ("bebo / bebes","I drink/you drink","¿Qué bebes tú?",                 "BEH-boh / BEH-behs"),
        ("hablo / hablas","I speak/you speak","¿Hablas español?",             "AH-bloh / AH-blahs"),
    ]},
    # Lesson 21: Telling the time
    {"type": "A1 · Telling the Time",
     "items": [
        ("¿Qué hora es?",  "What time is it?",  "¿Qué hora es, por favor?",     "keh OH-rah es"),
        ("Es la una.",     "It's one o'clock.", "Son las reuniones a la una.",   "es lah OO-nah"),
        ("Son las dos.",   "It's two o'clock.", "Son las dos de la tarde.",      "sohn lahs dohs"),
        ("de la mañana",   "in the morning",    "Son las ocho de la mañana.",   "deh lah mah-NYAH-nah"),
        ("de la noche",    "at night",          "Son las diez de la noche.",    "deh lah NOH-cheh"),
    ]},
    # Lesson 22: Numbers 11–20
    {"type": "A1 · Numbers 11–20",
     "items": [
        ("once / doce",     "eleven / twelve",    "Hay doce meses en el año.",   "OHN-seh / DOH-seh"),
        ("trece / catorce", "thirteen / fourteen","Tengo catorce primas.",        "TREH-seh / kah-TOR-seh"),
        ("quince",          "fifteen",            "Quince minutos, por favor.",  "KEEN-seh"),
        ("dieciséis / diecisiete","16 / 17",      "Tengo diecisiete años.",      "dyeh-see-SEHEES"),
        ("veinte",          "twenty",             "Hay veinte personas aquí.",   "BEHN-teh"),
    ]},
    # Lesson 23: Basic adjectives
    {"type": "A2 · Describing Things",
     "items": [
        ("grande",    "big",       "La ciudad es muy grande.",      "GRAHN-deh"),
        ("pequeño/a", "small",     "Tengo un apartamento pequeño.", "peh-KEH-nyoh"),
        ("bonito/a",  "pretty",    "Qué día tan bonito.",           "boh-NEE-toh"),
        ("fácil",     "easy",      "Esta lección es muy fácil.",    "FAH-seel"),
        ("difícil",   "difficult", "La gramática es difícil.",      "dee-FEE-seel"),
    ]},
    # Lesson 24: Feelings
    {"type": "A2 · Feelings",
     "items": [
        ("feliz",        "happy",    "Estoy muy feliz hoy.",            "feh-LEES"),
        ("triste",       "sad",      "Me siento un poco triste.",       "TREES-teh"),
        ("cansada/o",    "tired",    "Estoy muy cansada hoy.",          "kahn-SAH-dah"),
        ("emocionada/o", "excited",  "¡Estoy emocionada con el viaje!", "eh-moh-syoh-NAH-dah"),
        ("tranquila/o",  "calm",     "Respira. Sé tranquila.",          "trahn-KEE-lah"),
    ]},
    # Lesson 25: Directions
    {"type": "A2 · Directions",
     "items": [
        ("a la derecha",  "on the right",    "El banco está a la derecha.", "ah lah deh-REH-chah"),
        ("a la izquierda","on the left",     "Gira a la izquierda aquí.",   "ah lah ees-KYEHR-dah"),
        ("todo recto",    "straight ahead",  "Sigue todo recto.",           "TOH-doh REK-toh"),
        ("cerca de",      "near",            "Está cerca de la estación.",  "SEHR-kah deh"),
        ("lejos de",      "far from",        "Está lejos de aquí.",         "LEH-hohs deh"),
    ]},
    # Lesson 26: Weather
    {"type": "A2 · Weather",
     "items": [
        ("¿Qué tiempo hace?","What's the weather?","¿Qué tiempo hace hoy?",       "keh TYEHM-poh AH-seh"),
        ("Hace calor.",  "It's hot.",         "Hace mucho calor en verano.",   "AH-seh kah-LOR"),
        ("Hace frío.",   "It's cold.",        "Hace frío en diciembre.",       "AH-seh FREE-oh"),
        ("Llueve.",      "It's raining.",     "Hoy llueve mucho.",             "YWE-beh"),
        ("Hace sol.",    "It's sunny.",       "Hace sol — ¡perfecto!",         "AH-seh sohl"),
    ]},
    # Lesson 27: Ser vs Estar in practice
    {"type": "A2 · Ser vs Estar",
     "items": [
        ("Soy alta.",      "I am tall. (trait)",      "Soy alta y delgada.",          "soy AHL-tah"),
        ("Estoy aquí.",    "I am here. (location)",   "Estoy aquí en el café.",       "es-TOY ah-KEE"),
        ("Es bonita.",     "It's pretty. (permanent)","La ciudad es bonita.",         "es boh-NEE-tah"),
        ("Está abierto.",  "It's open. (state)",      "La tienda está abierta.",      "es-TAH ah-BYEHR-toh"),
        ("Somos amigos.",  "We are friends.",          "Somos amigos desde siempre.", "SOH-mohs ah-MEE-gohs"),
    ]},
    # Lesson 28: -AR verb conjugation
    {"type": "A2 · -AR Verbs",
     "items": [
        ("(yo) hablo",        "I speak",    "Hablo español un poco.",        "AH-bloh"),
        ("(tú) caminas",      "you walk",   "Caminas muy rápido.",           "kah-MEE-nahs"),
        ("(él/ella) trabaja", "he/she works","Mi madre trabaja en casa.",    "trah-BAH-hah"),
        ("(nosotros) cantamos","we sing",   "Cantamos en el coche.",         "kahn-TAH-mohs"),
        ("(ellos) bailan",    "they dance", "Ellos bailan muy bien.",        "BAH-ee-lahn"),
    ]},
    # Lesson 29: Daily routine (reflexive verbs)
    {"type": "A2 · Daily Routine",
     "items": [
        ("Me levanto",   "I get up",     "Me levanto a las siete.",       "meh leh-BAHN-toh"),
        ("Me ducho",     "I shower",     "Me ducho por la mañana.",       "meh DOO-choh"),
        ("Desayuno",     "I eat breakfast","Desayuno a las ocho.",         "deh-sah-YOO-noh"),
        ("Trabajo",      "I work",       "Trabajo de nueve a seis.",      "trah-BAH-hoh"),
        ("Me acuesto",   "I go to bed",  "Me acuesto a las once.",        "meh ah-KWES-toh"),
    ]},
    # Lesson 30: Useful idioms & survival phrases
    {"type": "A2 · Handy Phrases",
     "items": [
        ("¿Me puede ayudar?","Can you help me?",    "Perdón, ¿me puede ayudar?",    "meh PWEH-deh ah-yoo-DAR"),
        ("No hablo bien español.","I don't speak Spanish well.","No hablo bien español, lo siento.","noh AH-bloh byehn"),
        ("¿Puede repetir?", "Can you repeat?",      "¿Puede repetir más despacio?", "PWEH-deh reh-peh-TEER"),
        ("¡Qué guay!",      "How cool!",            "¡Qué guay ese lugar!",         "keh gwah-ee"),
        ("¡Venga!",         "Let's go! / Come on!", "¡Venga, que llegamos tarde!",  "BEHN-gah"),
    ]},
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

    markets["nifty"]  = {**get_yahoo("^NSEI",  "Nifty 50"),  "key": "nifty"}
    markets["sensex"] = {**get_yahoo("^BSESN", "Sensex"),    "key": "sensex"}
    markets["sp500"]  = {**get_yahoo("^GSPC",  "S&P 500"),   "key": "sp500"}

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
            "label": "Bitcoin", "symbol": "BTC", "key": "bitcoin",
            "price": f"{btc_price:,.0f}", "prefix": "$",
            "change": btc_chg, "change_str": f"{btc_chg:+.2f}%",
            "up": btc_chg >= 0, "error": False,
        }
        log(f"Bitcoin: ${btc_price:,.0f} ({btc_chg:+.2f}%)")
    except Exception as exc:
        log(f"Bitcoin failed — {exc}", "✗")
        markets["bitcoin"] = {"label": "Bitcoin", "symbol": "BTC", "key": "bitcoin", "price": "N/A", "change": 0, "error": True}

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
    idx         = (day_of_year - 1) % len(SPANISH_LESSONS)
    lesson      = dict(SPANISH_LESSONS[idx])
    lesson["index"] = idx + 1
    lesson["total"] = len(SPANISH_LESSONS)
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
MARKET_LINKS = {
    "nifty":   "https://finance.yahoo.com/quote/%5ENSEI/",
    "sensex":  "https://finance.yahoo.com/quote/%5EBSESN/",
    "sp500":   "https://finance.yahoo.com/quote/%5EGSPC/",
    "bitcoin": "https://www.coingecko.com/en/coins/bitcoin",
}

def _market_card(m, default_prefix=""):
    label  = m.get("label", "")
    key    = m.get("key", "")
    link   = MARKET_LINKS.get(key, "#")
    if m.get("error"):
        return (f'<a class="market-card" href="{link}" target="_blank" rel="noopener">'
                f'<span class="market-label">{label}</span>'
                f'<span class="market-price">N/A</span>'
                f'<span class="market-change neutral">—</span>'
                f'</a>')
    color  = "gain" if m.get("up", True) else "loss"
    arrow  = "▲" if m.get("up", True) else "▼"
    prefix = m.get("prefix", default_prefix)
    return (f'<a class="market-card" href="{link}" target="_blank" rel="noopener">'
            f'<span class="market-label">{label}</span>'
            f'<span class="market-price">{prefix}{m["price"]}</span>'
            f'<span class="market-change {color}">{arrow} {m.get("change_str", "")}</span>'
            f'</a>')

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

    pipe = '<span class="ticker-pipe">|</span>'
    ticker_html = (
        '<span class="ticker-markets-label">Markets</span>' + pipe +
        _market_card(markets.get("nifty",   {"label": "Nifty 50",  "key": "nifty",   "error": True})) + pipe +
        _market_card(markets.get("sensex",  {"label": "Sensex",    "key": "sensex",  "error": True})) + pipe +
        _market_card(markets.get("sp500",   {"label": "S&P 500",   "key": "sp500",   "error": True})) + pipe +
        _market_card(markets.get("bitcoin", {"label": "Bitcoin",   "key": "bitcoin", "error": True}))
    )

    # Spanish vocab cards (Duolingo-style)
    vocab_cards = ""
    for es, en, example, pron in spanish["items"]:
        pron_html = f'<div class="vocab-pron">{pron}</div>' if pron else ""
        vocab_cards += f"""<div class="vocab-card">
              <div class="vocab-es">{es}</div>
              <div class="vocab-en">{en}</div>
              <div class="vocab-example">{example}</div>
              {pron_html}
            </div>"""

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
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;0,900;1,400;1,700&family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Jost:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --paper:        #f6f1e7;
    --paper-dark:   #ede8da;
    --paper-white:  #ffffff;
    --ink:          #111111;
    --ink-dim:      #333333;
    --ink-light:    #666666;
    --ink-faint:    #999999;
    --red:          #c0001a;
    --border:       rgba(0,0,0,0.18);
    --border-light: rgba(0,0,0,0.08);
    --gain:         #1a6b35;
    --loss:         #b50016;
    --neutral:      #777;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--paper);
    color: var(--ink);
    font-family: 'EB Garamond', Georgia, serif;
    font-size: 1rem;
    line-height: 1.75;
    min-height: 100vh;
  }}

  /* ── TOP RULE ─────────────────────────────── */
  .top-rule {{
    height: 4px;
    background: var(--red);
  }}

  /* ── MASTHEAD ─────────────────────────────── */
  .masthead {{
    background: var(--paper);
    border-bottom: 3px double var(--ink);
    padding: 0.9rem 4rem 1.5rem;
    text-align: center;
  }}
  .masthead-meta {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: 'Jost', sans-serif;
    font-size: 0.65rem;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--ink-light);
    padding-bottom: 0.7rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1rem;
  }}
  .masthead-eyebrow {{
    font-family: 'Jost', sans-serif;
    font-size: 0.6rem;
    letter-spacing: 0.32em;
    text-transform: uppercase;
    color: var(--ink-light);
    margin-bottom: 0.3rem;
  }}
  .masthead-title {{
    font-family: 'Playfair Display', serif;
    font-size: clamp(2.6rem, 7vw, 4.8rem);
    font-weight: 900;
    color: var(--ink);
    line-height: 1.0;
    letter-spacing: -0.02em;
  }}
  .masthead-title em {{
    font-style: italic;
    font-weight: 700;
  }}
  .masthead-tagline {{
    font-family: 'EB Garamond', serif;
    font-size: 1rem;
    font-style: italic;
    color: var(--ink-light);
    margin-top: 0.4rem;
  }}
  @media (max-width: 900px) {{
    .masthead {{ padding-left: 1.5rem; padding-right: 1.5rem; }}
    .masthead-meta {{ font-size: 0.55rem; }}
  }}

  /* ── MARKET TICKER ───────────────────────── */
  .ticker-bar {{
    background: var(--paper);
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    padding: 0.75rem 4rem;
  }}
  .ticker-inner {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1.4rem;
    flex-wrap: wrap;
  }}
  .ticker-markets-label {{
    font-family: 'Jost', sans-serif;
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--ink-light);
  }}
  .ticker-pipe {{
    color: var(--border);
    font-size: 1.1rem;
    font-weight: 300;
    line-height: 1;
    user-select: none;
  }}
  .market-card {{
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    text-decoration: none;
    cursor: pointer;
    padding: 0.15rem 0.35rem;
    border-radius: 2px;
    transition: background 0.15s;
  }}
  .market-card:hover {{ background: var(--paper-dark); }}
  .market-label  {{ font-family: 'Jost', sans-serif; font-size: 0.6rem; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-light); }}
  .market-price  {{ font-family: 'Playfair Display', serif; font-size: 1rem; color: var(--ink); font-weight: 700; }}
  .market-change {{ font-family: 'Jost', sans-serif; font-size: 0.68rem; font-weight: 500; }}
  .market-change.gain    {{ color: var(--gain); }}
  .market-change.loss    {{ color: var(--loss); }}
  .market-change.neutral {{ color: var(--neutral); }}

  /* ── MAIN LAYOUT ─────────────────────────── */
  .main-wrap {{
    max-width: 1300px;
    margin: 0 auto;
    padding: 2.5rem 4rem;
  }}
  .section-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.8rem;
    margin-bottom: 1.8rem;
  }}
  @media (max-width: 900px) {{
    .section-grid {{ grid-template-columns: 1fr; }}
    .masthead, .ticker-bar, .main-wrap {{ padding-left: 1.5rem; padding-right: 1.5rem; }}
  }}

  /* ── SECTION CARDS ───────────────────────── */
  .section-card {{
    border: 1px solid var(--border);
    overflow: hidden;
  }}
  .section-header {{
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.85rem 1.4rem;
    background: var(--ink);
    border-bottom: 2px solid var(--ink);
  }}
  .section-icon  {{ font-size: 1rem; }}
  .section-title {{
    font-family: 'Jost', sans-serif;
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: var(--paper);
  }}
  .section-body {{
    padding: 1.5rem;
    font-size: 0.96rem;
    color: var(--ink-dim);
    line-height: 1.82;
    background: var(--paper);
  }}
  .section-body p {{ margin-bottom: 0.85rem; }}
  .section-body p:last-child {{ margin-bottom: 0; }}
  .section-body strong {{ color: var(--ink); font-weight: 700; }}
  .section-body em {{ color: var(--ink-dim); font-style: italic; }}
  .section-body .spacer {{ height: 0.4rem; }}
  .digest-list {{ padding-left: 1.2rem; margin: 0.5rem 0 0.85rem; }}
  .digest-list li {{ margin-bottom: 0.35rem; }}
  .inline-heading {{
    font-family: 'Jost', sans-serif;
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--ink);
    margin: 1rem 0 0.35rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    border-bottom: 1px solid var(--border-light);
    padding-bottom: 0.2rem;
  }}

  /* ── SPEED ROUND ─────────────────────────── */
  .speed-section {{
    border: 1px solid var(--border);
    overflow: hidden;
    margin-bottom: 1.8rem;
  }}
  .speed-header {{
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.85rem 1.4rem;
    background: var(--red);
  }}
  .speed-header .section-title {{ color: white; }}
  .speed-body {{
    padding: 1rem 1.2rem;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
    background: var(--paper);
  }}
  @media (max-width: 700px) {{ .speed-body {{ grid-template-columns: 1fr; }} }}
  .speed-item {{
    padding: 0.52rem 0.7rem;
    border-bottom: 1px solid var(--border-light);
    font-size: 0.9rem;
    color: var(--ink-dim);
    line-height: 1.55;
  }}
  .speed-item:last-child {{ border-bottom: none; }}
  .speed-item strong {{ color: var(--ink); }}

  /* ── SPANISH SECTION ─────────────────────── */
  .spanish-section {{
    border: 1px solid var(--border);
    overflow: hidden;
    margin-bottom: 1.8rem;
  }}
  .spanish-header {{
    background: var(--ink);
    padding: 0.85rem 1.4rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.7rem;
  }}
  .spanish-title-group {{ display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap; }}
  .spanish-badge {{
    font-family: 'Jost', sans-serif;
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--ink);
    background: var(--paper);
    padding: 0.15rem 0.5rem;
  }}
  .spanish-counter {{
    font-family: 'Jost', sans-serif;
    font-size: 0.62rem;
    color: rgba(246,241,231,0.55);
    letter-spacing: 0.08em;
  }}
  .spanish-body {{ padding: 1.4rem; background: var(--paper); }}
  .vocab-grid {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 0.8rem;
  }}
  @media (max-width: 1100px) {{ .vocab-grid {{ grid-template-columns: repeat(3, 1fr); }} }}
  @media (max-width: 700px)  {{ .vocab-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  .vocab-card {{
    background: var(--paper-white);
    border: 1px solid var(--border);
    padding: 1rem 1rem 0.9rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    transition: border-color 0.18s, box-shadow 0.18s;
  }}
  .vocab-card:hover {{
    border-color: var(--ink);
    box-shadow: 2px 2px 0 var(--ink);
  }}
  .vocab-es {{
    font-family: 'Playfair Display', serif;
    font-size: 1.1rem;
    font-style: italic;
    color: var(--ink);
    font-weight: 600;
  }}
  .vocab-en {{
    font-family: 'Jost', sans-serif;
    font-size: 0.68rem;
    font-weight: 600;
    color: var(--red);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }}
  .vocab-example {{
    font-family: 'EB Garamond', serif;
    font-size: 0.9rem;
    color: var(--ink-light);
    font-style: italic;
    line-height: 1.5;
    margin-top: 0.2rem;
    flex: 1;
  }}
  .vocab-pron {{
    font-family: 'Jost', sans-serif;
    font-size: 0.62rem;
    color: var(--ink-faint);
    margin-top: 0.3rem;
    letter-spacing: 0.04em;
  }}

  /* ── FOOTER ──────────────────────────────── */
  .site-footer {{
    border-top: 3px double var(--ink);
    padding: 1.4rem 4rem;
    text-align: center;
    color: var(--ink-light);
    font-family: 'Jost', sans-serif;
    font-size: 0.65rem;
    line-height: 1.9;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }}
  .footer-sources {{ max-width: 900px; margin: 0 auto 0.4rem; }}
  .footer-tag {{
    font-family: 'EB Garamond', serif;
    font-style: italic;
    color: var(--ink-dim);
    font-size: 0.9rem;
    text-transform: none;
    letter-spacing: 0;
  }}

  /* ── SCROLLBAR ───────────────────────────── */
  ::-webkit-scrollbar {{ width: 5px; }}
  ::-webkit-scrollbar-track {{ background: var(--paper); }}
  ::-webkit-scrollbar-thumb {{ background: var(--ink); }}
</style>
</head>
<body>

<!-- MASTHEAD -->
<div class="top-rule"></div>
<header class="masthead">
  <div class="masthead-meta">
    <span>{date_str}</span>
    <span>Generated at {time_str} IST</span>
  </div>
  <p class="masthead-eyebrow">Your morning brief</p>
  <h1 class="masthead-title">{OWNER_NAME}'s <em>Daily</em> Digest</h1>
  <p class="masthead-tagline">Served sharp. No fluff. Just the world as it is.</p>
</header>

<!-- MARKET TICKER -->
<div class="ticker-bar">
  <div class="ticker-inner">
    {ticker_html}
  </div>
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
        <div class="spanish-badge">{spanish['type']}</div>
      </div>
      <div class="spanish-counter">Lesson {spanish['index']} of {spanish['total']}</div>
    </div>
    <div class="spanish-body">
      <div class="vocab-grid">
        {vocab_cards}
      </div>
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
# GITHUB PAGES PUBLISHER
# ══════════════════════════════════════════════════════════
def push_to_gh_pages(html_path):
    """Push dashboard.html as index.html to the gh-pages branch."""
    import subprocess, tempfile, shutil
    log_section("PUBLISHING TO GITHUB PAGES")

    if not GITHUB_TOKEN:
        log("GITHUB_TOKEN not set — skipping GitHub Pages publish.", "!")
        return False

    try:
        with tempfile.TemporaryDirectory() as tmp:
            # Copy dashboard as index.html
            shutil.copy(html_path, os.path.join(tmp, "index.html"))

            remote = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
            date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M IST")

            def run(cmd, **kw):
                return subprocess.run(cmd, cwd=tmp, check=True,
                                      capture_output=True, text=True, **kw)

            run(["git", "init"])
            run(["git", "checkout", "-b", "gh-pages"])
            run(["git", "config", "user.email", "digest@local"])
            run(["git", "config", "user.name",  "Saloni's Digest Bot"])
            run(["git", "add", "index.html"])
            run(["git", "commit", "-m", f"digest: {date_str}"])
            run(["git", "push", "--force", remote, "gh-pages"])

        log(f"Published → https://{GITHUB_REPO.split('/')[0]}.github.io/"
            f"{GITHUB_REPO.split('/')[1]}/", "✓")
        return True
    except Exception as exc:
        log(f"GitHub Pages publish failed — {exc}", "✗")
        return False


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
    log_section(f"SPANISH › Lesson {spanish['index']}: {spanish['type']}")
    log(f"{len(spanish['items'])} items loaded")

    # 5 — Build HTML
    log_section("BUILDING HTML DASHBOARD")
    html = build_html(sections, markets, spanish, all_articles)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    log(f"Saved → {OUTPUT_HTML}", "✓")

    # 6 — Publish to GitHub Pages
    push_to_gh_pages(OUTPUT_HTML)

    # 7 — Email
    if skip_email:
        log("Email skipped (--no-email flag)", "!")
    else:
        date_str = datetime.datetime.now().strftime("%A, %d %B %Y")
        send_email(sections, markets, date_str)

    # 8 — Open browser
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
