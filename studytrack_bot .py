#!/usr/bin/env python3
"""
StudyTrack Telegram Bot
FIXED: Uses GET params (URL query string) instead of POST body.
       This bypasses mod_security/proxy POST blocking on shared hosting.

Setup: pip install pyTelegramBotAPI requests
Run:   python studytrack_bot.py
"""

import telebot, requests, hashlib, hmac as hmac_lib, sys, threading, time
from datetime import datetime
from telebot.types import (InlineKeyboardMarkup, InlineKeyboardButton,
                           ReplyKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardRemove)

# ─── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN  = "8600643569:AAHquV7kNofsBeLCBAgyiyCgmHlumJwYbXw"
SITE_URL   = "https://studytrack.edurx.icu/studytrack"
API_URL    = f"{SITE_URL}/api/telegram-bot.php"
ADMIN_URL  = f"{SITE_URL}/api/admin-bot.php"
BOT_SECRET = "abc123"

# /start type කළාම ID show වෙයි — add කරන්න
ADMIN_IDS = []  # e.g. [123456789]

# ─── Bot ──────────────────────────────────────────────────────────────────────
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ─── State ────────────────────────────────────────────────────────────────────
states = {}
def ss(uid, state, data=None): states[uid] = {"state": state, "data": data or {}}
def gs(uid): return states.get(uid, {"state": None, "data": {}})
def cs(uid): states.pop(uid, None)


# ─── Loading Animation System ─────────────────────────────────────────────────
# Telegram built-in sticker file_ids for loading animations
# These are free animated stickers from Telegram's official packs
LOADING_STICKERS = [
    "CAACAgIAAxkBAAEKkh9mO6nNNHGKNXqAv1ZGJu5O3TDkfAAC2g8AAifWGEuKn-3LvAb0LTQE",  # spinning
    "CAACAgIAAxkBAAEKkiBmO6nkXJXm0NTmZSxFJd-xvfbdTQACrA8AAifWGEuRPGj5TvHPRTQE",  # loading dots
]

# Simple text-based loading frames (fallback)
LOADING_FRAMES = ["⏳", "⌛"]

def show_loading(cid, text="Loading..."):
    """Send a loading message and return its message_id for later deletion."""
    try:
        m = bot.send_message(cid, f"⏳ <i>{text}</i>")
        return m.message_id
    except Exception:
        return None

def delete_msg(cid, msg_id):
    """Safely delete a message."""
    if msg_id:
        try:
            bot.delete_message(cid, msg_id)
        except Exception:
            pass

def loading_action(cid, action_type="typing"):
    """Show Telegram typing/upload action."""
    try:
        bot.send_chat_action(cid, action_type)
    except Exception:
        pass

# ─── API — uses GET params to avoid POST body blocking on shared hosting ──────
def api(action, data=None, tg_id=0):
    """Send all params as URL query string (GET) — avoids mod_security blocking POST body."""
    params = {"action": action, "telegram_id": str(tg_id)}
    if data:
        params.update({str(k): str(v) for k, v in data.items()})
    try:
        # Use GET request with params in URL
        r = requests.get(API_URL, params=params, timeout=15)
        try:
            result = r.json()
            if not result.get("success"):
                err = result.get("message", "?")
                if err != "not_linked":
                    print(f"[API] {action} → {err} | {result.get('debug','')}")
            return result
        except Exception:
            print(f"[API] Non-JSON ({r.status_code}): {r.text[:300]}")
            return {"success": False, "message": f"Server error: {r.text[:100]}"}
    except Exception as e:
        print(f"[API] Request failed: {e}")
        return {"success": False, "message": str(e)}

def adm(action, data=None):
    payload = {"secret": BOT_SECRET, "action": action}
    if data: payload.update(data)
    try:
        r = requests.post(ADMIN_URL, data=payload, timeout=15)
        return r.json()
    except Exception as e:
        return {"success": False, "message": str(e)}

# ─── Helpers ──────────────────────────────────────────────────────────────────
def is_admin(uid): return not ADMIN_IDS or uid in ADMIN_IDS

def fmt(mins):
    mins = int(mins or 0)
    if not mins: return "0m"
    h, m = divmod(mins, 60)
    return f"{h}h {m}m" if h and m else f"{h}h" if h else f"{m}m"

def link_url(uid, name):
    h = hmac_lib.new(BOT_TOKEN.encode(), f"tg_link:{uid}".encode(), hashlib.sha256).hexdigest()
    return f"{SITE_URL}/telegram-link.php?tg={uid}&name={name}&hash={h}"

def send_not_linked(cid, uid, name):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔗 Link My Account", url=link_url(uid, name)))
    bot.send_message(cid,
        "❌ <b>Account Not Linked</b>\n\n"
        "Your StudyTrack account is not connected to this bot.\n\n"
        "<b>How to link:</b>\n"
        "1. Tap the button below\n"
        "2. Log in to StudyTrack\n"
        "3. Your account will be connected automatically",
        reply_markup=kb)

def check(res, cid, uid, name):
    if not res.get("success"):
        if res.get("message") == "not_linked":
            send_not_linked(cid, uid, name); return False
        bot.send_message(cid, f"❌ Error: {res.get('message', 'Unknown error')}")
        return False
    return True

PE = {"high": "🔴", "medium": "🟡", "low": "🟢"}

# ─── Keyboards ────────────────────────────────────────────────────────────────
def main_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📊 Summary"),      KeyboardButton("📝 Log Study"),
        KeyboardButton("✅ Tasks"),         KeyboardButton("📚 Marks"),
        KeyboardButton("🎯 Goals"),         KeyboardButton("🔔 Notifications"),
        KeyboardButton("📈 Weekly Stats"), KeyboardButton("🔥 Streak"),
        KeyboardButton("👤 My Profile"),   KeyboardButton("⚙️ Settings"),
        KeyboardButton("🔗 Link Account"), KeyboardButton("🏆 Leaderboard"),
        KeyboardButton("❓ Help"),
    )
    return kb

