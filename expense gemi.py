import logging
import sqlite3
import matplotlib.pyplot as plt
import pandas as pd
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Matplotlib setup
import matplotlib
matplotlib.use('Agg')

# --- ပြင်ဆင်ချက် ၁: Token ကို Environment Variable ကနေ ယူခြင်း ---
TOKEN = os.getenv('BOT_TOKEN')

# States
CHOOSING, TYPING_AMOUNT, CHOOSING_CATEGORY = range(3)

EXPENSE_CATEGORIES = ["အစားအသောက်", "အရက်ဘီယာ", "အပြင်သွား", "ဖျော်ဖြေရေး", "အခြား"]
INCOME_CATEGORIES = ["လစာ", "စီးပွားရေး", "အခြား"]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Database
def init_db():
    with sqlite3.connect('expenses.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS transactions 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, 
                        amount REAL, category TEXT, date TEXT)''')

def add_transaction(user_id, t_type, amount, category):
    with sqlite3.connect('expenses.db') as conn:
        date = datetime.now().strftime('%Y-%m-%d')
        conn.execute('INSERT INTO transactions (user_id, type, amount, category, date) VALUES (?, ?, ?, ?, ?)',
                     (user_id, t_type, amount, category, date))

def get_summary(user_id):
    with sqlite3.connect('expenses.db') as conn:
        return pd.read_sql_query('SELECT type, amount, category, date FROM transactions WHERE user_id = ?', conn, params=(user_id,))

# Keyboards
def main_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Graph ပြရန်"), KeyboardButton("💰 အနှစ်ချုပ် ကြည့်ရန်")],
        [KeyboardButton("📝 ငွေဝင် မှတ်ရန်"), KeyboardButton("💸 ငွေထွက် မှတ်ရန်")],
        [KeyboardButton("🗑️ Reset (အားလုံးဖျက်ရန်)")]
    ], resize_keyboard=True)

def category_keyboard(categories):
    return ReplyKeyboardMarkup([[KeyboardButton(cat)] for cat in categories], resize_keyboard=True)

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "မင်္ဂလာပါ! ငွေဝင်ငွေထွက် မှတ်တမ်းတင် Bot မှ ကြိုဆိုပါတယ်။",
        reply_markup=main_menu_keyboard()
    )
    return CHOOSING

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if "ငွေဝင်" in text:
        context.user_data['type'] = 'income'
        await update.message.reply_text("ဝင်ငွေ ပမာဏကို ရိုက်ထည့်ပါ (ဥပမာ- 5000)။", reply_markup=ReplyKeyboardRemove())
        return TYPING_AMOUNT
    
    elif "ငွေထွက်" in text:
        context.user_data['type'] = 'expense'
        await update.message.reply_text("ထွက်ငွေ ပမာဏကို ရိုက်ထည့်ပါ (ဥပမာ- 2000)။", reply_markup=ReplyKeyboardRemove())
        return TYPING_AMOUNT
    
    elif "Graph" in text:
        df = get_summary(user_id)
        if df.empty:
            await update.message.reply_text("မှတ်တမ်း မရှိသေးပါ။")
            return CHOOSING
        
        df['date'] = pd.to_datetime(df['date'])
        daily = df.groupby(['date', 'type'])['amount'].sum().unstack(fill_value=0)
        
        plt.figure(figsize=(8, 5))
        daily.plot(kind='bar', color=['green', 'red'] if 'income' in daily.columns else ['red'])
        plt.title('Income vs Expense')
        plt.tight_layout()
        
        path = f'graph_{user_id}.png'
        plt.savefig(path)
        plt.close()
        
        with open(path, 'rb') as photo:
            await update.message.reply_photo(photo, reply_markup=main_menu_keyboard())
        os.remove(path)
        return CHOOSING

    elif "အနှစ်ချုပ်" in text:
        df = get_summary(user_id)
        if df.empty:
            await update.message.reply_text("မှတ်တမ်း မရှိသေးပါ။")
            return CHOOSING

        # စုစုပေါင်း တွက်ချက်ခြင်း
        income_total = df[df['type'] == 'income']['amount'].sum()
        expense_total = df[df['type'] == 'expense']['amount'].sum()
        balance = income_total - expense_total

        # Category အလိုက် အသေးစိတ် ခွဲထုတ်ခြင်း
        summary_text = f"💰 **အနှစ်ချုပ် အစီရင်ခံစာ**\n"
        summary_text += f"━━━━━━━━━━━━━━━\n"
        summary_text += f"📈 **ဝင်ငွေစုစုပေါင်း:** {income_total:,.0f}\n"
        
        # ဝင်ငွေ Category များ
        income_df = df[df['type'] == 'income'].groupby('category')['amount'].sum()
        for cat, amt in income_df.items():
            summary_text += f"  ▫️ {cat}: {amt:,.0f}\n"

        summary_text += f"\n📉 **ထွက်ငွေစုစုပေါင်း:** {expense_total:,.0f}\n"
        
        # ထွက်ငွေ Category များ
        expense_df = df[df['type'] == 'expense'].groupby('category')['amount'].sum()
        for cat, amt in expense_df.items():
            summary_text += f"  ▫️ {cat}: {amt:,.0f}\n"

        summary_text += f"━━━━━━━━━━━━━━━\n"
        summary_text += f"💵 **လက်ကျန်ငွေ:** {balance:,.0f}"

        await update.message.reply_text(summary_text, parse_mode='Markdown', reply_markup=main_menu_keyboard())
        return CHOOSING

    elif "Reset" in text:
        with sqlite3.connect('expenses.db') as conn:
            conn.execute('DELETE FROM transactions WHERE user_id = ?', (user_id,))
        await update.message.reply_text("✅ ဖျက်ပြီးပါပြီ။", reply_markup=main_menu_keyboard())
        return CHOOSING

    return CHOOSING

async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # ကော်မာ ပါလာရင်လည်း ဖယ်ထုတ်ပြီး တွက်နိုင်အောင် ပြင်ထားပါတယ်
        clean_amount = update.message.text.replace(',', '')
        amount = float(clean_amount)
        context.user_data['amount'] = amount
        t_type = context.user_data.get('type')
        cats = INCOME_CATEGORIES if t_type == 'income' else EXPENSE_CATEGORIES
        await update.message.reply_text(f"အမျိုးအစား ရွေးပါ-", reply_markup=category_keyboard(cats))
        return CHOOSING_CATEGORY
    except ValueError:
        await update.message.reply_text("ကျေးဇူးပြု၍ ဂဏန်းသီးသန့် (ဥပမာ - 5000) ရိုက်ပေးပါ!")
        return TYPING_AMOUNT

async def receive_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cat = update.message.text
    amt = context.user_data.get('amount')
    t_type = context.user_data.get('type')

    add_transaction(user_id, t_type, amt, cat)
    await update.message.reply_text(f"✅ {cat} အတွက် {amt:,.0f} မှတ်သားပြီးပါပြီ။", reply_markup=main_menu_keyboard())
    return CHOOSING

if __name__ == '__main__':
    init_db()
    
    # --- ပြင်ဆင်ချက် ၂: Token မရှိရင် Error ပေးအောင် လုပ်ထားခြင်း ---
    if not TOKEN:
        print("Error: BOT_TOKEN environment variable မရှိပါ။ Railway Variables မှာ ထည့်ပေးပါ။")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        
        conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)], # MessageHandler ကို ဒီထဲကနေ ဖယ်လိုက်ပါ
    states={
        CHOOSING: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_choice)],
        TYPING_AMOUNT: [MessageHandler(filters.TEXT & (~filters.COMMAND), receive_amount)],
        CHOOSING_CATEGORY: [MessageHandler(filters.TEXT & (~filters.COMMAND), receive_category)],
    },
    fallbacks=[CommandHandler('start', start)],
    allow_reentry=True
)
        
        app.add_handler(conv_handler)
        print("Bot is running...")
        app.run_polling(drop_pending_updates=True)
