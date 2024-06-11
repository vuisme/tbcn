import logging
import os
import re
import asyncio
import tempfile
import shutil
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CommandHandler, MessageHandler, filters, CallbackContext, ApplicationBuilder
import requests
import json

# Lấy bot token và API URL từ biến môi trường
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
API_URL = os.getenv('API_URL')
API_TB = os.getenv('API_TB')

# Thiết lập logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Hàm khởi đầu khi bắt đầu bot
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Xin chào! Hãy gửi mã kiện hàng của bạn để tôi tra cứu.')
    logging.info('Bot started.')

# Hàm xử lý tin nhắn nhận được
async def handle_message(update: Update, context: CallbackContext) -> None:
    logging.info('Received message: %s', update.message.text)
    message_text = update.message.text.strip()
    if message_text.startswith('https://item.taobao.com/'):
        taobao_id = extract_taobao_id(message_text)
        logging.info('Extracted Taobao ID: %s', taobao_id)
        if taobao_id:
            url = API_TB
            logging.info('API_TB URL: %s', url)
            payload = {'idsp': taobao_id}
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            logging.info('API_TB Response status: %d', response.status_code)

            if response.status_code == 200:
                data = response.json()
                logging.info('API_TB Response data: %s', data)
                img_urls = data.get('imageLinks', []) + data.get('videoLinks', [])
                cleaned_urls = [clean_image_url(url) for url in img_urls]
                logging.info('Cleaned URLs: %s', cleaned_urls)
                await download_and_send_media(update, cleaned_urls)
            else:
                await update.message.reply_text('Failed to fetch image details.')
                logging.error('Failed to fetch image details from API_TB.')
        else:
            await update.message.reply_text('Invalid Taobao link format.')
            logging.warning('Invalid Taobao link format.')
    else:
        # Lọc ra các mã vận đơn có độ dài từ 10 đến 20 ký tự
        tracking_numbers = re.findall(r'\b\w{10,20}\b', message_text)
        logging.info('Extracted tracking numbers: %s', tracking_numbers)
    
        if not tracking_numbers:
            await update.message.reply_text('Không tìm thấy mã vận đơn hợp lệ trong tin nhắn của bạn.')
            logging.warning('No valid tracking numbers found.')
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
        logging.info('API_URL Response status: %d', response.status_code)
    
        if response.status_code == 200:
            data = response.json()
            logging.info('API_URL Response data: %s', data)
            for tracking_number in tracking_numbers:
                # Lọc các phần tử trong danh sách có mã kiện hàng phù hợp
                tracking_infos = [item for item in data if tracking_number in str(item.get('tracking'))]
                logging.info('Filtered tracking infos for %s: %s', tracking_number, tracking_infos)
                if tracking_infos:
                    for tracking_info in tracking_infos:
                        await send_tracking_info(update, tracking_info)
                else:
                    await update.message.reply_text(f'Không tìm thấy mã kiện hàng: {tracking_number}')
                    logging.warning('No tracking info found for %s.', tracking_number)
        else:
            await update.message.reply_text('Không thể kết nối đến API. Vui lòng thử lại sau.')
            logging.error('Failed to connect to API_URL.')

def extract_taobao_id(url: str) -> str:
    # Implement logic to extract Taobao ID from the URL
    taobao_id = url.split('=')[-1]
    logging.info('Extracted Taobao ID from URL: %s', taobao_id)
    return taobao_id

def clean_image_url(url: str) -> str:
    match = re.match(r'(https://.*?(\.jpg|\.mp4))', url)
    if match:
        cleaned_url = match.group(1)
        logging.info('Cleaned URL: %s', cleaned_url)
        return cleaned_url
    logging.warning('No match found for URL: %s', url)
    return url

async def download_and_send_media(update: Update, media_urls: list) -> None:
    temp_dir = tempfile.mkdtemp()
    logging.info('Created temporary directory: %s', temp_dir)
    try:
        downloaded_files = []
        for media_url in media_urls:
            logging.info('Downloading media: %s', media_url)
            response = requests.get(media_url, stream=True)
            if response.status_code == 200:
                file_extension = '.mp4' if media_url.endswith('.mp4') else '.jpg'
                file_name = os.path.basename(media_url).split('_')[0] + file_extension
                file_path = os.path.join(temp_dir, file_name)
                with open(file_path, 'wb') as f:
                    shutil.copyfileobj(response.raw, f)
                downloaded_files.append(file_path)
                logging.info('Downloaded and saved media to: %s', file_path)
            else:
                logging.error('Failed to download media: %s', media_url)

        media_groups = []
        for i in range(0, len(downloaded_files), 9):
            media_group = downloaded_files[i:i + 9]
            media_objects = []
            for file_path in media_group:
                if file_path.endswith('.mp4'):
                    media_objects.append(InputMediaVideo(open(file_path, 'rb')))
                else:
                    media_objects.append(InputMediaPhoto(open(file_path, 'rb')))
            media_groups.append(media_objects)

        for media_group in media_groups:
            await update.message.reply_media_group(media_group)
            logging.info('Sent media group with %d items.', len(media_group))

    finally:
        # Xóa thư mục tạm sau khi đã gửi tin nhắn
        shutil.rmtree(temp_dir)
        logging.info('Deleted temporary directory: %s', temp_dir)

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
    logging.info('Sent tracking info message: %s', message)
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