def admin_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("👥 Users"),         KeyboardButton("📊 Site Stats"),
        KeyboardButton("📢 Broadcast"),     KeyboardButton("📣 Announce"),
        KeyboardButton("🔔 Notify User"),   KeyboardButton("📋 Weekly Report"),
        KeyboardButton("🔗 Linked Users"),  KeyboardButton("⬅️ User Mode"),
    )
    return kb

def cancel_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("❌ Cancel"))
    return kb

# ══════════════════════════════════════════════════════════════════════════════
#  START / HELP / ADMIN
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    uid  = msg.from_user.id
    name = msg.from_user.first_name or "Student"
    extra = (f"\n\n🛡️ Admin mode active. Type /admin."
             if is_admin(uid) and ADMIN_IDS else
             f"\n\n💡 <b>Your Telegram ID:</b> <code>{uid}</code>")
    bot.send_message(msg.chat.id,
        f"👋 <b>Hello, {name}!</b>\n\n"
        f"Welcome to <b>StudyTrack Bot</b>!\n\n"
        f"Tap <b>🔗 Link Account</b> to connect your StudyTrack account.{extra}",
        reply_markup=main_kb())

@bot.message_handler(commands=["admin"])
def cmd_admin(msg):
    if not is_admin(msg.from_user.id):
        bot.send_message(msg.chat.id, "❌ No admin access."); return
    bot.send_message(msg.chat.id, "🛡️ <b>Admin Panel</b>", reply_markup=admin_kb())

@bot.message_handler(func=lambda m: m.text in ["❓ Help", "/help"])
def cmd_help(msg):
    bot.send_message(msg.chat.id,
        "📖 <b>StudyTrack Bot — Help</b>\n\n"
        "📊 Summary — Today's study summary\n"
        "📝 Log Study — Record a study session\n"
        "✅ Tasks — Add / complete / delete tasks\n"
        "📚 Marks — Add / delete exam results\n"
        "🎯 Goals — View / add goals\n"
        "🔔 Notifications — View notifications\n"
        "📈 Weekly Stats — Last 7 days\n"
        "🔥 Streak — Your study streak\n"
        "👤 My Profile — Profile overview\n"
        "⚙️ Settings — Name, goal, sessions\n"
        "🔗 Link Account — Connect your account")

# ══════════════════════════════════════════════════════════════════════════════
#  LINK ACCOUNT
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🔗 Link Account")
def msg_link(msg):
    send_not_linked(msg.chat.id, msg.from_user.id, msg.from_user.first_name or "User")

@bot.callback_query_handler(func=lambda c: c.data == "do_link")
def cb_link(c):
    bot.answer_callback_query(c.id)
    send_not_linked(c.message.chat.id, c.from_user.id, c.from_user.first_name or "User")

# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "📊 Summary")
def user_summary(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Fetching your today's summary...")
    res = api("today_summary", tg_id=uid)
    delete_msg(msg.chat.id, lmid)
    if not check(res, msg.chat.id, uid, name): return
    n = res["name"]; tot = res["total_minutes"]; g = res["goal_minutes"]
    pct = min(100, int(tot/g*100)) if g else 0
    bar = "█"*(pct//10) + "░"*(10-pct//10)
    txt = (f"📊 <b>{n}'s Today</b> — {datetime.now().strftime('%Y-%m-%d')}\n\n"
           f"⏱️ <b>{fmt(tot)}</b> / {fmt(g)}\n[{bar}] {pct}%\n"
           f"{'🎉 Goal met!' if res['goal_met'] else '💪 Keep going!'}\n\n")
    sess = res.get("sessions", [])
    if sess:
        txt += "📚 <b>Sessions:</b>\n"
        for s in sess:
            txt += f"  • {s['subject_name']} — {fmt(s['duration_minutes'])}"
            if s.get("notes"): txt += f" <i>({s['notes'][:30]})</i>"
            txt += "\n"
    else:
        txt += "📭 <i>No sessions today. Tap \"📝 Log Study\"!</i>"
    bot.send_message(msg.chat.id, txt)

# ══════════════════════════════════════════════════════════════════════════════
#  LOG STUDY
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "📝 Log Study")
def log_start(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Loading your subjects...")
    res = api("get_subjects", tg_id=uid)
    delete_msg(msg.chat.id, lmid)
    if not check(res, msg.chat.id, uid, name): return
    subjects = res.get("subjects", [])
    ss(uid, "log_subject", {"subjects": subjects})
    if subjects:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for s in subjects[:8]: kb.add(KeyboardButton(s["name"]))
        kb.add(KeyboardButton("➕ New Subject"), KeyboardButton("❌ Cancel"))
        bot.send_message(msg.chat.id, "📝 <b>Log Study</b>\n\nSelect a subject:", reply_markup=kb)
    else:
        bot.send_message(msg.chat.id, "📝 <b>Log Study</b>\n\nType subject name:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "log_subject")
def log_subject(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel":
        cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    if msg.text == "➕ New Subject":
        ss(uid, "log_new_subject", gs(uid)["data"])
        bot.send_message(msg.chat.id, "Type new subject name:", reply_markup=cancel_kb()); return
    d = gs(uid)["data"]; d["subject"] = msg.text.strip()
    ss(uid, "log_minutes", d); _ask_minutes(msg.chat.id, msg.text.strip())

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "log_new_subject")
def log_new_subject(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel":
        cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    d = gs(uid)["data"]; d["subject"] = msg.text.strip()
    ss(uid, "log_minutes", d); _ask_minutes(msg.chat.id, msg.text.strip())

def _ask_minutes(cid, subj):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    for t in ["30","45","60","90","120","180"]: kb.add(KeyboardButton(t))
    kb.add(KeyboardButton("❌ Cancel"))
    bot.send_message(cid, f"<b>{subj}</b> — How many minutes?", reply_markup=kb)

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "log_minutes")
def log_minutes(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel":
        cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    try: mins = int(msg.text.strip()); assert 1 <= mins <= 600
    except: bot.send_message(msg.chat.id, "❌ Enter a valid number (1–600)."); return
    d = gs(uid)["data"]; d["minutes"] = mins
    ss(uid, "log_notes", d)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("⏭️ Skip"), KeyboardButton("❌ Cancel"))
    bot.send_message(msg.chat.id, "Add a note? (optional)", reply_markup=kb)

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "log_notes")
def log_notes(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    if msg.text == "❌ Cancel":
        cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    d = gs(uid)["data"]; notes = "" if msg.text == "⏭️ Skip" else msg.text.strip(); cs(uid)
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Saving your study session...")
    res = api("log_session", {"subject": d["subject"], "minutes": d["minutes"], "notes": notes}, uid)
    delete_msg(msg.chat.id, lmid)
    if not check(res, msg.chat.id, uid, name): return
    bot.send_message(msg.chat.id,
        f"✅ <b>Session Logged!</b>\n\n📚 {d['subject']}\n⏱️ {fmt(d['minutes'])}"
        + (f"\n📝 {notes}" if notes else ""), reply_markup=main_kb())

# ══════════════════════════════════════════════════════════════════════════════
#  TASKS
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "✅ Tasks")
def tasks_menu(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Loading your tasks...")
    res = api("get_tasks", {"filter": "pending"}, uid)
    delete_msg(msg.chat.id, lmid)
    if not check(res, msg.chat.id, uid, name): return
    tasks = res.get("tasks", [])
    txt = f"✅ <b>Pending Tasks ({len(tasks)})</b>\n\n"
    if tasks:
        for i, t in enumerate(tasks, 1):
            txt += f"{i}. {PE.get(t.get('priority','medium'),'🟡')} {t['title']}"
            if t.get("due_date"): txt += f" 📅 {t['due_date']}"
            txt += "\n"
    else:
        txt += "🎉 <i>No pending tasks!</i>"
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("➕ Add",      callback_data="task_add"),
           InlineKeyboardButton("📋 All",      callback_data="task_all"),
           InlineKeyboardButton("✔️ Complete", callback_data="task_complete"),
           InlineKeyboardButton("🗑 Delete",   callback_data="task_delete"))
    bot.send_message(msg.chat.id, txt, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "task_add")
def cb_task_add(c):
    bot.answer_callback_query(c.id); ss(c.from_user.id, "task_title")
    bot.send_message(c.message.chat.id, "➕ Enter task title:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "task_title")
def task_title(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel":
        cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    ss(uid, "task_priority", {"title": msg.text.strip()})
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("🔴 High", callback_data="tp_high"),
           InlineKeyboardButton("🟡 Medium", callback_data="tp_medium"),
           InlineKeyboardButton("🟢 Low", callback_data="tp_low"))
    bot.send_message(msg.chat.id, f"Priority for: <b>{msg.text.strip()}</b>", reply_markup=ReplyKeyboardRemove())
    bot.send_message(msg.chat.id, "Select:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("tp_"))
def cb_tp(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id; name = c.from_user.first_name or "User"
    p = c.data[3:]; d = gs(uid)["data"]; cs(uid)
    res = api("add_task", {"title": d["title"], "priority": p}, uid)
    if not check(res, c.message.chat.id, uid, name): return
    bot.send_message(c.message.chat.id, f"✅ <b>Task Added!</b>\n\n{PE.get(p,'🟡')} {d['title']}", reply_markup=main_kb())

@bot.callback_query_handler(func=lambda c: c.data == "task_all")
def cb_task_all(c):
    bot.answer_callback_query(c.id)
    res = api("get_tasks", {"filter": "all"}, c.from_user.id)
    tasks = res.get("tasks", [])
    txt = f"📋 <b>All Tasks ({len(tasks)})</b>\n\n"
    for i, t in enumerate(tasks, 1): txt += f"{i}. {PE.get(t.get('priority','medium'),'🟡')} {t['title']}\n"
    bot.send_message(c.message.chat.id, txt or "No tasks.", reply_markup=main_kb())

@bot.callback_query_handler(func=lambda c: c.data == "task_complete")
def cb_task_complete(c):
    bot.answer_callback_query(c.id)
    res = api("get_tasks", {"filter": "pending"}, c.from_user.id)
    tasks = res.get("tasks", [])
    if not tasks: bot.send_message(c.message.chat.id, "✅ No pending tasks!", reply_markup=main_kb()); return
    kb = InlineKeyboardMarkup(row_width=1)
    for t in tasks[:8]: kb.add(InlineKeyboardButton(f"✔️ {t['title'][:45]}", callback_data=f"done_{t['id']}"))
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="xcl"))
    bot.send_message(c.message.chat.id, "Select task to complete:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("done_"))
def cb_done(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id; name = c.from_user.first_name or "User"
    res = api("complete_task", {"task_id": c.data[5:]}, uid)
    if not check(res, c.message.chat.id, uid, name): return
    bot.send_message(c.message.chat.id, "✅ <b>Task completed! 🎉</b>", reply_markup=main_kb())

@bot.callback_query_handler(func=lambda c: c.data == "task_delete")
def cb_task_delete(c):
    bot.answer_callback_query(c.id)
    res = api("get_tasks", {"filter": "all"}, c.from_user.id)
    tasks = res.get("tasks", [])
    if not tasks: bot.send_message(c.message.chat.id, "No tasks.", reply_markup=main_kb()); return
    kb = InlineKeyboardMarkup(row_width=1)
    for t in tasks[:8]: kb.add(InlineKeyboardButton(f"🗑 {t['title'][:45]}", callback_data=f"deltask_{t['id']}"))
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="xcl"))
    bot.send_message(c.message.chat.id, "Select task to delete:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("deltask_"))
def cb_deltask(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id; name = c.from_user.first_name or "User"
    res = api("delete_task", {"task_id": c.data[8:]}, uid)
    if not check(res, c.message.chat.id, uid, name): return
    bot.send_message(c.message.chat.id, "🗑 Task deleted.", reply_markup=main_kb())

# ══════════════════════════════════════════════════════════════════════════════
#  MARKS
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "📚 Marks")
def marks_menu(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Loading your marks...")
    res = api("get_marks", tg_id=uid)
    delete_msg(msg.chat.id, lmid)
    if not check(res, msg.chat.id, uid, name): return
    marks = res.get("marks", [])
    txt = f"📚 <b>Marks & Results ({len(marks)})</b>\n\n"
    if marks:
        for m in marks[:8]:
            mo = m.get("marks_obtained"); tot = m.get("total_marks")
            pct = round(float(mo)/float(tot)*100) if mo is not None and tot else None
            g = "🏆" if pct and pct>=75 else ("👍" if pct and pct>=50 else "📖")
            txt += f"{g} <b>{m.get('exam_name','')}</b> <i>({m.get('subject_name','')})</i>"
            if pct is not None: txt += f" — {mo}/{tot} ({pct}%)"
            if m.get("exam_date"): txt += f" 📅 {m['exam_date']}"
            txt += "\n"
    else:
        txt += "📭 <i>No marks recorded yet.</i>"
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("➕ Add Mark", callback_data="mark_add"),
           InlineKeyboardButton("🗑 Delete Mark", callback_data="mark_delete"))
    bot.send_message(msg.chat.id, txt, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "mark_add")
def cb_mark_add(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id; name = c.from_user.first_name or "User"
    res = api("get_subjects", tg_id=uid)
    if not check(res, c.message.chat.id, uid, name): return
    subs = res.get("subjects", [])
    if not subs: bot.send_message(c.message.chat.id, "⚠️ No subjects. Add them on the site."); return
    ss(uid, "mark_subject", {})
    kb = InlineKeyboardMarkup(row_width=2)
    for s in subs[:8]: kb.add(InlineKeyboardButton(s["name"], callback_data=f"mksub_{s['id']}_{s['name'][:15]}"))
    bot.send_message(c.message.chat.id, "Select a subject:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("mksub_"))
def cb_mksub(c):
    bot.answer_callback_query(c.id)
    parts = c.data.split("_", 2)
    ss(c.from_user.id, "mark_exam_name", {"sub_id": parts[1], "sub_name": parts[2] if len(parts)>2 else ""})
    bot.send_message(c.message.chat.id, f"Subject: <b>{parts[2] if len(parts)>2 else ''}</b>\n\nEnter exam name:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "mark_exam_name")
def mark_exam_name(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    d = gs(uid)["data"]; d["exam_name"] = msg.text.strip(); ss(uid, "mark_obtained", d)
    bot.send_message(msg.chat.id, "Enter marks obtained (e.g. 75):")

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "mark_obtained")
def mark_obtained(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    try: d = gs(uid)["data"]; d["obtained"] = float(msg.text.strip())
    except: bot.send_message(msg.chat.id, "❌ Enter a valid number."); return
    ss(uid, "mark_total", d); bot.send_message(msg.chat.id, "Enter total marks (e.g. 100):")

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "mark_total")
def mark_total(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    try: tot = float(msg.text.strip()); assert tot > 0
    except: bot.send_message(msg.chat.id, "❌ Enter a valid number."); return
    d = gs(uid)["data"]; d["total"] = tot; ss(uid, "mark_date", d)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton(datetime.now().strftime("%Y-%m-%d")), KeyboardButton("❌ Cancel"))
    bot.send_message(msg.chat.id, "Enter exam date (YYYY-MM-DD):", reply_markup=kb)

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "mark_date")
def mark_date(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    d = gs(uid)["data"]; cs(uid)
    res = api("add_mark", {"subject_id": d["sub_id"], "exam_name": d["exam_name"],
                           "marks_obtained": d["obtained"], "total_marks": d["total"],
                           "exam_date": msg.text.strip()}, uid)
    if not check(res, msg.chat.id, uid, name): return
    pct = round(d["obtained"]/d["total"]*100)
    g = "🏆" if pct>=75 else ("👍" if pct>=50 else "📖")
    bot.send_message(msg.chat.id, f"✅ <b>Mark Added!</b>\n\n{g} {d['exam_name']} ({d['sub_name']})\n📊 {d['obtained']}/{d['total']} = {pct}%", reply_markup=main_kb())

@bot.callback_query_handler(func=lambda c: c.data == "mark_delete")
def cb_mark_delete(c):
    bot.answer_callback_query(c.id)
    res = api("get_marks", tg_id=c.from_user.id)
    marks = res.get("marks", [])
    if not marks: bot.send_message(c.message.chat.id, "No marks.", reply_markup=main_kb()); return
    kb = InlineKeyboardMarkup(row_width=1)
    for m in marks[:8]: kb.add(InlineKeyboardButton(f"🗑 {m.get('exam_name','')[:30]} ({m.get('subject_name','')})", callback_data=f"delmark_{m['id']}"))
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="xcl"))
    bot.send_message(c.message.chat.id, "Select mark to delete:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("delmark_"))
def cb_delmark(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id; name = c.from_user.first_name or "User"
    res = api("delete_mark", {"mark_id": c.data[8:]}, uid)
    if not check(res, c.message.chat.id, uid, name): return
    bot.send_message(c.message.chat.id, "🗑 Mark deleted.", reply_markup=main_kb())

# ══════════════════════════════════════════════════════════════════════════════
#  GOALS
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🎯 Goals")
def goals_menu(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Loading your goals...")
    res = api("get_goals", tg_id=uid)
    delete_msg(msg.chat.id, lmid)
    if not check(res, msg.chat.id, uid, name): return
    goals = res.get("goals", [])
    txt = f"🎯 <b>Goals ({len(goals)})</b>\n\n"
    if goals:
        for g in goals[:8]:
            cur = float(g.get("current_value") or 0); tgt = float(g.get("target_value") or 0)
            pct = min(100, int(cur/tgt*100)) if tgt else 0
            bar = "█"*(pct//10) + "░"*(10-pct//10)
            txt += f"{'✅' if g.get('status')=='completed' else '🔄'} <b>{g['title']}</b>\n   [{bar}] {pct}% ({cur}/{tgt} {g.get('unit','')})\n\n"
    else:
        txt += "📭 <i>No goals yet.</i>"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Add Goal", callback_data="goal_add"))
    bot.send_message(msg.chat.id, txt, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "goal_add")
def cb_goal_add(c):
    bot.answer_callback_query(c.id); ss(c.from_user.id, "goal_title")
    bot.send_message(c.message.chat.id, "🎯 Enter a goal title:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "goal_title")
def goal_title(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    ss(uid, "goal_target", {"title": msg.text.strip()})
    bot.send_message(msg.chat.id, "Enter the target value (e.g. 100):")

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "goal_target")
def goal_target(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    try: tgt = float(msg.text.strip()); assert tgt > 0
    except: bot.send_message(msg.chat.id, "❌ Enter a valid number."); return
    d = gs(uid)["data"]; d["target"] = tgt; ss(uid, "goal_unit", d)
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    for u in ["hours","sessions","days","pages","problems"]: kb.add(KeyboardButton(u))
    kb.add(KeyboardButton("❌ Cancel"))
    bot.send_message(msg.chat.id, "Select or type a unit:", reply_markup=kb)

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "goal_unit")
def goal_unit(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    d = gs(uid)["data"]; cs(uid)
    res = api("add_goal", {"title": d["title"], "target_value": d["target"], "unit": msg.text.strip()}, uid)
    if not check(res, msg.chat.id, uid, name): return
    bot.send_message(msg.chat.id, f"✅ <b>Goal Added!</b>\n\n🎯 {d['title']}\nTarget: {d['target']} {msg.text.strip()}", reply_markup=main_kb())

# ══════════════════════════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🔔 Notifications")
def notifications_menu(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Loading notifications...")
    res = api("get_notifications", tg_id=uid)
    delete_msg(msg.chat.id, lmid)
    if not check(res, msg.chat.id, uid, name): return
    notifs = res.get("notifications", [])
    unread = sum(1 for n in notifs if not n.get("is_read"))
    ti = {"info":"ℹ️","success":"✅","warning":"⚠️","danger":"🚨","achievement":"🏆","streak":"🔥","reminder":"⏰","task":"✅"}
    txt = f"🔔 <b>Notifications</b> ({unread} unread)\n\n"
    if notifs:
        for n in notifs[:8]:
            txt += f"{'🆕 ' if not n.get('is_read') else ''}{ti.get(n.get('type','info'),'🔔')} <b>{n['title']}</b>\n   <i>{n['message'][:60]}</i>\n\n"
    else:
        txt += "📭 <i>No notifications.</i>"
    kb = InlineKeyboardMarkup()
    if unread: kb.add(InlineKeyboardButton("✅ Mark All Read", callback_data="notif_readall"))
    bot.send_message(msg.chat.id, txt, reply_markup=kb if unread else None)

@bot.callback_query_handler(func=lambda c: c.data == "notif_readall")
def cb_notif_read(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id; name = c.from_user.first_name or "User"
    res = api("read_all_notifications", tg_id=uid)
    if not check(res, c.message.chat.id, uid, name): return
    bot.send_message(c.message.chat.id, "✅ All notifications marked as read.", reply_markup=main_kb())

# ══════════════════════════════════════════════════════════════════════════════
#  STATS / STREAK
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "📈 Weekly Stats")
def weekly_stats(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Calculating your weekly stats...")
    res = api("weekly_stats", tg_id=uid)
    delete_msg(msg.chat.id, lmid)
    if not check(res, msg.chat.id, uid, name): return
    tot = res.get("total_minutes",0); days = res.get("days_studied",0); by = res.get("by_subject",[])
    txt = f"📈 <b>Weekly Stats</b> — Last 7 days\n\n⏱️ Total: <b>{fmt(tot)}</b>\n📅 Days: <b>{days}/7</b>\n\n"
    if by:
        mx = max(float(s.get("total_mins") or 0) for s in by) or 1
        txt += "📚 <b>By Subject:</b>\n"
        for s in by:
            m = float(s.get("total_mins") or 0)
            bar = "▓"*int(m/mx*8) + "░"*(8-int(m/mx*8))
            txt += f"  {bar} {s['name']}: {fmt(m)}\n"
    bot.send_message(msg.chat.id, txt)

@bot.message_handler(func=lambda m: m.text == "🔥 Streak")
def user_streak(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    res = api("get_streak", tg_id=uid)
    if not check(res, msg.chat.id, uid, name): return
    streak = res.get("streak",0); uname = res.get("name","")
    e = "🔥" if streak>=7 else ("✨" if streak>=3 else "💪")
    tip = ("💡 Log a session today to start!" if streak==0 else
           f"💪 {3-streak} more day(s) → 3-day streak!" if streak<3 else
           f"🌟 {7-streak} more day(s) → 7-day streak!" if streak<7 else "🏆 Amazing!")
    bot.send_message(msg.chat.id, f"{e} <b>{uname}'s Streak</b>\n\n🔥 <b>{streak} day(s)</b>\n\n{tip}")

# ══════════════════════════════════════════════════════════════════════════════
#  PROFILE
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "👤 My Profile")
def user_profile(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Loading your profile...")
    res = api("get_profile", tg_id=uid)
    delete_msg(msg.chat.id, lmid)
    if not check(res, msg.chat.id, uid, name): return
    p = res.get("profile", {})
    txt = (f"👤 <b>My Profile</b>\n\n"
           f"📛 Name: <b>{p.get('name','')}</b>\n"
           f"📧 Email: <code>{p.get('email','')}</code>\n"
           f"✅ Verified: {'Yes ✅' if p.get('is_verified') else 'No ⏳'}\n"
           f"🎯 Daily Goal: <b>{fmt(p.get('study_goal_minutes',120))}</b>\n"
           f"📅 Joined: {str(p.get('created_at',''))[:10]}\n\n"
           f"📚 Sessions: <b>{p.get('total_sessions',0)}</b>\n"
           f"⏱️ Total Study: <b>{fmt(p.get('total_mins',0))}</b>\n"
           f"🏆 Achievements: <b>{p.get('achievements',0)}</b>")
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🌐 View on Site", url=f"{SITE_URL}/profile.php"))
    bot.send_message(msg.chat.id, txt, reply_markup=kb)

# ══════════════════════════════════════════════════════════════════════════════
#  SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "⚙️ Settings")
def settings_menu(msg):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📛 Change Name",           callback_data="set_name"),
           InlineKeyboardButton("🎯 Update Study Goal",     callback_data="set_goal"),
           InlineKeyboardButton("🗑 Delete Study Session",  callback_data="set_del_session"),
           InlineKeyboardButton("🌐 Full Settings on Site", url=f"{SITE_URL}/settings.php"))
    bot.send_message(msg.chat.id, "⚙️ <b>Settings</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "set_name")
def cb_set_name(c):
    bot.answer_callback_query(c.id); ss(c.from_user.id, "setting_name")
    bot.send_message(c.message.chat.id, "Enter your new name:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "setting_name")
def setting_name(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    cs(uid)
    res = api("update_name", {"name": msg.text.strip()}, uid)
    if not check(res, msg.chat.id, uid, name): return
    bot.send_message(msg.chat.id, f"✅ Name updated to <b>{msg.text.strip()}</b>!", reply_markup=main_kb())

@bot.callback_query_handler(func=lambda c: c.data == "set_goal")
def cb_set_goal(c):
    bot.answer_callback_query(c.id); ss(c.from_user.id, "setting_goal")
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    for g in ["60","90","120","150","180","240"]: kb.add(KeyboardButton(g))
    kb.add(KeyboardButton("❌ Cancel"))
    bot.send_message(c.message.chat.id, "🎯 Select or type daily goal (minutes):", reply_markup=kb)

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "setting_goal")
def setting_goal(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=main_kb()); return
    try: g = int(msg.text.strip()); assert 15 <= g <= 600
    except: bot.send_message(msg.chat.id, "❌ Enter a value between 15 and 600."); return
    cs(uid)
    res = api("update_goal", {"goal_minutes": g}, uid)
    if not check(res, msg.chat.id, uid, name): return
    bot.send_message(msg.chat.id, f"✅ Goal updated: <b>{fmt(g)}/day</b>!", reply_markup=main_kb())

@bot.callback_query_handler(func=lambda c: c.data == "set_del_session")
def cb_del_session_start(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id; name = c.from_user.first_name or "User"
    res = api("get_recent_sessions", tg_id=uid)
    if not check(res, c.message.chat.id, uid, name): return
    sessions = res.get("sessions", [])
    if not sessions: bot.send_message(c.message.chat.id, "No sessions found.", reply_markup=main_kb()); return
    kb = InlineKeyboardMarkup(row_width=1)
    for s in sessions[:8]:
        label = f"🗑 {s.get('subject_name','')} — {fmt(s.get('duration_minutes',0))} ({s.get('date','')})"
        kb.add(InlineKeyboardButton(label[:55], callback_data=f"delsess_{s['id']}"))
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="xcl"))
    bot.send_message(c.message.chat.id, "Select session to delete:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("delsess_"))
def cb_delsess(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id; name = c.from_user.first_name or "User"
    res = api("delete_session", {"session_id": c.data[8:]}, uid)
    if not check(res, c.message.chat.id, uid, name): return
    bot.send_message(c.message.chat.id, "🗑 Session deleted.", reply_markup=main_kb())

@bot.callback_query_handler(func=lambda c: c.data == "xcl")
def cb_xcl(c):
    bot.answer_callback_query(c.id); cs(c.from_user.id)
    bot.send_message(c.message.chat.id, "❌ Cancelled.", reply_markup=main_kb())


# ══════════════════════════════════════════════════════════════════════════════
#  LEADERBOARD
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🏆 Leaderboard")
def leaderboard_menu(msg):
    uid = msg.from_user.id; name = msg.from_user.first_name or "User"
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("📅 Today",   callback_data="lb_daily"),
        InlineKeyboardButton("📆 Weekly",  callback_data="lb_weekly"),
        InlineKeyboardButton("🗓️ Monthly", callback_data="lb_monthly"),
    )
    bot.send_message(msg.chat.id,
        "🏆 <b>Leaderboard</b>\n\nSelect a time period:",
        reply_markup=kb)

def show_leaderboard(cid, uid, name, period):
    loading_action(cid)
    lmid = show_loading(cid, "Loading leaderboard...")
    res  = api("get_leaderboard", {"period": period}, uid)
    delete_msg(cid, lmid)
    if not check(res, cid, uid, name): return

    board = res.get("board", [])
    my_rank = res.get("my_rank", 0)
    total   = res.get("total", 0)

    period_label = {"daily": "📅 Today", "weekly": "📆 This Week", "monthly": "🗓️ This Month"}.get(period, "📆 This Week")
    rank_emoji   = {1: "🥇", 2: "🥈", 3: "🥉"}

    txt = f"🏆 <b>Leaderboard — {period_label}</b>\n"
    txt += f"👥 {total} friend(s) competing\n\n"

    if not board:
        txt += "📭 <i>No friends yet!</i>\n\n"
        txt += f"Add friends on the site: {SITE_URL}/leaderboard"
    else:
        for i, entry in enumerate(board[:10], 1):
            is_me = entry.get("is_me", False)
            emoji = rank_emoji.get(i, f"{i}.")
            mins  = entry.get("period_mins", 0)
            h, m  = divmod(int(mins), 60)
            time_str = f"{h}h {m}m" if h else f"{m}m" if m else "0m"
            badges = entry.get("badges", 0)
            name_str = entry.get("name", "")

            line = f"{emoji} <b>{name_str}</b> — ⏱️ {time_str}"
            if badges: line += f" 🏅{badges}"
            if is_me:  line = f"<u>{line}</u>"
            txt += line + "\n"

        txt += f"\n📍 <b>Your rank: #{my_rank}</b> out of {total}"

    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("📅 Today",   callback_data="lb_daily"),
        InlineKeyboardButton("📆 Weekly",  callback_data="lb_weekly"),
        InlineKeyboardButton("🗓️ Monthly", callback_data="lb_monthly"),
    )
    kb.add(InlineKeyboardButton("👥 Add Friends on Site", url=f"{SITE_URL}/leaderboard"))
    bot.send_message(cid, txt, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["lb_daily","lb_weekly","lb_monthly"])
def cb_leaderboard(c):
    bot.answer_callback_query(c.id)
    period_map = {"lb_daily": "daily", "lb_weekly": "weekly", "lb_monthly": "monthly"}
    show_leaderboard(c.message.chat.id, c.from_user.id,
                     c.from_user.first_name or "User",
                     period_map[c.data])

# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "⬅️ User Mode")
def sw_user(msg): bot.send_message(msg.chat.id, "👤 User mode.", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text == "📊 Site Stats" and is_admin(m.from_user.id))
def adm_stats(msg):
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Fetching site statistics...")
    res = adm("stats")
    delete_msg(msg.chat.id, lmid)
    if res.get("success"):
        s = res["stats"]
        bot.send_message(msg.chat.id,
            f"📊 <b>Site Stats</b>\n\n"
            f"👥 Users: <b>{s.get('total_users',0)}</b>\n"
            f"✅ Verified: <b>{s.get('verified',0)}</b>\n"
            f"🔗 Bot Linked: <b>{s.get('linked',0)}</b>\n"
            f"📚 Sessions: <b>{s.get('sessions',0)}</b>\n"
            f"⏱️ Total: <b>{fmt(s.get('total_mins',0))}</b>\n"
            f"✅ Tasks: <b>{s.get('tasks',0)}</b>\n"
            f"📅 Today: <b>{s.get('today_sessions',0)}</b>\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    else:
        bot.send_message(msg.chat.id, f"⚠️ {SITE_URL}/admin/")

@bot.message_handler(func=lambda m: m.text == "👥 Users" and is_admin(m.from_user.id))
def adm_users(msg):
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Loading user list...")
    res = adm("users")
    delete_msg(msg.chat.id, lmid)
    if res.get("success"):
        users = res.get("users",[])
        txt = f"👥 <b>Users ({len(users)})</b>\n\n"
        for u in users[:15]:
            txt += f"{'✅' if u.get('is_verified') else '⏳'}{'🔗' if u.get('telegram_id') else '  '} {u.get('name','')} — <i>{u.get('email','')}</i>\n"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🌐 Admin Panel", url=f"{SITE_URL}/admin/users.php"))
        bot.send_message(msg.chat.id, txt, reply_markup=kb)
    else:
        bot.send_message(msg.chat.id, f"⚠️ {SITE_URL}/admin/users.php")

@bot.message_handler(func=lambda m: m.text == "🔗 Linked Users" and is_admin(m.from_user.id))
def adm_linked(msg):
    res = adm("linked_users")
    if res.get("success"):
        users = res.get("users",[])
        txt = f"🔗 <b>Linked ({len(users)})</b>\n\n"
        for u in users[:20]: txt += f"👤 {u.get('name','')} — <code>{u.get('telegram_id','')}</code>\n"
    else: txt = "⚠️ API error."
    bot.send_message(msg.chat.id, txt)

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and is_admin(m.from_user.id))
def adm_broadcast(msg):
    ss(msg.from_user.id, "broadcast_msg")
    bot.send_message(msg.chat.id, "📢 Type broadcast message:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "broadcast_msg")
def broadcast_text(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=admin_kb()); return
    ss(uid, "bc_confirm", {"text": msg.text.strip()})
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Send", callback_data="bc_send"),
           InlineKeyboardButton("❌ Cancel", callback_data="bc_no"))
    bot.send_message(msg.chat.id, f"📢 <b>Preview:</b>\n\n{msg.text}\n\nSend to all?", reply_markup=ReplyKeyboardRemove())
    bot.send_message(msg.chat.id, "⬆️", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["bc_send","bc_no"])
def cb_bc(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id
    if not is_admin(uid): return
    if c.data == "bc_no": cs(uid); bot.send_message(c.message.chat.id, "❌ Cancelled.", reply_markup=admin_kb()); return
    txt = gs(uid)["data"].get("text",""); cs(uid)
    res = adm("linked_users"); users = res.get("users",[]) if res.get("success") else []
    sent = failed = 0
    for u in users:
        tgid = u.get("telegram_id")
        if not tgid: continue
        try: bot.send_message(int(tgid), f"📢 <b>StudyTrack</b>\n\n{txt}\n\n<i>— StudyTrack Team</i>"); sent+=1
        except: failed+=1
    bot.send_message(c.message.chat.id, f"📢 Done! ✅{sent} ❌{failed}", reply_markup=admin_kb())

@bot.message_handler(func=lambda m: m.text == "📣 Announce" and is_admin(m.from_user.id))
def adm_announce(msg):
    ss(msg.from_user.id, "ann_title")
    bot.send_message(msg.chat.id, "📣 Title:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "ann_title")
def ann_title(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=admin_kb()); return
    ss(uid, "ann_content", {"title": msg.text.strip()}); bot.send_message(msg.chat.id, "Content:")

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "ann_content")
def ann_content(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=admin_kb()); return
    d = gs(uid)["data"]; d["content"] = msg.text.strip(); ss(uid, "ann_priority", d)
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("🔴 High", callback_data="annp_high"),
           InlineKeyboardButton("🟡 Normal", callback_data="annp_normal"),
           InlineKeyboardButton("🟢 Low", callback_data="annp_low"))
    bot.send_message(msg.chat.id, "Priority:", reply_markup=ReplyKeyboardRemove())
    bot.send_message(msg.chat.id, "⬆️", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("annp_"))
def cb_annp(c):
    bot.answer_callback_query(c.id)
    uid = c.from_user.id
    if not is_admin(uid): return
    p = c.data[5:]; d = gs(uid)["data"]; cs(uid)
    res = adm("add_announcement", {"title": d["title"], "content": d["content"], "priority": p})
    bot.send_message(c.message.chat.id,
        f"✅ Posted!\n\n📣 {d['title']}" if res.get("success") else f"⚠️ {SITE_URL}/admin/announcements.php",
        reply_markup=admin_kb())

@bot.message_handler(func=lambda m: m.text == "🔔 Notify User" and is_admin(m.from_user.id))
def adm_notify(msg):
    ss(msg.from_user.id, "notify_tgid")
    bot.send_message(msg.chat.id, "🔔 Enter user Telegram ID:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "notify_tgid")
def notify_id(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=admin_kb()); return
    try: tid = int(msg.text.strip())
    except: bot.send_message(msg.chat.id, "❌ Invalid ID."); return
    ss(uid, "notify_text", {"target": tid}); bot.send_message(msg.chat.id, f"Message for <code>{tid}</code>:")

@bot.message_handler(func=lambda m: gs(m.from_user.id)["state"] == "notify_text")
def notify_text(msg):
    uid = msg.from_user.id
    if msg.text == "❌ Cancel": cs(uid); bot.send_message(msg.chat.id, "❌ Cancelled.", reply_markup=admin_kb()); return
    d = gs(uid)["data"]; cs(uid)
    try:
        bot.send_message(d["target"], f"🔔 <b>StudyTrack</b>\n\n{msg.text}\n\n<i>— Admin</i>")
        bot.send_message(msg.chat.id, f"✅ Sent!", reply_markup=admin_kb())
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Failed: {e}", reply_markup=admin_kb())

@bot.message_handler(func=lambda m: m.text == "📋 Weekly Report" and is_admin(m.from_user.id))
def adm_report(msg):
    loading_action(msg.chat.id)
    lmid = show_loading(msg.chat.id, "Generating weekly report...")
    res = adm("weekly_report")
    delete_msg(msg.chat.id, lmid)
    if res.get("success"):
        r = res["report"]
        bot.send_message(msg.chat.id,
            f"📋 <b>Weekly Report</b>\n\n"
            f"👥 Active: <b>{r.get('active_users',0)}</b>\n"
            f"📚 Sessions: <b>{r.get('sessions',0)}</b>\n"
            f"⏱️ Total: <b>{fmt(r.get('total_mins',0))}</b>\n"
            f"✅ Tasks done: <b>{r.get('completed_tasks',0)}</b>\n"
            f"🆕 New users: <b>{r.get('new_users',0)}</b>")
    else:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🌐 View", url=f"{SITE_URL}/admin/weekly-reports.php"))
        bot.send_message(msg.chat.id, "⚠️ API error.", reply_markup=kb)

# ══════════════════════════════════════════════════════════════════════════════
#  FALLBACK
# ══════════════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: True)
def fallback(msg):
    if gs(msg.from_user.id)["state"]: return
    bot.send_message(msg.chat.id, "Use the menu below 👇", reply_markup=main_kb())

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 50)
    print("  StudyTrack Bot — GET mode (proxy-safe)")
    print(f"  {SITE_URL}")
    print("=" * 50)
    print("Running... Ctrl+C to stop.\n")
    try:
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)