import os
import re
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

# =========================================================
# CONFIG
# =========================================================

# Railway Variable:
# BOT_TOKEN = your BotFather token
#
# TELEGRAM_BOT_TOKEN ko fallback ke roop mein bhi support kiya hai.
BOT_TOKEN = "8742750136:AAFy6kTxycv_CuAe3zdpzLVAUa2tTmxmWSE"

MAX_FILE_SIZE = 50 * 1024 * 1024

# Optional:
# ALLOWED_USERS=123456789,987654321
_allowed = os.getenv("ALLOWED_USERS", "").strip()

ALLOWED_USERS = set()

if _allowed:
    for value in _allowed.split(","):
        value = value.strip()
        if value.isdigit():
            ALLOWED_USERS.add(int(value))

# Temporary directory
TEMP_ROOT = Path(tempfile.gettempdir()) / "apk_demo_bot"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("APK-BOT")


# =========================================================
# HELPERS
# =========================================================

def allowed_user(user_id: int) -> bool:
    # Empty ALLOWED_USERS = everyone allowed
    if not ALLOWED_USERS:
        return True

    return user_id in ALLOWED_USERS


def safe_filename(filename: str) -> str:
    filename = os.path.basename(filename or "application.apk")

    filename = re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        filename,
    )

    if not filename.lower().endswith(".apk"):
        filename += ".apk"

    return filename[:150]


def calculate_sha256(path: Path) -> str:
    sha = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            sha.update(chunk)

    return sha.hexdigest()


def looks_like_apk(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            magic = file.read(4)

        # APK is a ZIP archive
        return magic == b"PK\x03\x04"

    except Exception:
        return False


def cleanup(directory: Path):
    try:
        if directory.exists():
            shutil.rmtree(
                directory,
                ignore_errors=True,
            )
    except Exception:
        logger.exception("Cleanup failed")


# =========================================================
# COMMANDS
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.effective_user:
        return

    if not allowed_user(update.effective_user.id):
        await update.message.reply_text(
            "❌ Access denied."
        )
        return

    await update.message.reply_text(
        "YE BOT apk KO UNPACK KARTA HAI\n\n"
        "FEER ENC KARR KE REPACK KARTA HAI.\n\n"
        "Bot APK ko receive karega, validate karega "
        "Unlimited Enc.\n\n"
        "xxxxxx "
        "send apk."
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "📱 APK Demo Bot\n\n"
        "/start - Bot start\n"
        "/help - Help\n\n"
        "Maximum APK size: 50 MB"
    )


# =========================================================
# APK PROCESSOR
# =========================================================

async def handle_apk(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message
    user = update.effective_user

    if not message or not user:
        return

    if not allowed_user(user.id):
        await message.reply_text(
            "❌ Access denied."
        )
        return

    document = message.document

    if not document:
        return

    filename = safe_filename(
        document.file_name
    )

    # Telegram MIME can vary, so extension + magic
    # are checked instead of trusting MIME alone.
    if not filename.lower().endswith(".apk"):
        await message.reply_text(
            "❌ Sirf APK file bhejo."
        )
        return

    if (
        document.file_size
        and document.file_size > MAX_FILE_SIZE
    ):
        await message.reply_text(
            "❌ APK maximum 50 MB ho sakti hai."
        )
        return

    workdir = Path(
        tempfile.mkdtemp(
            prefix="job_",
            dir=str(TEMP_ROOT),
        )
    )

    input_path = workdir / filename
    output_path = workdir / (
        "processed_" + filename
    )

    try:
        await message.reply_text(
            "⏳ APK receive ho rahi hai..."
        )

        telegram_file = await context.bot.get_file(
            document.file_id
        )

        await telegram_file.download_to_drive(
            custom_path=str(input_path)
        )

        if not input_path.exists():
            raise RuntimeError(
                "APK download nahi hui."
            )

        size = input_path.stat().st_size

        if size > MAX_FILE_SIZE:
            raise RuntimeError(
                "APK 50 MB limit se badi hai."
            )

        if not looks_like_apk(input_path):
            raise RuntimeError(
                "File valid APK nahi lagti."
            )

        original_hash = calculate_sha256(
            input_path
        )

        await message.reply_text(
            "✅ APK validation successful.\n\n"
            f"📦 Size: {size / 1024 / 1024:.2f} MB\n"
            f"🔐 SHA-256:\n"
            f"`{original_hash}`\n\n"
            "⚙️ Demo processing..."
            ,
            parse_mode="Markdown",
        )

        # -------------------------------------------------
        # DEMO PROCESSING
        # -------------------------------------------------
        #
        # Intentionally leaves APK unchanged.
        # This verifies the complete Telegram → Railway
        # upload → processing → download pipeline.
        #
        # -------------------------------------------------

        shutil.copy2(
            input_path,
            output_path,
        )

        processed_hash = calculate_sha256(
            output_path
        )

        with output_path.open("rb") as file:
            await message.reply_document(
                document=file,
                caption=(
                    "✅ Processing complete\n\n"
                    f"📱 `{output_path.name}`\n"
                    f"🔐 SHA-256:\n"
                    f"`{processed_hash}`\n\n"
                    "⚠️ Demo mode: APK contents "
                    "were not modified."
                ),
                parse_mode="Markdown",
            )

    except Exception as error:
        logger.exception(
            "APK processing error"
        )

        await message.reply_text(
            "❌ Error:\n"
            f"`{str(error)[:500]}`",
            parse_mode="Markdown",
        )

    finally:
        cleanup(workdir)


# =========================================================
# NON-APK FILES
# =========================================================

async def reject_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message:
        await update.message.reply_text(
            "❌ Is bot mein sirf APK files accepted hain."
        )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.exception(
        "Unhandled bot error",
        exc_info=context.error,
    )


# =========================================================
# MAIN
# =========================================================

def main():

    # IMPORTANT:
    # Railway par BOT_TOKEN variable mandatory hai.
    if not BOT_TOKEN:
        logger.error(
            "BOT_TOKEN / TELEGRAM_BOT_TOKEN "
            "environment variable missing."
        )

        raise RuntimeError(
            "BOT_TOKEN environment variable missing. "
            "Railway → Service → Variables mein "
            "BOT_TOKEN add karo."
        )

    logger.info(
        "BOT_TOKEN detected. Starting bot..."
    )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Document.FileExtension("apk"),
            handle_apk,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            reject_file,
        )
    )

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "🤖 APK bot started successfully."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()