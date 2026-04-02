"""
vyasa-yt configuration — Parvan definitions, URL patterns, pipeline constants.
"""

import os
from pathlib import Path

# ── Project paths ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
CHAPTERS_DIR = DATA_DIR / "chapters"
SCRIPTS_DIR = DATA_DIR / "scripts"
AUDIO_DIR = DATA_DIR / "audio"
VIDEOS_DIR = DATA_DIR / "videos"
METADATA_DIR = DATA_DIR / "metadata"
ASSETS_DIR = PROJECT_ROOT / "assets"
INDEX_PATH = DATA_DIR / "index.json"

for d in [CHAPTERS_DIR, SCRIPTS_DIR, AUDIO_DIR, VIDEOS_DIR, METADATA_DIR, ASSETS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Website ────────────────────────────────────────────────────
BASE_URL = "https://vyas-mahabharat.com"
CHAPTER_URL_TEMPLATE = BASE_URL + "/book/{parvan_name}/{chapter_num}/"

USER_AGENT = "Mozilla/5.0 (educational/personal)"
REQUEST_DELAY = 3  # seconds between HTTP requests

# ── Parvan registry ─────────────────────────────────────────────
# Chapter counts verified against vyas-mahabharat.com (probe, March 2026).
# These may differ from the BORI CE numbering used in print editions.
# Each entry: (parvan_name, parvan_key, book_number, total_chapters)
PARVANS = [
    ("Adiparvan",            "adiparvan",             1, 225),
    ("Sabhaparvan",          "sabhaparvan",            2,  72),
    ("Aranyakaparvan",       "aranyakaparvan",         3, 299),
    ("Virataparvan",         "virataparvan",           4,  67),
    ("Udyogaparvan",         "udyogaparvan",           5, 197),
    ("Bhishmaparvan",        "bhishmaparvan",          6, 117),
    ("Dronaparvan",          "dronaparvan",            7, 173),
    ("Karnaparvan",          "karnaparvan",            8,  69),
    ("Shalyaparvan",         "shalyaparvan",           9,  64),
    ("Sauptikaparvan",       "sauptikaparvan",        10,  18),
    ("Striparvan",           "striparvan",            11,  27),
    ("Shantiparvan",         "shantiparvan",          12, 353),
    ("Anushasanaparvan",     "anushasanaparvan",      13, 154),
    ("Ashvamedhikaparvan",   "ashvamedhikaparvan",    14,  96),
    ("Ashramavasikaparvan",  "ashramavasikaparvan",   15,  47),
    ("Mausalaparvan",        "mausalaparvan",         16,   9),
    ("Mahaprasthanikaparvan","mahaprasthanikaparvan", 17,   3),
    ("Svargarohanaparvan",   "svargarohanaparvan",    18,   5),
]

TOTAL_CHAPTERS = sum(p[3] for p in PARVANS)  # 1795 on website

# ── Script generation ──────────────────────────────────────────
MIN_WORDS_STANDALONE = 250   # below this → combine with adjacent chapter
MAX_WORDS_SINGLE = 1500      # above this → split into two scripts
MAX_INPUT_CHARS = 5500       # cap reference text sent to LLM

# ── HuggingFace Inference API ──────────────────────────────────
HF_MODEL = "Qwen/Qwen2.5-72B-Instruct"

SYSTEM_PROMPT = (
    "You are a scholar and storyteller presenting the Mahābhārata to a general audience. "
    "You have studied the BORI Critical Edition deeply. Given a prose summary of a chapter's "
    "events as reference material, write an ORIGINAL narration script for a 4–7 minute "
    "YouTube video.\n\n"
    "Rules:\n"
    "(1) Write in your own words — do not quote or closely paraphrase the reference text.\n"
    "(2) Begin with one sentence placing the listener in the story arc "
    "('In the previous chapter...').\n"
    "(3) Capture the moral complexity of the Mahābhārata — characters are neither simply "
    "good nor evil. Let that ambiguity breathe.\n"
    "(4) Use clear, dignified English. Not archaic. Not casual. The register of a respected "
    "documentary narrator.\n"
    "(5) Where a chapter is primarily philosophical (e.g. Shantiparvan discourse), frame "
    "it as 'Yudhishthira asks... Bhishma explains...' to keep it narrative.\n"
    "(6) End with one sentence on why this chapter matters to the larger story.\n"
    "(7) Plain text only. No headers, no stage directions."
)

METADATA_SYSTEM_PROMPT = (
    "You are a YouTube metadata specialist for an educational Mahābhārata channel. "
    "Given a narration script and chapter info, generate YouTube metadata as a JSON object. "
    "Return ONLY a valid JSON object with keys: yt_title, yt_description, yt_tags, "
    "yt_category, playlist. The title should be under 100 characters, compelling but dignified. "
    "The description should be 3-4 sentences summarizing the chapter's events in your own words, "
    "followed by the tagline: 'This channel presents the complete Mahābhārata, chapter by chapter.' "
    "Tags: array of 10-15 relevant searchable terms including character names. "
    "Return ONLY the JSON object, no other text."
)

# ── Video assembly ─────────────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 24
SUBTITLE_WORD_CHUNK = 10  # words per subtitle line

# ── TTS ────────────────────────────────────────────────────────
TTS_LANG = "en"
TTS_SLOW = False
