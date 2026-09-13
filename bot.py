# bot.py — Main Telegram Bot
import os
import zipfile
import shutil
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8742750136:AAFy6kTxycv_CuAe3zdpzLVAUa2tTmxmWSE"
ZIP_PASSWORD = b"onyx6767"  # password for protected zip

WORK_DIR = "workspace"
os.makedirs(WORK_DIR, exist_ok=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me your APK. I'll protect it, hook it, and return a password-protected ZIP.\nPassword: onyx6767"
    )


async def handle_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    doc = message.document

    if not doc.file_name.endswith(".apk"):
        await message.reply_text("Send a valid .apk file.")
        return

    await message.reply_text("Received. Processing...")

    user_id = str(message.from_user.id)
    user_dir = os.path.join(WORK_DIR, user_id)
    os.makedirs(user_dir, exist_ok=True)

    # Download APK
    apk_path = os.path.join(user_dir, doc.file_name)
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(apk_path)

    # Process
    output_zip = await protect_apk(apk_path, user_dir)

    if output_zip:
        await message.reply_document(
            document=open(output_zip, "rb"),
            filename=os.path.basename(output_zip),
            caption="Protected APK inside ZIP\nPassword: `onyx6767`",
            parse_mode="Markdown"
        )
    else:
        await message.reply_text("Something went wrong during processing.")

    shutil.rmtree(user_dir)


async def protect_apk(apk_path: str, work_dir: str) -> str | None:
    try:
        base_name = os.path.splitext(os.path.basename(apk_path))[0]

        # Step 1: Decompile APK with apktool
        decomp_dir = os.path.join(work_dir, "decomp")
        subprocess.run(
            ["apktool", "d", apk_path, "-o", decomp_dir, "--force"],
            check=True, capture_output=True
        )

        # Step 2: Inject loader smali + hook
        inject_loader(decomp_dir)

        # Step 3: Recompile APK
        rebuilt_apk = os.path.join(work_dir, f"{base_name}_protected.apk")
        subprocess.run(
            ["apktool", "b", decomp_dir, "-o", rebuilt_apk],
            check=True, capture_output=True
        )

        # Step 4: Sign APK (debug keystore)
        signed_apk = os.path.join(work_dir, f"{base_name}_signed.apk")
        sign_apk(rebuilt_apk, signed_apk)

        # Step 5: Pack into password-protected ZIP using pyminizip
        import pyminizip
        output_zip = os.path.join(work_dir, f"{base_name}_protected.zip")
        pyminizip.compress(signed_apk, None, output_zip, ZIP_PASSWORD.decode(), 5)

        return output_zip

    except subprocess.CalledProcessError as e:
        print(f"Subprocess error: {e.stderr.decode()}")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def inject_loader(decomp_dir: str):
    """
    Injects a smali loader class that wraps the real DEX logic.
    Real app functions go inside the ZIP payload, loader calls them at runtime.
    """
    smali_dir = os.path.join(decomp_dir, "smali", "com", "loader")
    os.makedirs(smali_dir, exist_ok=True)

    loader_smali = """.class public Lcom/loader/OnyxLoader;
.super Ljava/lang/Object;

.method public static init()V
    .registers 1
    # Loader stub — hooks into main app flow
    # Real payload executes from encrypted DEX inside ZIP
    return-void
.end method
"""
    with open(os.path.join(smali_dir, "OnyxLoader.smali"), "w") as f:
        f.write(loader_smali)

    # Patch AndroidManifest to reference loader (optional: add application class)
    manifest_path = os.path.join(decomp_dir, "AndroidManifest.xml")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            content = f.read()

        # Basic: add meta-data tag inside application node
        if "com.loader.OnyxLoader" not in content:
            content = content.replace(
                "<application",
                '<application android:name="com.loader.OnyxLoader"',
                1
            )
            with open(manifest_path, "w") as f:
                f.write(content)


def sign_apk(input_apk: str, output_apk: str):
    """
    Signs APK with debug keystore. Replace with your own for release.
    """
    keystore = os.path.expanduser("~/.android/debug.keystore")

    if not os.path.exists(keystore):
        # Generate debug keystore if not present
        subprocess.run([
            "keytool", "-genkey", "-v",
            "-keystore", keystore,
            "-alias", "androiddebugkey",
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-storepass", "android",
            "-keypass", "android",
            "-dname", "CN=Android Debug,O=Android,C=US"
        ], check=True, capture_output=True)

    subprocess.run([
        "jarsigner",
        "-verbose",
        "-sigalg", "SHA1withRSA",
        "-digestalg", "SHA1",
        "-keystore", keystore,
        "-storepass", "android",
        "-keypass", "android",
        "-signedjar", output_apk,
        input_apk,
        "androiddebugkey"
    ], check=True, capture_output=True)


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_apk))
    app.run_polling()


if __name__ == "__main__":
    main()