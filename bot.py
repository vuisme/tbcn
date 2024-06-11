import logging
import os
import re
import asyncio
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, CallbackContext, ApplicationBuilder
import requests
import json

# Lấy bot token và API URL từ biến môi trường
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
API_URL = os.getenv('API_URL')
API_TB = os.getenv('API_TB')
# Thiết lập logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

# Hàm khởi đầu khi bắt đầu bot
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Xin chào! Hãy gửi mã kiện hàng của bạn để tôi tra cứu.')

# Hàm xử lý tin nhắn nhận được
async def handle_message(update: Update, context: CallbackContext) -> None:
    message_text = update.message.text.strip()
    if message_text.startswith('https://item.taobao.com/'):
        taobao_id = extract_taobao_id(message_text)
        logging.info(taobao_id)
        if taobao_id:
            url = API_TB
            logging.info(url)
            payload = {'idsp': taobao_id}
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, data=json.dumps(payload))

            if response.status_code == 200:
                data = response.json()
                img_url = data.get('image_url')
                if img_url:
                    await update.message.reply_text(f'Image URL: {img_url}')
                else:
                    await update.message.reply_text('Image not found for this Taobao ID.')
            else:
                await update.message.reply_text('Failed to fetch image details.')
        else:
            await update.message.reply_text('Invalid Taobao link format.')
    else:
        # Lọc ra các mã vận đơn có độ dài từ 10 đến 20 ký tự
        tracking_numbers = re.findall(r'\b\w{10,20}\b', message_text)
    
        if not tracking_numbers:
            await update.message.reply_text('Không tìm thấy mã vận đơn hợp lệ trong tin nhắn của bạn.')
            return
    
        # Kiểm tra số lượng tracking_numbers
        if len(tracking_numbers) == 1:
            # Sử dụng message_text gốc để kiểm tra sheetIndex
            if ' ' in message_text:
                tracking_number, sheet_index = message_text.rsplit(' ', 1)
                if sheet_index.isdigit():
                    url = f'{API_URL}?sheetIndex={sheet_index}'
                else:
                    url = API_URL
            else:
                tracking_number = tracking_numbers[0]
                url = API_URL
    
            tracking_numbers = [tracking_number.strip()]
        else:
            url = API_URL
    
        response = requests.get(url)
    
        if response.status_code == 200:
            data = response.json()
            for tracking_number in tracking_numbers:
                # Lọc các phần tử trong danh sách có mã kiện hàng phù hợp
                tracking_infos = [item for item in data if tracking_number in str(item.get('tracking'))]
                if tracking_infos:
                    for tracking_info in tracking_infos:
                        await send_tracking_info(update, tracking_info)
                else:
                    await update.message.reply_text(f'Không tìm thấy mã kiện hàng: {tracking_number}')
        else:
            await update.message.reply_text('Không thể kết nối đến API. Vui lòng thử lại sau.')

def extract_taobao_id(url: str) -> str:
    # Implement logic to extract Taobao ID from the URL
    # Example: Extract the ID from 'https://item.taobao.com/item.htm?id=123456789'
    taobao_id = url.split('=')[-1]
    return taobao_id
  
async def send_tracking_info(update: Update, tracking_info: dict) -> None:
    tracking = tracking_info.get('tracking', 'Không có mã')
    imgurl = tracking_info.get('imgurl', 'Không có ảnh')
    imgurl = re.sub(r'_(\d+x\d+\.jpg)$', '', imgurl)
    rec = tracking_info.get('rec', False)
    var = tracking_info.get('var', 'Không có thuộc tính')
    sl = tracking_info.get('sl', 'Không có số lượng')
    status = "Đã nhận hàng" if rec else "Chưa nhận hàng"
    message = f"Mã kiện hàng: {tracking}\nTrạng thái đơn hàng: {status}\nSố lượng: {sl}\nThuộc Tính: {var}\nHình ảnh: {imgurl}"
    await update.message.reply_text(message)
    await asyncio.sleep(1)  # Thêm thời gian nghỉ để tránh spam

def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Thêm các handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Bắt đầu bot
    application.run_polling()

if __name__ == '__main__':
    main()
