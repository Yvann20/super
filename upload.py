from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Diretório onde o script está sendo executado
UPLOAD_FOLDER = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = '7816694561:AAHyDveY-XnNVj6vTREJ_s4bXBRPd5oQ7is'  # Substitua pelo seu token

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Envie o arquivo que deseja fazer upload para a VPS.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    file = await context.bot.get_file(document.file_id)

    file_path = os.path.join(UPLOAD_FOLDER, document.file_name)
    await file.download_to_drive(file_path)

    await update.message.reply_text(f"Arquivo salvo com sucesso em:\n{file_path}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Bot está rodando...")
    app.run_polling()
