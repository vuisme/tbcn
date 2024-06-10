import logging
import os
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, filters, CallbackContext, ApplicationBuilder
import requests
import re

# Lấy bot token và API URL từ biến môi trường
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
API_URL = os.getenv('API_URL')

# Thiết lập logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levellevel)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

# Hàm khởi đầu khi bắt đầu bot
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Xin chào! Hãy gửi mã kiện hàng của bạn để tôi tra cứu.')

# Hàm xử lý tin nhắn nhận được
async def handle_message(update: Update, context: CallbackContext) -> None:
    message_text = update.message.text.strip()
    
    # Kiểm tra xem mã kiện hàng có chứa khoảng trắng và số ở phía sau hay không
    if ' ' in message_text:
        tracking_number, sheet_index = message_text.rsplit(' ', 1)
        if sheet_index.isdigit():
            url = f'{API_URL}?tracking={tracking_number}&sheetIndex={sheet_index}'
        else:
            url = f'{API_URL}?tracking={tracking_number}'
    else:
        tracking_number = message_text
        url = f'{API_URL}?tracking={tracking_number}'

    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        
        # Tìm phần tử trong danh sách có mã kiện hàng phù hợp
        tracking_info = next((item for item in data if str(item.get('tracking')) == tracking_number), None)
        
        if tracking_info:
            tracking = tracking_info.get('tracking', 'Không có mã')
            imgurl = tracking_info.get('imgurl', 'Không có ảnh')
            imgurl = re.sub(r'_(\d+x\d+\.jpg)$', '', imgurl)
            rec = tracking_info.get('rec', False)
            var = tracking_info.get('var', 'Không có thuộc tính')
            sl = tracking_info.get('sl', 'Không có số lượng')
            status = "Đã nhận hàng" if rec else "Chưa nhận hàng"
            message = f"Mã kiện hàng: {tracking}\nTrạng thái đơn hàng: {status}\nSố lượng: {sl}\nThuộc Tính: {var}\nHình ảnh: {imgurl}"
            await update.message.reply_text(message)
        else:
            await update.message.reply_text('Không tìm thấy mã kiện hàng này.')
    else:
        await update.message.reply_text('Không thể tra cứu mã kiện hàng này. Vui lòng thử lại sau.')

def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Thêm các handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Bắt đầu bot
    application.run_polling()

if __name__ == '__main__':
    main()
