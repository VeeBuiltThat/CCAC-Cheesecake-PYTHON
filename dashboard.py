"""
Cheesecake Bot — Admin Dashboard
Run with:  streamlit run dashboard.py
Set DASHBOARD_PASSWORD in .env to protect the dashboard (default: cheesecake-admin)
"""

import streamlit as st
import importlib.util
import json
import os
import sys
import pymysql
import pymysql.cursors
from pathlib import Path
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

# ─── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Cheesecake Admin",
    page_icon="🍰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS — Cheesecake theme
st.markdown("""
<style>
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #2b0a1e 0%, #1a0d14 100%);
        padding-top: 0.5rem;
    }
    [data-testid="stSidebar"] * { color: #ffb6c1 !important; }
    [data-testid="stSidebar"] hr { border-color: #ff69b440 !important; }
    [data-testid="stSidebar"] .stRadio label {
        font-size: 0.88rem;
        padding: 3px 0;
        letter-spacing: 0.2px;
    }
    h1 { color: #ff69b4; font-weight: 700; letter-spacing: -0.3px; margin-bottom: 0.25rem; }
    h2, h3 { color: #d4457a; }
    .stButton > button[kind="primary"] {
        background-color: #c2185b;
        border: none;
        color: white;
        font-weight: 600;
    }
    .stButton > button[kind="primary"]:hover { background-color: #e91e63; }
    .stButton > button[kind="secondary"] { border-color: #c2185b55; color: #ff69b4; }
    div[data-testid="stMetricValue"] { color: #ff69b4 !important; font-weight: 700; }
    .stTabs [aria-selected="true"] {
        color: #ff69b4 !important;
        border-bottom-color: #ff69b4 !important;
    }
    .stAlert { border-radius: 6px; }
    .stDataFrame { border-radius: 6px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ─── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
SETTINGS_FILE = ROOT / "dashboard_settings.json"
sys.path.insert(0, str(ROOT))

# ─── Authentication ────────────────────────────────────────────────────────────
# Priority: .env / env var → st.secrets → hardcoded default
def _get_admin_password() -> str:
    if (pw := os.getenv("DASHBOARD_PASSWORD")):
        return pw
    try:
        return st.secrets["DASHBOARD_PASSWORD"]
    except Exception:
        return "cheesecake-admin"

ADMIN_PASSWORD = _get_admin_password()


def check_auth() -> None:
    if st.session_state.get("authenticated"):
        return
    st.title("Cheesecake Admin Dashboard")
    st.markdown("### Sign in to continue")
    password = st.text_input("Password", type="password", key="login_pw")
    if st.button("Sign In", type="primary"):
        if password == ADMIN_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


# ─── Settings Helpers ──────────────────────────────────────────────────────────

def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_settings(settings: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    st.success("Settings saved to `dashboard_settings.json`. Restart the bot to apply.")


# ─── Bot Config Loader ────────────────────────────────────────────────────────

def _load_cogs_config():
    """Load cogs/config.py by file path. Returns None if the file doesn't exist."""
    cfg_path = Path(__file__).parent / "cogs" / "config.py"
    if not cfg_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("cogs.config", cfg_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _get_db_creds() -> dict:
    """Return DB connection kwargs.

    Priority:
    1. cogs/config.py  (local dev)
    2. st.secrets["database"]  (Streamlit Cloud — add a [database] section in App Secrets)
    3. Environment variables DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME
    """
    cfg = _load_cogs_config()
    if cfg is not None:
        return dict(
            host=cfg.DB_HOST,
            port=int(cfg.DB_PORT),
            user=cfg.DB_USER,
            password=cfg.DB_PASSWORD,
            database=cfg.DB_NAME,
        )
    if hasattr(st, "secrets") and "database" in st.secrets:
        db = st.secrets["database"]
        return dict(
            host=db["host"],
            port=int(db.get("port", 3306)),
            user=db["user"],
            password=db["password"],
            database=db["name"],
        )
    return dict(
        host=os.getenv("DB_HOST", ""),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", ""),
    )


# ─── Database Helpers ─────────────────────────────────────────────────────────

def get_db():
    try:
        creds = _get_db_creds()
        conn = pymysql.connect(
            **creds,
            autocommit=True,
            connect_timeout=5,
            cursorclass=pymysql.cursors.DictCursor,
        )
        return conn, None
    except Exception as exc:
        return None, str(exc)


@st.cache_data(ttl=30)
def query_db(sql: str) -> list:
    conn, err = get_db()
    if err or conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return list(cur.fetchall() or [])
    except Exception:
        return []
    finally:
        conn.close()


def db_execute(sql: str, params: tuple = ()) -> str | None:
    """Run a write query. Returns error string or None on success."""
    conn, err = get_db()
    if err or conn is None:
        return err or "Could not connect to database.  Check Streamlit secrets or environment variables."
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        return None
    except Exception as exc:
        return str(exc)
    finally:
        conn.close()


# ─── Config Loader ─────────────────────────────────────────────────────────────

def load_bot_config() -> dict:
    try:
        cfg = _load_cogs_config()
        creds = _get_db_creds()
        if cfg is not None:
            return {
                "DB_HOST": cfg.DB_HOST,
                "DB_PORT": cfg.DB_PORT,
                "DB_USER": cfg.DB_USER,
                "DB_PASSWORD": cfg.DB_PASSWORD,
                "DB_NAME": cfg.DB_NAME,
                "ABSENCE_ROLE_ID": cfg.ABSENCE_ROLE_ID,
                "ABSENCE_CHANNEL_ID": cfg.ABSENCE_CHANNEL_ID,
                "STAFF_ALERT_CHANNEL_ID": cfg.STAFF_ALERT_CHANNEL_ID,
                "MIRROR_GUILD_ID": cfg.MIRROR_GUILD_ID,
                "MIRROR_CHANNEL_ID": cfg.MIRROR_CHANNEL_ID,
                "ABSENCE_WARNING_PERIOD": cfg.ABSENCE_WARNING_PERIOD,
                "BIRTHDAY_CHANNEL_ID": cfg.BIRTHDAY_CHANNEL_ID,
                "GIVEAWAY_CHANNEL_ID": cfg.GIVEAWAY_CHANNEL_ID,
                "ALLOWED_LOVE_REACTOR_CHANNELS": list(cfg.ALLOWED_LOVE_REACTOR_CHANNELS),
                "ALLOWED_CHANNELS": list(cfg.ALLOWED_CHANNELS),
                "ART_SHOWCASE_ID": cfg.ART_SHOWCASE_ID,
                "SERVER_FANART_ID": cfg.SERVER_FANART_ID,
                "STARBOARD_ID": cfg.STARBOARD_ID,
                "CUSTOM_EMOJI": cfg.CUSTOM_EMOJI,
                "SMALL_THUMBNAIL": cfg.SMALL_THUMBNAIL,
                "ABSENCE_RESTRICTED_CATEGORIES": list(cfg.ABSENCE_RESTRICTED_CATEGORIES),
            }
        # config.py not present (e.g. Streamlit Cloud) — return DB creds only;
        # Discord IDs will be populated from dashboard_settings.json overrides.
        return {
            "DB_HOST": creds["host"],
            "DB_PORT": creds["port"],
            "DB_USER": creds["user"],
            "DB_PASSWORD": creds["password"],
            "DB_NAME": creds["database"],
        }
    except Exception as exc:
        st.warning(f"Could not load bot config: {exc}")
        return {}


# ─── CC Bot defaults (matches cc.py) ──────────────────────────────────────────
CC_DEFAULTS = {
    "AUTHORIZED_USER": 766005564190359552,
    "STATUSES": [
        "Cooking up pastries",
        "HIII",
        "Attempting not to cry",
        "Need Help? Contact Mousse The Mouse",
        "I love Dixie so much <3",
    ],
    "TYPING_CPM": 190.0,
    "TYPING_MIN": 1.0,
    "TYPING_MAX": 12.0,
    "TYPING_RANDOM_MIN": 0.5,
    "TYPING_RANDOM_MAX": 2.0,
    "STATUS_UPDATE_MINUTES": 5,
}

# ─── Helpers ───────────────────────────────────────────────────────────────────

def _int_field(overrides: dict, key: str, fallback) -> int:
    return int(overrides.get(key, fallback) or 0)


def _float_field(overrides: dict, key: str, fallback) -> float:
    return float(overrides.get(key, fallback) or 0.0)


def _snowflake_input(label: str, value: int, key: str | None = None, help: str | None = None) -> int:
    """text_input wrapper for Discord snowflake IDs (too large for JS number_input)."""
    raw = st.text_input(label, value=str(value) if value else "", key=key, help=help, placeholder="Discord ID")
    if raw.strip():
        try:
            return int(raw.strip())
        except ValueError:
            st.error(f"{label}: must be a valid Discord ID (integer).")
    return value


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

check_auth()

settings = load_settings()
bot_cfg = load_bot_config()

# ─── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<h2 style='color:#ff69b4;margin-bottom:0;font-size:1.15rem'>&#127856; Cheesecake</h2>"
        "<p style='color:#ffb6c188;margin-top:2px;font-size:0.72em;text-transform:uppercase;letter-spacing:1.2px'>Admin Dashboard</p>",
        unsafe_allow_html=True,
    )
    st.divider()
    page = st.radio(
        "Navigation",
        [
            "Overview",
            "Bot Config",
            "CC Relay Bot",
            "Trigger Responses",
            "Absences",
            "Birthdays",
            "Events",
            "Giveaways",
            "Starboard",
            "Emergency Comms",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    if st.button("Log Out", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()
    st.caption("Changes require a bot restart.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Overview
# ══════════════════════════════════════════════════════════════════════════════
if page == "Overview":
    st.title("Overview")
    st.markdown("Live snapshot of the Cheesecake bot and its database.")

    # DB connectivity
    _, db_err = get_db()
    if db_err:
        st.error(f"Database unreachable: {db_err}")
    else:
        st.success("Database connected")

    st.divider()

    # Metric row
    col1, col2, col3, col4, col5 = st.columns(5)
    conn, err = get_db()
    if not err and conn:
        with conn.cursor() as cur:
            def _count(table):
                try:
                    cur.execute(f"SELECT COUNT(*) as n FROM {table}")
                    row = cur.fetchone()
                    return row["n"] if row else 0
                except Exception:
                    return "—"
            col1.metric("Triggers", _count("trigger_words"))
            col2.metric("Absences", _count("absences"))
            col3.metric("Birthdays", _count("birthdays"))
            col4.metric("Event Channels", _count("event_channels"))
            col5.metric("Giveaways", _count("giveaways"))
        conn.close()

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Channel IDs")
        if bot_cfg:
            st.json({
                "Absence": bot_cfg.get("ABSENCE_CHANNEL_ID"),
                "Staff Alert": bot_cfg.get("STAFF_ALERT_CHANNEL_ID"),
                "Birthday": bot_cfg.get("BIRTHDAY_CHANNEL_ID"),
                "Giveaway": bot_cfg.get("GIVEAWAY_CHANNEL_ID"),
                "Starboard": bot_cfg.get("STARBOARD_ID"),
                "Mirror": bot_cfg.get("MIRROR_CHANNEL_ID"),
            })
    with col_b:
        st.subheader("Key Settings")
        if bot_cfg:
            st.json({
                "Absence Warning Period": f"{bot_cfg.get('ABSENCE_WARNING_PERIOD')} days",
                "Allowed Response Channels": len(bot_cfg.get("ALLOWED_CHANNELS", [])),
                "Love Reactor Channels": len(bot_cfg.get("ALLOWED_LOVE_REACTOR_CHANNELS", [])),
                "Restricted Absence Categories": len(bot_cfg.get("ABSENCE_RESTRICTED_CATEGORIES", [])),
                "DB Host": bot_cfg.get("DB_HOST"),
                "DB Name": bot_cfg.get("DB_NAME"),
            })

    st.divider()
    st.subheader("Saved Overrides (dashboard_settings.json)")
    if settings:
        st.json(settings)
    else:
        st.caption("No saved overrides yet. Edit settings on other pages.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Bot Config
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Bot Config":
    st.title("Bot Configuration")
    st.info("Edits are saved to `dashboard_settings.json`. The bot reads overrides from that file on restart.")

    cfg_ov = settings.get("config", {})

    tab_ch, tab_roles, tab_absence, tab_art = st.tabs(
        ["Channels", "Roles", "Absence", "Starboard & Art"]
    )

    # ── Channels tab ──
    with tab_ch:
        st.subheader("Core Channel IDs")
        c1, c2 = st.columns(2)
        with c1:
            absence_ch = _snowflake_input("Absence Channel", _int_field(cfg_ov, "ABSENCE_CHANNEL_ID", bot_cfg.get("ABSENCE_CHANNEL_ID", 0)), key="absence_ch")
            staff_ch = _snowflake_input("Staff Alert Channel", _int_field(cfg_ov, "STAFF_ALERT_CHANNEL_ID", bot_cfg.get("STAFF_ALERT_CHANNEL_ID", 0)), key="staff_ch")
            mirror_ch = _snowflake_input("Mirror Channel", _int_field(cfg_ov, "MIRROR_CHANNEL_ID", bot_cfg.get("MIRROR_CHANNEL_ID", 0)), key="mirror_ch")
            mirror_guild = _snowflake_input("Mirror Guild", _int_field(cfg_ov, "MIRROR_GUILD_ID", bot_cfg.get("MIRROR_GUILD_ID", 0)), key="mirror_guild")
        with c2:
            birthday_ch = _snowflake_input("Birthday Channel", _int_field(cfg_ov, "BIRTHDAY_CHANNEL_ID", bot_cfg.get("BIRTHDAY_CHANNEL_ID", 0)), key="birthday_ch")
            giveaway_ch = _snowflake_input("Giveaway Channel", _int_field(cfg_ov, "GIVEAWAY_CHANNEL_ID", bot_cfg.get("GIVEAWAY_CHANNEL_ID", 0)), key="giveaway_ch")

        st.subheader("Allowed Auto-Response Channels")
        allowed_default = "\n".join(str(c) for c in cfg_ov.get("ALLOWED_CHANNELS", bot_cfg.get("ALLOWED_CHANNELS", [])))
        allowed_str = st.text_area("Channel IDs — one per line", value=allowed_default, height=130, key="allowed_ch")

        st.subheader("Love Reactor Channels")
        love_default = "\n".join(str(c) for c in cfg_ov.get("ALLOWED_LOVE_REACTOR_CHANNELS", bot_cfg.get("ALLOWED_LOVE_REACTOR_CHANNELS", [])))
        love_str = st.text_area("Channel IDs — one per line", value=love_default, height=100, key="love_ch")

        if st.button("Save Channels", type="primary", key="save_channels"):
            try:
                parsed_allowed = [int(x.strip()) for x in allowed_str.splitlines() if x.strip()]
                parsed_love = [int(x.strip()) for x in love_str.splitlines() if x.strip()]
                settings.setdefault("config", {}).update({
                    "ABSENCE_CHANNEL_ID": absence_ch,
                    "STAFF_ALERT_CHANNEL_ID": staff_ch,
                    "MIRROR_CHANNEL_ID": mirror_ch,
                    "MIRROR_GUILD_ID": mirror_guild,
                    "BIRTHDAY_CHANNEL_ID": birthday_ch,
                    "GIVEAWAY_CHANNEL_ID": giveaway_ch,
                    "ALLOWED_CHANNELS": parsed_allowed,
                    "ALLOWED_LOVE_REACTOR_CHANNELS": parsed_love,
                })
                save_settings(settings)
            except ValueError as exc:
                st.error(f"Invalid channel ID: {exc}")

    # ── Roles tab ──
    with tab_roles:
        st.subheader("Role IDs")
        absence_role = _snowflake_input(
            "Absence Role ID",
            _int_field(cfg_ov, "ABSENCE_ROLE_ID", bot_cfg.get("ABSENCE_ROLE_ID", 0)),
            key="absence_role",
            help="Role applied when a staff member marks themselves absent.",
        )
        if st.button("Save Roles", type="primary", key="save_roles"):
            settings.setdefault("config", {})["ABSENCE_ROLE_ID"] = absence_role
            save_settings(settings)

    # ── Absence tab ──
    with tab_absence:
        st.subheader("Absence Warning Settings")
        warning_days = st.number_input(
            "Warning Period (days)",
            value=_int_field(cfg_ov, "ABSENCE_WARNING_PERIOD", bot_cfg.get("ABSENCE_WARNING_PERIOD", 60)),
            min_value=1, max_value=365, step=1,
            help="Staff are warned if their absence exceeds this many days.",
        )
        st.subheader("Restricted Categories")
        st.caption("Absent staff cannot send messages in these Discord category IDs.")
        restricted_default = "\n".join(str(c) for c in cfg_ov.get("ABSENCE_RESTRICTED_CATEGORIES", bot_cfg.get("ABSENCE_RESTRICTED_CATEGORIES", [])))
        restricted_str = st.text_area("Category IDs — one per line", value=restricted_default, height=100, key="restricted_cats")

        if st.button("Save Absence Settings", type="primary", key="save_absence"):
            try:
                parsed_restricted = [int(x.strip()) for x in restricted_str.splitlines() if x.strip()]
                settings.setdefault("config", {}).update({
                    "ABSENCE_WARNING_PERIOD": warning_days,
                    "ABSENCE_RESTRICTED_CATEGORIES": parsed_restricted,
                })
                save_settings(settings)
            except ValueError as exc:
                st.error(f"Invalid category ID: {exc}")

    # ── Starboard & Art tab ──
    with tab_art:
        st.subheader("Starboard Channels")
        c1, c2 = st.columns(2)
        with c1:
            art_showcase = _snowflake_input("Art Showcase Channel", _int_field(cfg_ov, "ART_SHOWCASE_ID", bot_cfg.get("ART_SHOWCASE_ID", 0)), key="art_showcase")
            server_fanart = _snowflake_input("Server Fanart Channel", _int_field(cfg_ov, "SERVER_FANART_ID", bot_cfg.get("SERVER_FANART_ID", 0)), key="server_fanart")
        with c2:
            starboard = _snowflake_input("Starboard Channel", _int_field(cfg_ov, "STARBOARD_ID", bot_cfg.get("STARBOARD_ID", 0)), key="starboard_ch")

        st.subheader("Appearance")
        custom_emoji = st.text_input("Custom Starboard Emoji", value=cfg_ov.get("CUSTOM_EMOJI", bot_cfg.get("CUSTOM_EMOJI", "")))
        thumbnail_url = st.text_input("Server Thumbnail URL", value=cfg_ov.get("SMALL_THUMBNAIL", bot_cfg.get("SMALL_THUMBNAIL", "")))

        if thumbnail_url:
            st.image(thumbnail_url, width=120, caption="Preview")

        if st.button("Save Starboard Settings", type="primary", key="save_starboard"):
            settings.setdefault("config", {}).update({
                "ART_SHOWCASE_ID": art_showcase,
                "SERVER_FANART_ID": server_fanart,
                "STARBOARD_ID": starboard,
                "CUSTOM_EMOJI": custom_emoji,
                "SMALL_THUMBNAIL": thumbnail_url,
            })
            save_settings(settings)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: CC Relay Bot
# ══════════════════════════════════════════════════════════════════════════════
elif page == "CC Relay Bot":
    st.title("CC Relay Bot")
    st.markdown("Configure `cc.py` — the DM message relay utility.")
    st.info("Changes are saved to `dashboard_settings.json`. Restart `cc.py` to apply them.")

    cc_ov = settings.get("cc", {})

    tab_id, tab_typing = st.tabs(["Identity & Statuses", "Typing Simulation"])

    # ── Identity & Statuses ──
    with tab_id:
        st.subheader("Authorized User")
        auth_user = _snowflake_input(
            "Discord User ID",
            _int_field(cc_ov, "AUTHORIZED_USER", CC_DEFAULTS["AUTHORIZED_USER"]),
            key="auth_user",
            help="Only messages from this user are relayed. Changing this restricts bot access.",
        )

        st.subheader("Watching Statuses")
        st.caption("The bot cycles through these 'Watching …' statuses every few minutes.")
        statuses_str = st.text_area(
            "Statuses — one per line",
            value="\n".join(cc_ov.get("STATUSES", CC_DEFAULTS["STATUSES"])),
            height=180,
        )

        status_interval = st.number_input(
            "Rotation interval (minutes)",
            value=_int_field(cc_ov, "STATUS_UPDATE_MINUTES", CC_DEFAULTS["STATUS_UPDATE_MINUTES"]),
            min_value=1, max_value=60, step=1,
        )

        if st.button("Save Identity & Statuses", type="primary", key="save_cc_id"):
            parsed_statuses = [s.strip() for s in statuses_str.splitlines() if s.strip()]
            if not parsed_statuses:
                st.error("At least one status is required.")
            else:
                settings.setdefault("cc", {}).update({
                    "AUTHORIZED_USER": auth_user,
                    "STATUSES": parsed_statuses,
                    "STATUS_UPDATE_MINUTES": status_interval,
                })
                save_settings(settings)

    # ── Typing Simulation ──
    with tab_typing:
        st.subheader("Typing Simulation")
        st.markdown(
            "The relay bot simulates realistic typing before each message. "
            "Duration is calculated as `(len / CPM × 60) × random_factor`, "
            "clamped between **Min** and **Max** seconds."
        )
        cpm = st.slider(
            "Characters Per Minute (CPM)",
            min_value=50, max_value=600,
            value=int(_float_field(cc_ov, "TYPING_CPM", CC_DEFAULTS["TYPING_CPM"])),
            step=10,
        )

        c1, c2 = st.columns(2)
        with c1:
            t_min = st.number_input("Min duration (s)", value=_float_field(cc_ov, "TYPING_MIN", CC_DEFAULTS["TYPING_MIN"]), min_value=0.1, max_value=10.0, step=0.1)
            r_min = st.number_input("Random factor min", value=_float_field(cc_ov, "TYPING_RANDOM_MIN", CC_DEFAULTS["TYPING_RANDOM_MIN"]), min_value=0.1, max_value=5.0, step=0.1)
        with c2:
            t_max = st.number_input("Max duration (s)", value=_float_field(cc_ov, "TYPING_MAX", CC_DEFAULTS["TYPING_MAX"]), min_value=1.0, max_value=60.0, step=0.5)
            r_max = st.number_input("Random factor max", value=_float_field(cc_ov, "TYPING_RANDOM_MAX", CC_DEFAULTS["TYPING_RANDOM_MAX"]), min_value=0.1, max_value=10.0, step=0.1)

        if t_min >= t_max:
            st.warning("Min duration must be less than max duration.")
        if r_min >= r_max:
            st.warning("Random factor min must be less than max.")

        # Live preview
        import random, math
        if cpm > 0:
            example_len = 80
            base = (example_len / cpm) * 60
            lo = max(t_min, min(base * r_min, t_max))
            hi = max(t_min, min(base * r_max, t_max))
            st.info(f"Example: an 80-char message will take **{lo:.1f}s – {hi:.1f}s** to \"type\".")

        if st.button("Save Typing Settings", type="primary", key="save_cc_typing"):
            if t_min >= t_max or r_min >= r_max:
                st.error("Fix the range errors above before saving.")
            else:
                settings.setdefault("cc", {}).update({
                    "TYPING_CPM": cpm,
                    "TYPING_MIN": t_min,
                    "TYPING_MAX": t_max,
                    "TYPING_RANDOM_MIN": r_min,
                    "TYPING_RANDOM_MAX": r_max,
                })
                save_settings(settings)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Trigger Responses
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Trigger Responses":
    st.title("Trigger Responses")
    st.markdown("Manage the **database-backed** trigger → response pairs used by `ResponseHandler`.")

    tab_view, tab_add = st.tabs(["View & Remove", "Add New"])

    with tab_view:
        if st.button("Refresh", key="refresh_triggers"):
            st.cache_data.clear()

        rows = query_db("SELECT id, trigger_text, response_text FROM trigger_words ORDER BY id")

        if not rows:
            st.info("No custom triggers in the database yet.")
        else:
            st.caption(f"**{len(rows)} trigger(s)** stored in the database")

            # Search filter
            search = st.text_input("Filter triggers", placeholder="Search by trigger text…")
            filtered = [r for r in rows if not search or search.lower() in r["trigger_text"].lower()]

            for row in filtered:
                with st.expander(f"#{row['id']}  —  `{row['trigger_text'][:70]}`"):
                    col_t, col_r = st.columns([1, 2])
                    col_t.markdown("**Trigger**")
                    col_t.code(row["trigger_text"])
                    col_r.markdown("**Response**")
                    col_r.markdown(row["response_text"])
                    if st.button(f"Delete #{row['id']}", key=f"del_trig_{row['id']}"):
                        err = db_execute("DELETE FROM trigger_words WHERE id=%s", (row["id"],))
                        if err:
                            st.error(err)
                        else:
                            st.success(f"Deleted trigger #{row['id']}")
                            st.cache_data.clear()
                            st.rerun()

    with tab_add:
        st.subheader("Add a New Trigger Response")
        new_trigger = st.text_input("Trigger Text", placeholder="e.g. how do i join", help="Case-insensitive partial match.")
        new_response = st.text_area("Response Text", placeholder="Type the bot's reply here…", height=130)

        if st.button("Add Trigger", type="primary", key="add_trigger"):
            if not new_trigger.strip():
                st.error("Trigger text cannot be empty.")
            elif not new_response.strip():
                st.error("Response text cannot be empty.")
            else:
                err = db_execute(
                    "INSERT INTO trigger_words (trigger_text, response_text) VALUES (%s, %s)",
                    (new_trigger.strip(), new_response.strip()),
                )
                if err:
                    st.error(f"Database error: {err}")
                else:
                    st.success(f"Added trigger: `{new_trigger.strip()}`")
                    st.cache_data.clear()
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Absences
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Absences":
    st.title("Absence Tracker")

    if st.button("Refresh", key="refresh_abs"):
        st.cache_data.clear()

    rows = query_db(
        "SELECT id, user_id, message, start_time, last_warned FROM absences ORDER BY start_time ASC"
    )

    if not rows:
        st.success("No active absences right now.")
    else:
        st.markdown(f"**{len(rows)} active absence(s)**")

        import pandas as pd

        df = pd.DataFrame(rows)
        df["user_id"] = df["user_id"].astype(str)
        df["start_time"] = pd.to_datetime(df["start_time"])
        now = datetime.utcnow()
        df["days_absent"] = (now - df["start_time"]).dt.days

        warning_period = settings.get("config", {}).get(
            "ABSENCE_WARNING_PERIOD",
            bot_cfg.get("ABSENCE_WARNING_PERIOD", 60),
        )
        df["overdue"] = df["days_absent"] > warning_period

        st.dataframe(
            df[["id", "user_id", "message", "start_time", "days_absent", "last_warned", "overdue"]],
            use_container_width=True,
            column_config={
                "id": "ID",
                "user_id": "User ID",
                "message": "Reason",
                "start_time": st.column_config.DatetimeColumn("Since (UTC)"),
                "days_absent": "Days Absent",
                "last_warned": st.column_config.DatetimeColumn("Last Warned"),
                "overdue": st.column_config.CheckboxColumn("Overdue"),
            },
        )

        overdue = df[df["overdue"]]
        if not overdue.empty:
            st.warning(f"{len(overdue)} absence(s) exceed the {warning_period}-day warning period.")

        st.divider()
        st.subheader("Remove an Absence")
        st.caption("Use this to manually clear a staff member's absence from the database.")
        del_id = st.number_input("Absence ID", min_value=1, step=1, key="del_abs_id")
        if st.button("Remove Absence", type="secondary", key="btn_del_abs"):
            err = db_execute("DELETE FROM absences WHERE id=%s", (int(del_id),))
            if err:
                st.error(err)
            else:
                st.success(f"Removed absence #{int(del_id)}")
                st.cache_data.clear()
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Birthdays
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Birthdays":
    st.title("Birthday Manager")

    if st.button("Refresh", key="refresh_bdays"):
        st.cache_data.clear()

    rows = query_db("SELECT user_id, birthday FROM birthdays ORDER BY birthday")

    tab_list, tab_edit = st.tabs(["All Birthdays", "Add / Remove"])

    with tab_list:
        if not rows:
            st.info("No birthdays saved yet.")
        else:
            import pandas as pd

            df = pd.DataFrame(rows)
            df["user_id"] = df["user_id"].astype(str)

            today = date.today()

            def _days_until(bday_str: str) -> int:
                try:
                    day, month = map(int, bday_str.split("/"))
                    bday = date(today.year, month, day)
                    if bday < today:
                        bday = date(today.year + 1, month, day)
                    return (bday - today).days
                except Exception:
                    return 999

            df["days_until"] = df["birthday"].apply(_days_until)
            df = df.sort_values("days_until")

            st.dataframe(
                df[["user_id", "birthday", "days_until"]],
                use_container_width=True,
                column_config={
                    "user_id": "User ID",
                    "birthday": "Birthday (DD/MM)",
                    "days_until": st.column_config.NumberColumn("Days Until", format="%d days"),
                },
            )

            soon = df[df["days_until"] <= 7]
            if not soon.empty:
                st.info(f"{len(soon)} birthday(s) within the next 7 days!")

    with tab_edit:
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("Add / Update Birthday")
            new_uid = st.text_input("Discord User ID", key="add_bday_uid")
            new_bday = st.text_input("Birthday (DD/MM)", placeholder="25/12", key="add_bday_date")
            if st.button("Save Birthday", type="primary", key="btn_add_bday"):
                try:
                    uid = int(new_uid.strip())
                    datetime.strptime(new_bday.strip(), "%d/%m")
                    err = db_execute(
                        "INSERT INTO birthdays (user_id, birthday) VALUES (%s, %s) "
                        "ON DUPLICATE KEY UPDATE birthday=%s",
                        (uid, new_bday.strip(), new_bday.strip()),
                    )
                    if err:
                        st.error(err)
                    else:
                        st.success(f"Saved birthday for `{uid}`")
                        st.cache_data.clear()
                        st.rerun()
                except ValueError:
                    st.error("Invalid input — User ID must be a number and date must be DD/MM.")

        with c2:
            st.subheader("Remove Birthday")
            del_uid = st.text_input("Discord User ID to remove", key="del_bday_uid")
            if st.button("Remove", type="secondary", key="btn_del_bday"):
                try:
                    uid = int(del_uid.strip())
                    err = db_execute("DELETE FROM birthdays WHERE user_id=%s", (uid,))
                    if err:
                        st.error(err)
                    else:
                        st.success(f"Removed birthday for `{uid}`")
                        st.cache_data.clear()
                        st.rerun()
                except ValueError:
                    st.error("Invalid User ID.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Events
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Events":
    st.title("Events")

    if st.button("Refresh", key="refresh_events"):
        st.cache_data.clear()

    tab_ch, tab_votes, tab_cfg = st.tabs(["Event Channels", "Votes", "Settings"])

    with tab_ch:
        rows = query_db(
            "SELECT channel_id, name, created_by, created_at FROM event_channels ORDER BY created_at DESC"
        )
        if not rows:
            st.info("No event channels found.")
        else:
            import pandas as pd
            df = pd.DataFrame(rows)
            df["channel_id"] = df["channel_id"].astype(str)
            df["created_by"] = df["created_by"].astype(str)
            df["created_at"] = pd.to_datetime(df["created_at"])
            st.dataframe(
                df,
                use_container_width=True,
                column_config={
                    "channel_id": "Channel ID",
                    "name": "Name",
                    "created_by": "Created By",
                    "created_at": st.column_config.DatetimeColumn("Created At"),
                },
            )

    with tab_votes:
        vote_rows = query_db(
            "SELECT channel_id, COUNT(*) AS vote_count "
            "FROM event_votes GROUP BY channel_id ORDER BY vote_count DESC"
        )
        if not vote_rows:
            st.info("No votes recorded yet.")
        else:
            import pandas as pd
            df = pd.DataFrame(vote_rows)
            df["channel_id"] = df["channel_id"].astype(str)
            st.bar_chart(df.set_index("channel_id")["vote_count"], color="#ff69b4")
            st.dataframe(
                df,
                use_container_width=True,
                column_config={
                    "channel_id": "Channel ID",
                    "vote_count": "Total Votes",
                },
            )

    with tab_cfg:
        st.subheader("Event Cog Configuration")
        st.info("These values override the hardcoded defaults in `cogs/event.py` after bot restart.")
        ev_ov = settings.get("events", {})

        events_cat = _snowflake_input("Events Category ID", _int_field(ev_ov, "EVENTS_CATEGORY_ID", 1412722642321932298), key="events_cat")
        vote_log = _snowflake_input("Vote Log Channel ID", _int_field(ev_ov, "VOTE_LOG_CHANNEL_ID", 1459105274332844053), key="vote_log")
        commands_ch = _snowflake_input("Commands Channel ID", _int_field(ev_ov, "COMMANDS_CHANNEL_ID", 1431691032516366337), key="commands_ch")
        min_join = st.number_input(
            "Minimum account age to vote (days)",
            value=_int_field(ev_ov, "MIN_JOIN_DAYS", 30),
            min_value=0, max_value=365, step=1,
        )

        if st.button("Save Event Settings", type="primary", key="save_events"):
            settings.setdefault("events", {}).update({
                "EVENTS_CATEGORY_ID": events_cat,
                "VOTE_LOG_CHANNEL_ID": vote_log,
                "COMMANDS_CHANNEL_ID": commands_ch,
                "MIN_JOIN_DAYS": min_join,
            })
            save_settings(settings)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Giveaways
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Giveaways":
    st.title("Giveaways")

    if st.button("Refresh", key="refresh_giveaways"):
        st.cache_data.clear()

    rows = query_db(
        "SELECT id, host_id, channel_id, duration_minutes, winners, prizes, message, start_time, end_time "
        "FROM giveaways ORDER BY start_time DESC"
    )

    if not rows:
        st.info("No giveaways found.")
    else:
        import pandas as pd

        df = pd.DataFrame(rows)
        df["host_id"] = df["host_id"].astype(str)
        df["channel_id"] = df["channel_id"].astype(str)
        df["start_time"] = pd.to_datetime(df["start_time"])
        df["end_time"] = pd.to_datetime(df["end_time"])
        now_dt = pd.Timestamp(datetime.utcnow())
        df["active"] = df["end_time"] > now_dt

        active_df = df[df["active"]]
        past_df = df[~df["active"]]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total", len(df))
        c2.metric("Active", len(active_df))
        c3.metric("Past", len(past_df))

        if not active_df.empty:
            st.subheader("Active Giveaways")
            st.dataframe(
                active_df[["id", "prizes", "winners", "duration_minutes", "end_time", "host_id", "channel_id"]],
                use_container_width=True,
                column_config={
                    "id": "ID",
                    "prizes": "Prize(s)",
                    "winners": "# Winners",
                    "duration_minutes": "Duration (min)",
                    "end_time": st.column_config.DatetimeColumn("Ends At (UTC)"),
                    "host_id": "Host ID",
                    "channel_id": "Channel ID",
                },
            )

        if not past_df.empty:
            st.subheader("Past Giveaways")
            st.dataframe(
                past_df[["id", "prizes", "winners", "start_time", "end_time", "host_id"]],
                use_container_width=True,
                column_config={
                    "id": "ID",
                    "prizes": "Prize(s)",
                    "winners": "# Winners",
                    "start_time": st.column_config.DatetimeColumn("Started (UTC)"),
                    "end_time": st.column_config.DatetimeColumn("Ended (UTC)"),
                    "host_id": "Host ID",
                },
            )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Starboard
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Starboard":
    st.title("Starboard")

    if st.button("Refresh", key="refresh_starboard"):
        st.cache_data.clear()

    rows = query_db(
        "SELECT id, message_id, author_id, posted_at FROM starboard ORDER BY posted_at DESC LIMIT 200"
    )

    c1, c2 = st.columns(2)
    c1.metric("Total Entries (last 200)", len(rows))

    if rows:
        import pandas as pd

        df = pd.DataFrame(rows)
        df["message_id"] = df["message_id"].astype(str)
        df["author_id"] = df["author_id"].astype(str)
        df["posted_at"] = pd.to_datetime(df["posted_at"])

        # Top contributors chart
        top = (
            df.groupby("author_id")
            .size()
            .reset_index(name="entries")
            .sort_values("entries", ascending=False)
            .head(10)
        )
        c2.metric("Unique Contributors", df["author_id"].nunique())

        if not top.empty:
            st.subheader("Top 10 Contributors")
            st.bar_chart(top.set_index("author_id")["entries"], color="#ff69b4")

        st.subheader("Recent Entries")
        st.dataframe(
            df[["id", "message_id", "author_id", "posted_at"]],
            use_container_width=True,
            column_config={
                "id": "ID",
                "message_id": "Message ID",
                "author_id": "Author ID",
                "posted_at": st.column_config.DatetimeColumn("Posted At (UTC)"),
            },
        )
    else:
        st.info("No starboard entries yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Emergency Commissions
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Emergency Comms":
    st.title("Emergency Commissions")

    if st.button("Refresh", key="refresh_ec"):
        st.cache_data.clear()

    # Try to load the applications table from the DB cog
    rows = query_db(
        "SELECT id, applicant_id, applicant_mention, emergency_matter, slots, info, status, created_at "
        "FROM emergency_applications ORDER BY created_at DESC"
    )

    if not rows:
        st.info("No emergency commission applications found (table may not exist yet).")
    else:
        import pandas as pd

        df = pd.DataFrame(rows)
        df["applicant_id"] = df["applicant_id"].astype(str)
        df["created_at"] = pd.to_datetime(df["created_at"])

        c1, c2, c3 = st.columns(3)
        c1.metric("Total", len(df))
        c2.metric("Accepted", len(df[df["status"] == "accepted"]))
        c3.metric("Rejected", len(df[df["status"] == "rejected"]))

        # Status filter
        status_filter = st.selectbox("Filter by status", ["all", "pending", "accepted", "rejected"])
        filtered = df if status_filter == "all" else df[df["status"] == status_filter]

        st.dataframe(
            filtered[["id", "applicant_id", "applicant_mention", "emergency_matter", "slots", "status", "created_at"]],
            use_container_width=True,
            column_config={
                "id": "ID",
                "applicant_id": "User ID",
                "applicant_mention": "Mention",
                "emergency_matter": "Emergency",
                "slots": "Slots",
                "status": "Status",
                "created_at": st.column_config.DatetimeColumn("Submitted (UTC)"),
            },
        )

    st.divider()
    st.subheader("Channel IDs (Emergency Cog)")
    ec_ov = settings.get("emergency", {})

    c1, c2 = st.columns(2)
    with c1:
        ec_channel = st.number_input("Emergency Rules Channel", value=_int_field(ec_ov, "EMERGENCY_CHANNEL_ID", 1435610754425294940), step=1, format="%d")
        staff_review = st.number_input("Staff Review Channel", value=_int_field(ec_ov, "STAFF_REVIEW_CHANNEL_ID", 1431344160840880159), step=1, format="%d")
    with c2:
        posting_ch = st.number_input("Approved Posting Channel", value=_int_field(ec_ov, "POSTING_CHANNEL_ID", 1245431550942904341), step=1, format="%d")
        logs_ch = st.number_input("Logs Channel", value=_int_field(ec_ov, "LOGS_CHANNEL_ID", 1430575592503378142), step=1, format="%d")

    if st.button("Save Emergency Settings", type="primary", key="save_ec"):
        settings.setdefault("emergency", {}).update({
            "EMERGENCY_CHANNEL_ID": ec_channel,
            "STAFF_REVIEW_CHANNEL_ID": staff_review,
            "POSTING_CHANNEL_ID": posting_ch,
            "LOGS_CHANNEL_ID": logs_ch,
        })
        save_settings(settings)
