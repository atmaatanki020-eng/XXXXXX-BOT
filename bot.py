import os
import re
import time
import shutil
import hashlib
import tempfile
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("8742750136:AAFy6kTxycv_CuAe3zdpzLVAUa2tTmxmWSE")

# Maximum APK accepted by this demo bot: 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024

# Optional: comma-separated Telegram user IDs.
# Leave empty to allow testing by everyone.
ALLOWED_USERS = {
    int(x.strip())
    for x in os.getenv("ALLOWED_USERS", "").split(",")
    if x.strip().isdigit()
}

TEMP_ROOT = Path(tempfile.gettempdir()) / "apk_protection_bot"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

log = logging.getLogger("apk-bot")


# ============================================================
# HELPERS
# ============================================================

def user_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()


def is_probably_apk(path: Path) -> bool:
    """
    APK is basically a ZIP archive.
    Check ZIP magic rather than trusting only filename.
    """
    try:
        with path.open("rb") as f:
            header = f.read(4)
        return header == b"PK\x03\x04"
    except OSError:
        return False


def safe_filename(name: str) -> str:
    """
    Prevent path traversal / weird filenames.
    """
    name = os.path.basename(name)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)

    if not name.lower().endswith(".apk"):
        name += ".apk"

    return name[:150]


async def cleanup(path: Path):
    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        log.exception("Cleanup failed")


# ============================================================
# COMMANDS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    if not user_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return

    await update.message.reply_text(
        "🤖 APK Protection Demo\n\n"
        "Apni APK file bhejo.\n"
        "Bot:\n"
        "• APK validate karega\n"
        "• SHA-256 calculate karega\n"
        "• Temporary workspace mein process karega\n"
        "• Processed APK return karega\n\n"
        "⚠️ Ye demo abhi DEX encryption inject nahi karta."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📱 APK Demo Bot\n\n"
        "1. /start bhejo\n"
        "2. APK upload karo\n"
        "3. Bot validation karega\n"
        "4. SHA-256 calculate hoga\n"
        "5. APK wapas milegi\n\n"
        "Maximum file size: 50 MB"
    )


# ============================================================
# APK HANDLER
# ============================================================

async def handle_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    if not user or not message:
        return

    if not user_allowed(user.id):
        await message.reply_text("❌ Access denied.")
        return

    document = message.document

    if not document:
        return

    filename = safe_filename(document.file_name or "application.apk")

    if not filename.lower().endswith(".apk"):
        await message.reply_text(
            "❌ Sirf .apk file bhejo."
        )
        return

    if document.file_size and document.file_size > MAX_FILE_SIZE:
        await message.reply_text(
            "❌ File 50 MB se badi hai."
        )
        return

    workdir = Path(
        tempfile.mkdtemp(
            prefix="job_",
            dir=str(TEMP_ROOT),
        )
    )

    input_file = workdir / filename
    output_file = workdir / f"protected_{filename}"

    try:
        await message.reply_text(
            "⏳ APK receive ho gayi.\n"
            "Validation start..."
        )

        tg_file = await context.bot.get_file(document.file_id)

        await tg_file.download_to_drive(
            custom_path=str(input_file)
        )

        # ----------------------------------------------------
        # Basic validation
        # ----------------------------------------------------

        if not input_file.exists():
            raise RuntimeError("Downloaded file not found.")

        actual_size = input_file.stat().st_size

        if actual_size > MAX_FILE_SIZE:
            raise RuntimeError("File exceeds size limit.")

        if not is_probably_apk(input_file):
            raise RuntimeError(
                "File APK/ZIP format mein valid nahi lagti."
            )

        original_hash = sha256_file(input_file)

        await message.reply_text(
            "✅ APK validation successful.\n\n"
            f"📦 Size: {actual_size / (1024 * 1024):.2f} MB\n"
            f"🔐 SHA-256:\n`{original_hash}`\n\n"
            "⚙️ Demo processing..."
            ,
            parse_mode="Markdown"
        )

        # ====================================================
        # DEMO PROCESSING
        # ====================================================
        #
        # IMPORTANT:
        # At this stage we intentionally DO NOT perform
        # arbitrary DEX encryption / anti-analysis injection.
        #
        # For pipeline testing, copy the APK unchanged.
        #
        # A legitimate production hardening workflow should
        # normally happen during YOUR app's build process using
        # R8/ProGuard and proper signing.
        # ====================================================

        shutil.copy2(input_file, output_file)

        processed_hash = sha256_file(output_file)

        await message.reply_document(
            document=output_file.open("rb"),
            caption=(
                "✅ Demo processing complete\n\n"
                f"📱 File: `{output_file.name}`\n"
                f"🔐 SHA-256:\n`{processed_hash}`\n\n"
                "⚠️ Demo mode: APK contents were not "
                "DEX-encrypted."
            ),
            parse_mode="Markdown",
        )

    except Exception as e:
        log.exception("APK processing failed")

        await message.reply_text(
            f"❌ Processing failed:\n`{str(e)[:500]}`",
            parse_mode="Markdown",
        )

    finally:
        # Always remove uploaded APK from server.
        await cleanup(workdir)


# ============================================================
# UNKNOWN FILE HANDLER
# ============================================================

async def other_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "❌ Is demo bot mein sirf APK files accepted hain."
        )


# ============================================================
# MAIN
# ============================================================

def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable missing."
        )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        MessageHandler(
            filters.Document.FileExtension("apk"),
            handle_apk,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            other_file,
        )
    )

    log.info("APK bot started.")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()