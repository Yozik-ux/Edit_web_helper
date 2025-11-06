import logging
import html
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from newspaper import Article, ArticleException
import language_tool_python

# --- НАЛАШТУВАННЯ ---

# ❗️ Вставте ваш токен, отриманий від @BotFather
TOKEN = "8576532219:AAH6ByMlWv19cMhKi7ZDPyq0E_Sbp39NfbY" 

# Налаштування логування (для пошуку помилок)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ІНІЦІАЛІЗАЦІЯ ПЕРЕВІРКИ МОВИ ---
# Це може зайняти кілька секунд при першому запуску, 
# оскільки завантажуються моделі.
try:
    logger.info("Завантаження мовних моделей (uk-UA)...")
    lang_tool = language_tool_python.LanguageTool('uk-UA')
    logger.info("Мовні моделі завантажено.")
except Exception as e:
    logger.error(f"НЕ МОЖЛИВО ЗАПУСТИТИ LanguageTool. Переконайтесь, що у вас встановлена Java. Помилка: {e}")
    # Якщо ми не можемо запустити інструмент, боту немає сенсу працювати.
    exit()

# --- ФУНКЦІЇ БОТА ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start"""
    user = update.effective_user
    await update.message.reply_html(
        f"Привіт, {user.first_name}!\n\n"
        f"Надішліть мені посилання (URL) на будь-яку статтю, і я спробую знайти в ній помилки."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє звичайні текстові повідомлення (URL)"""
    message_text = update.message.text
    
    # Проста перевірка, чи це URL
    if message_text.startswith('http://') or message_text.startswith('https://'):
        await update.message.reply_text("Отримав посилання. Починаю аналіз... 🧐\nЦе може зайняти до хвилини.")
        
        try:
            # Викликаємо основну логіку обробки
            await check_article_url(update, message_text)
        except Exception as e:
            logger.error(f"Критична помилка під час обробки {message_text}: {e}", exc_info=True)
            await update.message.reply_text(f"Вибачте, сталася непередбачувана помилка: {e}")
    else:
        await update.message.reply_text("Будь ласка, надішліть мені повне посилання (URL), що починається з http:// або https://")

async def check_article_url(update: Update, url: str):
    """Основна логіка: завантажує, парсить та перевіряє статтю"""
    
    try:
        # 1. Завантаження та парсинг статті
        logger.info(f"Обробка URL: {url}")
        article = Article(url)
        article.download()
        article.parse()
        
        text = article.text
        title = article.title

        if not text:
            await update.message.reply_text("Не зміг витягнути текст статті з цього посилання. 😥\nМожливо, сайт захищений від скрапінгу або має незвичну структуру.")
            return

        logger.info(f"Стаття '{title}' успішно завантажена. Довжина тексту: {len(text)} символів.")

        # 2. Перевірка тексту на помилки
        matches = lang_tool.check(text)
        
        if not matches:
            await update.message.reply_text(f"✅ Чудово! У статті '{title}' не знайдено жодних помилок.")
            return

        # 3. Форматування результатів
        logger.info(f"Знайдено {len(matches)} помилок у '{title}'.")
        
        results_header = f"🔍 Знайдено **{len(matches)}** помилок у статті:\n**{title}**\n\n"
        
        # Використовуємо HTML для форматування, оскільки він надійніший
        response_messages = []
        
        # Обмежимо кількість помилок, щоб не спамити (наприклад, перші 15)
        for match in matches[:15]:
            # Екрануємо HTML-теги в оригінальному тексті, щоб уникнути конфліктів
            sentence = html.escape(match.sentence)
            error_word = html.escape(match.sentence[match.offsetInContext : match.offsetInContext + match.errorLength])
            
            # Виділяємо помилку жирним
            highlighted_sentence = sentence.replace(error_word, f"<b>{error_word}</b>", 1)
            
            msg = f"📖 <b>Речення:</b>\n<i>«{highlighted_sentence}»</i>\n"
            msg += f"🚫 <b>Проблема:</b> {html.escape(match.message)}\n"
            
            if match.replacements:
                # Беремо першу пропозицію
                suggestion = html.escape(match.replacements[0])
                msg += f"💡 <b>Пропозиція:</b> <code>{suggestion}</code>"
            
            response_messages.append(msg)

        # Розділимо повідомлення, якщо воно занадто довге для Telegram
        current_message = results_header
        # Надсилаємо заголовок
        await update.message.reply_text(results_header, parse_mode=ParseMode.MARKDOWN)

        # Надсилаємо самі помилки
        for msg_part in response_messages:
            # Перевіряємо, чи не перевищить наступне повідомлення ліміт
            if len(current_message + msg_part) > 4096:
                await update.message.reply_text(current_message, parse_mode=ParseMode.HTML)
                current_message = msg_part
            else:
                current_message += "\n\n---\n\n" + msg_part

        # Надіслати залишок
        if current_message:
            await update.message.reply_text(current_message, parse_mode=ParseMode.HTML)
        
        if len(matches) > 15:
            await update.message.reply_text(f"... та ще {len(matches) - 15} помилок.")

    except ArticleException:
        await update.message.reply_text("Не зміг завантажити статтю за цим посиланням. Будь ласка, перевірте URL.")
    except Exception as e:
        logger.error(f"Помилка під час аналізу статті: {e}", exc_info=True)
        await update.message.reply_text(f"Виникла помилка під час аналізу: {e}")

# --- ЗАПУСК БОТА ---

def main():
    """Основна функція запуску бота"""
    if TOKEN == "ВАШ_ТЕЛЕГРАМ_ТОКЕН_ТУТ":
        logger.error("!!! НЕ ВКАЗАНО TELEGRAM ТОКЕН. Відредагуйте файл і вставте свій токен.")
        return

    logger.info("Створення Application...")
    application = Application.builder().token(TOKEN).build()

    # Додавання обробників
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота
    logger.info("Запуск бота...")
    application.run_polling()

if __name__ == "__main__":
    main()