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
    if SERVICE_JSON.lower().endswith(".json"):
        candidates = [SERVICE_JSON, f"/app/{SERVICE_JSON}", f"/app/data/{SERVICE_JSON}"]
        file_path = next((p for p in candidates if os.path.exists(p)), None)
        if not file_path:
            raise RuntimeError(f"Google service-account file not found: {SERVICE_JSON}")
        with open(file_path, "r", encoding="utf-8") as fh:
            info = json.load(fh)
    else:
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

def add_income(amount, source):
    sh = month_ws(); existing = sh.get("T3:T12"); row = 3
    for i, r in enumerate(existing, start=3):
        if not r or not r[0]: row = i; break
    else: row = 13
    sh.update(f"T{row}:U{row}", [[source, float(amount)]], value_input_option="USER_ENTERED")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["Доход", "Расход"], ["Кредиты", "Долги на сейчас"], ["Отчёт за сегодня"]]
    await update.message.reply_text("Выберите действие:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    step = context.user_data.get("step")
    if t == "Кредиты":
        kb = [["Добавить кредит", "Внести платёж"], ["Назад"]]
        context.user_data["step"] = "credit_menu"
        return await update.message.reply_text("Выберите действие с кредитом:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    if t == "Назад":
        context.user_data.clear()
        return await start(update, context)
    if step == "credit_menu":
        if t == "Добавить кредит":
            context.user_data["step"] = "credit_name"
            return await update.message.reply_text("Напишите название кредитора:")
        if t == "Внести платёж":
            context.user_data["step"] = "credit_payment_name"
            return await update.message.reply_text("Напишите название кредита из таблицы:")
    if step == "credit_name":
        context.user_data["credit_name"] = t.strip(); context.user_data["step"] = "credit_payment"
        return await update.message.reply_text("Введите ежемесячный платёж:")
    if step == "credit_payment":
        if not re.fullmatch(r"\d+(?:[.,]\d{1,2})?", t.strip()): return await update.message.reply_text("Введите сумму платежа, например 15000")
        context.user_data["credit_monthly"] = t.replace(",", "."); context.user_data["step"] = "credit_balance"
        return await update.message.reply_text("Введите остаток долга:")
    if step == "credit_balance":
        if not re.fullmatch(r"\d+(?:[.,]\d{1,2})?", t.strip()): return await update.message.reply_text("Введите остаток долга, например 120000")
        sh = month_ws(); rows = sh.get("G3:G52"); row = next((i for i,r in enumerate(rows,3) if not r or not r[0]),53)
        sh.update(f"G{row}:J{row}", [[context.user_data["credit_name"], "", float(context.user_data["credit_monthly"]), float(t.replace(",", "."))]], value_input_option="USER_ENTERED")
        context.user_data.clear(); return await update.message.reply_text("Кредит добавлен в текущий месяц.")
    if step == "credit_payment_name":
        context.user_data["credit_name"] = t.strip(); context.user_data["step"] = "credit_payment_amount"
        return await update.message.reply_text("Введите сумму внесённого платежа:")
    if step == "credit_payment_amount":
        if not re.fullmatch(r"\d+(?:[.,]\d{1,2})?", t.strip()): return await update.message.reply_text("Введите сумму платежа, например 15000")
        sh = month_ws(); vals = sh.get("G3:L52")
        for i,r in enumerate(vals,3):
            if r and r[0] == context.user_data["credit_name"]:
                sh.update(f"L{i}", [[float(t.replace(",", "."))]], value_input_option="USER_ENTERED")
                context.user_data.clear(); return await update.message.reply_text("Платёж записан.")
        return await update.message.reply_text("Кредит с таким названием не найден.")
    if t in ("Доход", "Расход"):
        context.user_data["kind"] = t
        context.user_data["step"] = "income_amount" if t == "Доход" else "amount"
        await update.message.reply_text("Введите сумму в рублях:")
    elif context.user_data.get("step") == "income_source":
        amount = context.user_data.get("amount")
        add_income(amount, t.strip())
        context.user_data.clear()
        await update.message.reply_text(f"Доход записан: {t.strip()} — {amount} ₽")
    elif context.user_data.get("step") == "income_amount":
        if not re.fullmatch(r"\d+(?:[.,]\d{1,2})?", t.strip()): return await update.message.reply_text("Введите сумму, например 100000 или 1250.50")
        context.user_data["amount"] = t.replace(",", "."); context.user_data["step"] = "income_source"
        await update.message.reply_text("Напишите источник дохода, например: зарплата, подработка или премия:")
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
    q = update.callback_query
    await q.answer()
    try:
        idx = int(q.data.split(":", 1)[1])
        place = PLACES[idx]
        amount = context.user_data.get("amount")
        kind = context.user_data.get("kind", "Расход")
        if not amount:
            return await q.edit_message_text("Сессия ввода истекла. Нажмите «Расход» ещё раз.")
        add_operation(kind, amount, place)
        context.user_data.clear()
        await q.edit_message_text(f"Записал: {place} — {amount} ₽")
    except Exception:
        logging.exception("Failed to save operation from category button")
        await q.edit_message_text("Не удалось записать операцию в таблицу. Я сохранил ошибку в журнале, попробуйте ещё раз.")

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
            x=float(str(r[4]).replace(",",".")); total+=x; key=r[3] if len(r)>3 and r[3] else r[2]; groups[key]=groups.get(key,0)+x
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
