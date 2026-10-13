import os, json, re, logging
from datetime import datetime, time, timedelta
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
SERVICE_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
MONTHS = ["Октябрь 2026","Ноябрь 2026","Декабрь 2026","Январь 2027","Февраль 2027","Март 2027","Апрель 2027","Май 2027","Июнь 2027","Июль 2027","Август 2027","Сентябрь 2027","Октябрь 2027"]
PLACES = ["Еда","Напитки","Магазины у дома","Аллея","Командор","Пятёрочка","Красное и Белое","Бристоль","Wildberries","Ozon","Кафе Малинники","Аренда квартиры","Коммунальные услуги","Связь Мегафон","Домашний интернет","Яндекс","Иви","ChatGPT","Подписки сервисов","Транспорт","Здоровье","Развлечения","Одежда","Химия","Подарки","Другое"]

def ws():
    if not SERVICE_JSON: raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not configured")
    info = json.loads(SERVICE_JSON)
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(SHEET_ID)

def month_ws(book=None):
    book = book or ws(); now = datetime.now()
    name = f"{['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'][now.month-1]} {now.year}"
    return book.worksheet(name) if name in MONTHS else book.worksheet(MONTHS[0])

def add_operation(kind, amount, place):
    sh = month_ws(); existing = sh.get("A3:A102"); row = 3
    for i, r in enumerate(existing, start=3):
        if not r or not r[0]: row = i; break
    else: row = 103
    sh.update(f"A{row}:E{row}", [[datetime.now().strftime("%d.%m.%Y"), kind, place, place, float(amount)]], value_input_option="USER_ENTERED")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["Доход", "Расход"], ["Долги на сейчас", "Отчёт за сегодня"]]
    await update.message.reply_text("Выберите действие:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t in ("Доход", "Расход"):
        context.user_data["kind"] = t
        context.user_data["step"] = "amount"
        await update.message.reply_text("Введите сумму в рублях:")
    elif context.user_data.get("step") == "amount":
        if not re.fullmatch(r"\d+(?:[.,]\d{1,2})?", t.strip()): return await update.message.reply_text("Введите сумму, например 400 или 1250.50")
        context.user_data["amount"] = t.replace(",", "."); context.user_data["step"] = "place"
        buttons = [[InlineKeyboardButton(p, callback_data=f"place:{i}")] for i,p in enumerate(PLACES)]
        await update.message.reply_text("Выберите категорию / место:", reply_markup=InlineKeyboardMarkup(buttons))
    elif t == "Долги на сейчас":
        await debts(update)
    elif t == "Отчёт за сегодня":
        await report(update)

async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); idx=int(q.data.split(":")[1]); place=PLACES[idx]
    amount=context.user_data["amount"]; kind=context.user_data.get("kind","Расход")
    add_operation(kind, amount, place)
    context.user_data.clear(); await q.edit_message_text(f"Записал: {place} — {amount} ₽")

async def debts(update):
    sh=month_ws(); vals=sh.get("G3:L52"); lines=[]; total=0
    for r in vals:
        if r and r[0] and len(r)>=4:
            bal=r[3] if len(r)>3 else ""; lines.append(f"{r[0]}: остаток {bal} ₽")
    await update.message.reply_text("Долги на сейчас:\n"+("\n".join(lines) if lines else "Кредиты пока не внесены."))

async def report(update):
    sh=month_ws(); vals=sh.get("A3:E102"); total=0; groups={}
    for r in vals:
        if len(r)>=5 and r[1]=="Расход" and r[4]:
            x=float(r[4].replace(",",".")); total+=x; groups[r[2]]=groups.get(r[2],0)+x
    body="\n".join(f"{k}: {v:.2f} ₽" for k,v in sorted(groups.items(), key=lambda x:-x[1]))
    await update.message.reply_text(f"Расходы за день: {total:.2f} ₽\n{body or 'Расходов нет.'}")

async def daily_job(context):
    # Add TELEGRAM_USER_ID to enable scheduled private reports.
    uid=os.environ.get("TELEGRAM_USER_ID")
    if uid:
        class M: pass
        m=M(); m.chat_id=int(uid)
        await report(type("U",(),{"message":m})())

def main():
    app=Application.builder().token(TOKEN).build(); app.add_handler(CommandHandler("start", start)); app.add_handler(CallbackQueryHandler(choose, pattern="^place:")); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    app.job_queue.run_daily(daily_job, time=time(22,0), name="daily-report")
    app.run_polling()

if __name__ == "__main__": main()
