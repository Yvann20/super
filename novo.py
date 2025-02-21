import os
import re
import json
import time
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError

# Configuração inicial
load_dotenv()
CACHE_DIR = Path('cache')
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL = 3600

# Configuração de logging
logger = logging.getLogger(__name__)
handler = RotatingFileHandler('bot.log', maxBytes=1e6, backupCount=3)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Variáveis de ambiente
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
YOUR_PHONE = os.getenv('YOUR_PHONE')

if not all([API_ID, API_HASH, BOT_TOKEN, YOUR_PHONE]):
    raise ValueError("Defina todas as variáveis de ambiente necessárias.")

client = TelegramClient('session_name', API_ID, API_HASH)

# Estados da conversação
LINK, INTERVAL = range(2)

# Estruturas de dados
settings = {
    'message_link': None,
    'user_id': None,
}

statistics = {
    'messages_sent': 0,
    'active_campaigns': 0,
}

group_list = []
active_campaigns = {}

# Funções auxiliares
def is_valid_message_link(link: str) -> bool:
    pattern = r"https://t\.me/[a-zA-Z0-9_]+/\d+"
    return re.match(pattern, link) is not None

def is_valid_interval(interval: int) -> bool:
    return 1 <= interval <= 1440

def save_state():
    data = {
        'active_campaigns': {
            uid: {k: v for k, v in data.items() if k != 'job'}
            for uid, data in active_campaigns.items()
        },
        'statistics': statistics,
        'settings': settings
    }
    with open('bot_state.json', 'w') as f:
        json.dump(data, f, default=str)

def load_state():
    try:
        with open('bot_state.json', 'r') as f:
            data = json.load(f)
            active_campaigns.update(data.get('active_campaigns', {}))
            statistics.update(data.get('statistics', {}))
            settings.update(data.get('settings', {}))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

# Autenticação
async def authenticate():
    await client.start(phone=YOUR_PHONE)
    if not await client.is_user_authorized():
        await client.send_code_request(YOUR_PHONE)
        await client.sign_in(YOUR_PHONE, input('Código recebido: '))
    logger.info("Autenticação concluída com sucesso.")

# Cache de participantes
async def get_participant_ids(group):
    cache_file = CACHE_DIR / f"{group.id}.json"
    try:
        if cache_file.exists():
            file_mtime = cache_file.stat().st_mtime
            if time.time() - file_mtime < CACHE_TTL:
                with open(cache_file, 'r') as f:
                    return set(json.load(f))
    except Exception as e:
        logger.error(f"Erro no cache: {e}")

    try:
        participants = await client.get_participants(group)
        participant_ids = {p.id for p in participants}
        with open(cache_file, 'w') as f:
            json.dump(list(participant_ids), f)
        return participant_ids
    except Exception as e:
        logger.error(f"Erro ao atualizar cache: {e}")
        return set()

# Atualização automática de grupos
async def refresh_groups():
    while True:
        try:
            await preload_groups()
            logger.info("Lista de grupos atualizada")
            await asyncio.sleep(3600)
        except Exception as e:
            logger.error(f"Erro na atualização de grupos: {e}")
            await asyncio.sleep(600)

async def preload_groups():
    group_list.clear()
    async for dialog in client.iter_dialogs():
        if dialog.is_group and not dialog.archived:
            group_list.append(dialog.entity)
    logger.info(f"Grupos pré-carregados: {len(group_list)}")

# Encaminhamento de mensagens
async def forward_message_with_formatting(context: ContextTypes.DEFAULT_TYPE):
    start_time = time.time()
    try:
        if not settings['message_link']:
            return

        parts = settings['message_link'].split('/')
        message = await client.get_messages(parts[-2], ids=int(parts[-1]))
        me = await client.get_me()
        success_count = 0

        for i, group in enumerate(group_list):
            try:
                if me.id in await get_participant_ids(group):
                    await client.forward_messages(group, message)
                    success_count += 1
                    statistics['messages_sent'] += 1
                    
                    if (i + 1) % 20 == 0:
                        await asyncio.sleep(10)
                        
            except FloodWaitError as fwe:
                logger.warning(f"FloodWait: Esperando {fwe.seconds} segundos")
                await asyncio.sleep(fwe.seconds)
            except Exception as e:
                logger.error(f"Erro no envio para grupo {group.id}: {e}")

        logger.info(f"Mensagens enviadas: {success_count}/{len(group_list)}")
        
    except Exception as e:
        logger.error(f"Erro geral no encaminhamento: {e}")
    finally:
        logger.info(f"Tempo de execução: {time.time() - start_time:.2f}s")
        save_state()

