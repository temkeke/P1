"""Telegram bot implementation for the P1 dialer application."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from telebot import TeleBot, types

from config import Config, load_config
from job_manager import JobManager
from models import Lead, UserStats


MAIN_MENU_SETTINGS = "Settings"
MAIN_MENU_START_JOB = "Start Job"
MAIN_MENU_JOB_STATUS = "Job Status"
MAIN_MENU_PRESETS = "Presets"
MAIN_MENU_ADMIN = "Admin Menu"

STATE_IDLE = "idle"
STATE_SETTING_CALLER_ID = "setting_caller_id"
STATE_WAITING_FILE = "waiting_file"
STATE_WAITING_STATUS_ID = "waiting_status_id"
STATE_ADMIN_WHITELIST = "admin_whitelist"
STATE_ADMIN_UNWHITELIST = "admin_unwhitelist"
STATE_ADMIN_STATS = "admin_stats"

ADMIN_WHITELIST = "Whitelist User"
ADMIN_UNWHITELIST = "Unwhitelist User"
ADMIN_VIEW_STATS = "View User Stats"
ADMIN_BACK = "Back"


@dataclass
class UserContext:
    caller_id: Optional[str]
    script: str
    preset: str
    stats: UserStats


class P1Bot:
    def __init__(self, config: Config):
        self.config = config
        self.bot = TeleBot(config.bot.token, parse_mode="Markdown")
        self.job_manager = JobManager(config, self.bot, self._on_call_complete)
        self.whitelist = set(config.bot.initial_whitelist) | set(config.bot.admin_ids)
        self.admin_ids = set(config.bot.admin_ids)
        self.user_context: Dict[int, UserContext] = {}
        self.user_states: Dict[int, str] = {}
        self._register_handlers()

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------
    def _register_handlers(self) -> None:
        bot = self.bot

        @bot.message_handler(commands=["start"])
        def handle_start(message):
            user_id = message.from_user.id
            context = self._ensure_context(user_id)
            welcome = self._build_welcome_message(message)
            bot.send_message(message.chat.id, welcome)

            if not self._is_authorized(user_id):
                bot.send_message(
                    message.chat.id,
                    "🚫 You are not authorized to use this bot.",
                )
                return

            self._send_main_menu(message.chat.id, is_admin=self._is_admin(user_id))
            self.user_states[user_id] = STATE_IDLE

        @bot.message_handler(commands=["cancel"])
        def handle_cancel(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            self.user_states[user_id] = STATE_IDLE
            bot.send_message(message.chat.id, "❌ Cancelled.")
            self._send_main_menu(message.chat.id, self._is_admin(user_id))

        @bot.message_handler(commands=["status"])
        def handle_status_command(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            parts = message.text.split()
            if len(parts) == 1:
                self.user_states[user_id] = STATE_WAITING_STATUS_ID
                bot.send_message(message.chat.id, "Please send the Job ID.")
                return
            job_id = parts[1]
            self._send_job_status(message.chat.id, job_id, user_id)

        @bot.message_handler(commands=["line"])
        def handle_line(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            queued = self.job_manager.get_next_press_one(user_id)
            if not queued:
                bot.send_message(message.chat.id, "No P1 leads are waiting.")
                return
            lead = queued.lead
            queued_at = queued.queued_at.strftime("%Y-%m-%d %H:%M:%S")
            bot.send_message(
                message.chat.id,
                (
                    "📋 Next P1 Line\n\n"
                    f"{lead.email or 'N/A'} | {lead.name or 'N/A'} | {lead.phone}\n\n"
                    "\n\n"
                    f"⏰ Queued: {queued_at}\n"
                    "📊 Remaining: {remaining}"
                ).format(remaining=self.job_manager.press_one_count(user_id)),
            )

        @bot.message_handler(func=lambda m: m.text == MAIN_MENU_SETTINGS)
        def handle_settings(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            self.user_states[user_id] = STATE_SETTING_CALLER_ID
            bot.send_message(
                message.chat.id,
                (
                    "📞 Set Caller ID\n\n"
                    "Please send the caller ID you want to use.\n"
                    "Format: 10-digit number (e.g., 1234567890)\n\n"
                    "Send /cancel to cancel."
                ),
            )

        @bot.message_handler(func=lambda m: m.text == MAIN_MENU_START_JOB)
        def handle_start_job(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            self.user_states[user_id] = STATE_WAITING_FILE
            bot.send_message(
                message.chat.id,
                (
                    "📤 Upload Contact File \n\n"
                    "Please send a .txt or .csv file with phone numbers.\n\n"
                    "📋 Accepted formats:\n"
                    "• email | name | phone (pipe separator)\n"
                    "• email,name,phone (comma separator)\n"
                    "• email name phone (space separator)\n"
                    "• phone (just phone number)\n\n"
                    "Examples:\n"
                    "john@example.com | John Doe | +1234567890\n"
                    "jane@example.com,Jane Smith,6505551234\n"
                    "bob@test.com Bob Jones 650-555-5678\n"
                    "+1234567890\n\n"
                    "Send /cancel to cancel."
                ),
            )

        @bot.message_handler(func=lambda m: m.text == MAIN_MENU_JOB_STATUS)
        def handle_job_status_button(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            self.user_states[user_id] = STATE_WAITING_STATUS_ID
            bot.send_message(message.chat.id, "Please send the Job ID.")

        @bot.message_handler(func=lambda m: m.text == MAIN_MENU_PRESETS)
        def handle_presets(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            buttons = [
                types.KeyboardButton(f"Preset {i}") for i in range(1, 6)
            ]
            markup.row(*buttons[:2])
            markup.row(*buttons[2:4])
            markup.row(buttons[4])
            markup.row(types.KeyboardButton("Back"))
            bot.send_message(message.chat.id, "Choose a preset:", reply_markup=markup)

        @bot.message_handler(func=lambda m: m.text and m.text.startswith("Preset "))
        def handle_preset_selection(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            context = self._ensure_context(user_id)
            context.preset = message.text.lower()
            bot.send_message(
                message.chat.id,
                f"✅ {message.text} selected.",
            )
            self.user_states[user_id] = STATE_IDLE
            self._send_main_menu(message.chat.id, self._is_admin(user_id))

        @bot.message_handler(func=lambda m: m.text == "Back")
        def handle_back(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            self.user_states[user_id] = STATE_IDLE
            self._send_main_menu(message.chat.id, self._is_admin(user_id))

        @bot.message_handler(func=lambda m: m.text == MAIN_MENU_ADMIN)
        def handle_admin_menu(message):
            user_id = message.from_user.id
            if not self._is_admin(user_id):
                return
            self.user_states[user_id] = STATE_IDLE
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row(ADMIN_WHITELIST, ADMIN_UNWHITELIST)
            markup.row(ADMIN_VIEW_STATS)
            markup.row("Back")
            bot.send_message(message.chat.id, "Admin actions:", reply_markup=markup)

        @bot.message_handler(func=lambda m: m.text in {ADMIN_WHITELIST, ADMIN_UNWHITELIST, ADMIN_VIEW_STATS})
        def handle_admin_actions(message):
            user_id = message.from_user.id
            if not self._is_admin(user_id):
                return
            if message.text == ADMIN_WHITELIST:
                self.user_states[user_id] = STATE_ADMIN_WHITELIST
                bot.send_message(message.chat.id, "Send the Telegram user ID to whitelist.")
            elif message.text == ADMIN_UNWHITELIST:
                self.user_states[user_id] = STATE_ADMIN_UNWHITELIST
                bot.send_message(message.chat.id, "Send the Telegram user ID to unwhitelist.")
            elif message.text == ADMIN_VIEW_STATS:
                self.user_states[user_id] = STATE_ADMIN_STATS
                bot.send_message(message.chat.id, "Send the Telegram user ID to view stats.")

        @bot.message_handler(content_types=["document"])
        def handle_document(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            if self.user_states.get(user_id) != STATE_WAITING_FILE:
                return
            file_name = message.document.file_name or ""
            if not (file_name.endswith(".txt") or file_name.endswith(".csv")):
                bot.send_message(message.chat.id, "Please upload a .txt or .csv file.")
                return
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            try:
                content = downloaded.decode("utf-8")
            except UnicodeDecodeError:
                content = downloaded.decode("latin-1")
            leads = self._parse_leads(content)
            if not leads:
                bot.send_message(message.chat.id, "No valid contacts found in file.")
                return
            context = self._ensure_context(user_id)
            job = self.job_manager.create_job(
                user_id=user_id,
                leads=leads,
                script=context.script,
                caller_id=context.caller_id,
                preset=context.preset,
            )
            context.stats.register_job(job)
            self.user_states[user_id] = STATE_IDLE

        @bot.message_handler(func=lambda _: True, content_types=["text"])
        def handle_text(message):
            user_id = message.from_user.id
            if not self._is_authorized(user_id):
                return
            state = self.user_states.get(user_id, STATE_IDLE)
            if state == STATE_SETTING_CALLER_ID:
                self._handle_caller_id_input(message)
            elif state == STATE_WAITING_STATUS_ID:
                self._send_job_status(message.chat.id, message.text.strip(), user_id)
                self.user_states[user_id] = STATE_IDLE
            elif state == STATE_ADMIN_WHITELIST:
                self._handle_admin_whitelist(message, add=True)
            elif state == STATE_ADMIN_UNWHITELIST:
                self._handle_admin_whitelist(message, add=False)
            elif state == STATE_ADMIN_STATS:
                self._handle_admin_stats(message)
            else:
                bot.send_message(
                    message.chat.id,
                    "I didn't understand that. Please choose an option from the menu.",
                )

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    def _handle_caller_id_input(self, message):
        user_id = message.from_user.id
        caller_id = message.text.strip()
        if not caller_id.isdigit() or len(caller_id) != 10:
            self.bot.send_message(
                message.chat.id,
                "Caller ID must be a 10-digit number. Try again or send /cancel.",
            )
            return
        context = self._ensure_context(user_id)
        context.caller_id = caller_id
        self.user_states[user_id] = STATE_IDLE
        self.bot.send_message(message.chat.id, f"✅ Caller ID set to {caller_id}.")
        self._send_main_menu(message.chat.id, self._is_admin(user_id))

    def _handle_admin_whitelist(self, message, add: bool) -> None:
        user_id = message.from_user.id
        try:
            target_id = int(message.text.strip())
        except ValueError:
            self.bot.send_message(message.chat.id, "Please send a valid numeric user ID.")
            return
        if add:
            self.whitelist.add(target_id)
            self.bot.send_message(message.chat.id, f"User {target_id} has been whitelisted.")
        else:
            if target_id in self.whitelist and target_id not in self.admin_ids:
                self.whitelist.remove(target_id)
            self.bot.send_message(message.chat.id, f"User {target_id} has been removed from whitelist.")
        self.user_states[user_id] = STATE_IDLE
        self._send_main_menu(message.chat.id, True)

    def _handle_admin_stats(self, message) -> None:
        user_id = message.from_user.id
        try:
            target_id = int(message.text.strip())
        except ValueError:
            self.bot.send_message(message.chat.id, "Please send a valid numeric user ID.")
            return
        context = self.user_context.get(target_id)
        if not context:
            self.bot.send_message(message.chat.id, "No statistics found for that user.")
            return
        stats = context.stats
        response = (
            f"📊 Stats for {target_id}:\n"
            f"• Jobs Started: {stats.jobs_started}\n"
            f"• Total Calls: {stats.total_calls}\n"
            f"• Answered: {stats.total_answered}\n"
            f"• Pressed 1: {stats.total_pressed_one}"
        )
        self.bot.send_message(message.chat.id, response)
        self.user_states[user_id] = STATE_IDLE
        self._send_main_menu(message.chat.id, True)

    def _send_job_status(self, chat_id: int, job_id: str, user_id: int) -> None:
        job = self.job_manager.get_job(job_id)
        if not job or job.user_id != user_id:
            self.bot.send_message(chat_id, "Job not found.")
            return
        status = (
            f"📋 Job {job.id}\n"
            f"• Total: {job.total_calls()}\n"
            f"• Processed: {job.processed}\n"
            f"• Answered: {job.answered}\n"
            f"• Pressed 1: {job.pressed_one}\n"
            f"• Completed: {'Yes' if job.completed else 'No'}"
        )
        self.bot.send_message(chat_id, status)

    def _send_main_menu(self, chat_id: int, is_admin: bool) -> None:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row(
            types.KeyboardButton(MAIN_MENU_SETTINGS),
            types.KeyboardButton(MAIN_MENU_START_JOB),
        )
        markup.row(
            types.KeyboardButton(MAIN_MENU_JOB_STATUS),
            types.KeyboardButton(MAIN_MENU_PRESETS),
        )
        if is_admin:
            markup.row(types.KeyboardButton(MAIN_MENU_ADMIN))
        self.bot.send_message(chat_id, "Main menu:", reply_markup=markup)

    def _is_authorized(self, user_id: int) -> bool:
        return user_id in self.whitelist or self._is_admin(user_id)

    def _is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def _ensure_context(self, user_id: int) -> UserContext:
        if user_id not in self.user_context:
            defaults = self.config.defaults
            stats = UserStats(user_id=user_id)
            self.user_context[user_id] = UserContext(
                caller_id=defaults.caller_id,
                script=defaults.script_text,
                preset=defaults.intro_preset,
                stats=stats,
            )
        return self.user_context[user_id]

    def _build_welcome_message(self, message) -> str:
        user = message.from_user
        username = f"@{user.username}" if user.username else "N/A"
        name = user.first_name or "Unknown"
        return (
            "🎉 Welcome to P1!\n\n"
            "👤 User Account:\n"
            f"• Name: {name}\n"
            f"• Username: {username}\n"
            f"• User ID: {user.id} \n\n"
            "📊 Current Settings\n\n"
            f"📞 Caller ID: {self._ensure_context(user.id).caller_id or 'example'}\n\n"
            f"📜 Script: {self._ensure_context(user.id).script}"
        )

    def _parse_leads(self, content: str):
        leads = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
            elif "," in line:
                parts = [p.strip() for p in line.split(",")]
            elif " " in line:
                parts = [p.strip() for p in line.split()]
            else:
                parts = [line]

            email = None
            name = None
            phone = None

            if len(parts) >= 3:
                email, name, phone = parts[0], parts[1], parts[2]
            elif len(parts) == 2:
                name, phone = parts
            elif len(parts) == 1:
                phone = parts[0]
            else:
                continue

            phone_normalized = self._normalize_phone(phone)
            if not phone_normalized:
                continue
            leads.append(Lead(email=email or None, name=name or None, phone=phone_normalized))
        return leads

    @staticmethod
    def _normalize_phone(phone: Optional[str]) -> Optional[str]:
        if not phone:
            return None
        digits = [ch for ch in phone if ch.isdigit() or ch == "+"]
        if not digits:
            return None
        normalized = "".join(digits)
        return normalized

    def _on_call_complete(self, job, lead, answered: bool, pressed_one: bool) -> None:
        context = self.user_context.get(job.user_id)
        if not context:
            return
        context.stats.register_call_update(answered, pressed_one)

    def run(self) -> None:
        self.bot.infinity_polling()


if __name__ == "__main__":
    config = load_config()
    app = P1Bot(config)
    app.run()