# Gestão de jobs
def manage_jobs(job_queue, user_id, interval):
    if user_id in active_campaigns:
        active_campaigns[user_id]['job'].schedule_removal()
        del active_campaigns[user_id]

    job = job_queue.run_repeating(
        forward_message_with_formatting,
        interval=interval * 60,
        first=0
    )
    
    active_campaigns[user_id] = {
        'job': job,
        'start_time': time.time(),
        'interval': interval
    }
    
    statistics['active_campaigns'] = len(active_campaigns)
    save_state()

# Handlers do Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    
    welcome_msg = (
        f"🚀 BOT DE MARKETING AUTOMATIZADO 🚀\n\n"
        f"📅 Início: {now}\n"
        f"🆔 Seu ID: {user_id}\n\n"
        "Selecione uma opção:"
    )

    keyboard = [
        [InlineKeyboardButton("🚀 INICIAR CAMPANHA", callback_data='create_campaign')],
        [InlineKeyboardButton("🛑 PARAR CAMPANHA", callback_data='cancel_campaign')],
        [InlineKeyboardButton("📊 ESTATÍSTICAS", callback_data='statistics')],
    ]

    await update.message.reply_text(welcome_msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id in active_campaigns:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "⚠️ Você já tem uma campanha ativa!",
            show_alert=True
        )
        return ConversationHandler.END
        
    await update.callback_query.answer()
    await update.callback_query.edit_message_text('Envie o link da mensagem:')
    return LINK

async def set_message_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text
    if not is_valid_message_link(link):
        await update.message.reply_text("❌ Link inválido! Formato correto: https://t.me/grupo/123")
        return LINK
    
    settings['message_link'] = link
    await update.message.reply_text("✅ Link salvo! Agora envie o intervalo em minutos (1-1440):")
    return INTERVAL

async def set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        interval = int(update.message.text)
        if not is_valid_interval(interval):
            raise ValueError
            
        user_id = update.effective_user.id
        await preload_groups()
        manage_jobs(context.application.job_queue, user_id, interval)
        await update.message.reply_text(f"✅ Campanha iniciada! Intervalo: {interval} minutos")
        logger.info(f"Nova campanha: User {user_id}, Intervalo {interval}min")
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Intervalo inválido! Use números entre 1 e 1440.")
        return INTERVAL

async def cancel_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in active_campaigns:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text("❌ Nenhuma campanha ativa para cancelar.")
        return

    active_campaigns[user_id]['job'].schedule_removal()
    del active_campaigns[user_id]
    
    statistics['active_campaigns'] = len(active_campaigns)
    await update.callback_query.answer()
    await update.callback_query.message.edit_text("✅ Campanha cancelada com sucesso!")
    save_state()

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    stats_message = (
        "📊 Estatísticas:\n"
        f"• Mensagens enviadas: {statistics['messages_sent']}\n"
        f"• Campanhas ativas: {statistics['active_campaigns']}"
    )
    await update.callback_query.message.reply_text(stats_message)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    logger.error(f"Erro não tratado: {error}", exc_info=True)
    
    if update and update.message:
        await update.message.reply_text("⚠️ Ocorreu um erro inesperado. Tente novamente mais tarde.")

def main():
    load_state()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(authenticate())
        loop.create_task(refresh_groups())
        
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        application.add_error_handler(error_handler)

        # Handlers
        conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(start_campaign, pattern='create_campaign')],
            states={
                LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_message_link)],
                INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_interval)],
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(show_statistics, pattern='statistics'))
        application.add_handler(CallbackQueryHandler(cancel_campaign, pattern='cancel_campaign'))
        application.add_handler(conv_handler)

        # Recriar jobs ativos
        for user_id, data in active_campaigns.items():
            manage_jobs(application.job_queue, user_id, data['interval'])
            logger.info(f"Campanha recarregada: User {user_id}, Intervalo {data['interval']}min")

        application.run_polling()
        
    finally:
        if client.is_connected():
            loop.run_until_complete(client.disconnect())
        save_state()
        loop.close()

if __name__ == '__main__':
    main()
