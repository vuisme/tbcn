import logging
import os
import re
import asyncio
import tempfile
import shutil
from PIL import Image
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CommandHandler, MessageHandler, filters, CallbackContext, ApplicationBuilder
import requests
import json
import time
from urllib.parse import urlparse, parse_qs

# Lấy bot token và API URL từ biến môi trường
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
API_URL = os.getenv('API_URL')
API_TB = os.getenv('API_TB')
API_PDD = os.getenv('API_PDD')

# Thiết lập logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Thiết lập mức độ log cho thư viện httpx
logging.getLogger('httpx').setLevel(logging.WARNING)

# Hàm khởi đầu khi bắt đầu bot
async def start(update: Update, context: CallbackContext) -> None:
    reply_func = get_reply_func(update)
    await reply_func('Xin chào! Hãy gửi mã kiện hàng của bạn để tôi tra cứu.')
    logging.info('Bot started.')

# Hàm để lấy hàm phản hồi phù hợp (business hoặc standard)
def get_reply_func(update: Update):
    if hasattr(update, 'business_message') and update.business_message:
        return update.business_message.reply_text
    else:
        return update.message.reply_text

# Hàm để lấy hàm phản hồi media group phù hợp (business hoặc standard)
def get_reply_media_group_func(update: Update):
    if hasattr(update, 'business_message') and update.business_message:
        return update.business_message.reply_media_group
    else:
        return update.message.reply_media_group

# Hàm xử lý tin nhắn nhận được
async def handle_message(update: Update, context: CallbackContext) -> None:
    message_text = None
    reply_func = get_reply_func(update)

    # Kiểm tra và xử lý tin nhắn từ tài khoản business
    if hasattr(update, 'business_message') and update.business_message:
        message_text = update.business_message.text
        logging.info('Received business message: %s', message_text)
        
        # Kiểm tra nếu tin nhắn bắt đầu bằng "/tb"
        if not message_text.startswith('/tb'):
            return

        # Bỏ qua phần tiền tố "/tb"
        message_text = message_text[3:].strip()

    # Kiểm tra và xử lý tin nhắn trực tiếp
    elif hasattr(update, 'message') and update.message:
        message_text = update.message.text
        logging.info('Received message: %s', message_text)
    
    if message_text:
        # Loại bỏ khoảng trắng đầu và cuối chuỗi
        message_text = message_text.strip()
        
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
                    img_urls = data.get('imageLinks', []) + data.get('skuImages', []) + data.get('videoLinks', []) + data.get('descIMG', []) + data.get('descVideo', [])
                    cleaned_urls = [clean_image_url(url) for url in img_urls]
                    logging.info('Cleaned URLs: %s', cleaned_urls)
                    await download_and_send_media(update, cleaned_urls)
                else:
                    await reply_func('Failed to fetch image details.')
                    logging.error('Failed to fetch image details from API_TB.')
            else:
                await reply_func('Invalid Taobao link format.')
                logging.warning('Invalid Taobao link format.')
        elif message_text.startswith('https://mobile.yangkeduo.com/'):
            pattern = re.compile(r'goods\d*\.html')
            if pattern.search(message_text):
                urlpdd = API_PDD
                logging.info('API_PDD URL: %s', urlpdd)
                payload = {'linksp': message_text}
                headers = {'Content-Type': 'application/json'}
                response = requests.post(urlpdd, headers=headers, data=json.dumps(payload))
                logging.info('API_PDD Response status: %d', response.status_code)

                if response.status_code == 200:
                    data = response.json()
                    logging.info('API_PDD Response data: %s', data)
                    img_urls = data.get('topGallery', []) + data.get('viewImage', []) + data.get('detailGalleryUrl', []) + data.get('videoGallery', []) + data.get('liveVideo', [])
                    cleaned_urls = [clean_image_url(url) for url in img_urls]
                    logging.info('Cleaned URLs: %s', cleaned_urls)
                    await download_and_send_media(update, cleaned_urls)
                else:
                    await reply_func('Failed to fetch image details.')
                    logging.error('Failed to fetch image details from API_PDD.')
            else:
                await reply_func('Invalid Pindoudou link format.')
                logging.warning('Invalid Pindoudou link format.')
        else:
            # Lọc ra các mã vận đơn có độ dài từ 10 đến 20 ký tự
            tracking_numbers = re.findall(r'\b\w{10,20}\b', message_text)
            logging.info('Extracted tracking numbers: %s', tracking_numbers)
        
            if not tracking_numbers:
                await reply_func('Không tìm thấy mã vận đơn hợp lệ trong tin nhắn của bạn.')
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
                        await reply_func(f'Không tìm thấy mã kiện hàng: {tracking_number}')
                        logging.warning('No tracking info found for %s.', tracking_number)
            else:
                await reply_func('Không thể kết nối đến API. Vui lòng thử lại sau.')
                logging.error('Failed to connect to API_URL.')

def extract_taobao_id(url: str) -> str:
    # Implement logic to extract Taobao ID from the URL
    taobao_id = url.split('=')[-1]
    logging.info('Extracted Taobao ID from URL: %s', taobao_id)
    return taobao_id

def clean_image_url(url: str) -> str:
    match = re.match(r'(https://.*?(\.jpg|\.jpeg|\.png|\.gif|\.bmp|\.webp|\.mp4))', url)
    if match:
        cleaned_url = match.group(1)
        logging.info('Cleaned URL: %s', cleaned_url)
        return cleaned_url
    logging.warning('No match found for URL: %s', url)
    return url

async def download_and_send_media(update: Update, media_urls: list) -> None:
    reply_media_group_func = get_reply_media_group_func(update)
    temp_dir = tempfile.mkdtemp()
    logging.info('Created temporary directory: %s', temp_dir)
    try:
        downloaded_files = []
        for media_url in media_urls:
            logging.info('Downloading media: %s', media_url)
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                success = False
                attempts = 0
                while not success and attempts < 3:  # Thử tối đa 3 lần
                    response = requests.get(media_url, headers=headers, stream=True)
                    if response.status_code == 200:
                        # Parse để lấy phần path của URL
                        parsed_url = urlparse(media_url)
                        path = parsed_url.path
                        # Xóa các tham số query sau dấu ?
                        base_filename = os.path.basename(path).split('?')[0]
                        # Lấy phần mở rộng của file từ URL
                        file_extension = os.path.splitext(base_filename)[1]

                        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                            shutil.copyfileobj(response.raw, tmp_file)
                            tmp_file_path = tmp_file.name

                        if not tmp_file_path.endswith('.mp4'):
                            try:
                                with Image.open(tmp_file_path) as img:
                                    if img.size[0] < 200 or img.size[1] < 200:
                                        logging.info('Image %s is too small, skipping.', tmp_file_path)
                                        os.remove(tmp_file_path)
                                        break
                            except Exception as e:
                                logging.error('Error checking image size for %s: %s', tmp_file_path, str(e))
                                os.remove(tmp_file_path)
                                break
                        downloaded_files.append(tmp_file_path)
                        logging.info('Downloaded and saved media to: %s', tmp_file_path)
                        success = True
                    elif response.status_code == 420:
                        logging.warning('Rate limited, waiting to retry: %s', media_url)
                        time.sleep(1)  # Chờ 1 giây trước khi thử lại
                    else:
                        logging.error('Failed to download media: %s, status code: %d', media_url, response.status_code)
                        break
                    attempts += 1

            except Exception as e:
                logging.error('Exception occurred while downloading media: %s, error: %s', media_url, str(e))

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
            await reply_media_group_func(media_group)
            logging.info('Sent media group with %d items.', len(media_group))

    finally:
        # Xóa thư mục tạm sau khi đã gửi tin nhắn
        shutil.rmtree(temp_dir)
        logging.info('Deleted temporary directory: %s', temp_dir)

async def send_tracking_info(update: Update, tracking_info: dict) -> None:
    reply_func = get_reply_func(update)
    tracking = tracking_info.get('tracking', 'Không có mã')
    imgurl = tracking_info.get('imgurl', 'Không có ảnh')
    imgurl = re.sub(r'_(\d+x\d+\.jpg)$', '', imgurl)
    rec = tracking_info.get('rec', False)
    var = tracking_info.get('var', 'Không có thuộc tính')
    sl = tracking_info.get('sl', 'Không có số lượng')
    status = "Đã nhận hàng" if rec else "Chưa nhận hàng"
    message = f"Mã kiện hàng: {tracking}\nTrạng thái đơn hàng: {status}\nSố lượng: {sl}\nThuộc Tính: {var}\nHình ảnh: {imgurl}"
    await reply_func(message)
    logging.info('Sent tracking info message: %s', message)
    await asyncio.sleep(1)  # Thêm thời gian nghỉ để tránh spam

def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Thêm các handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Chạy bot
    application.run_polling()

if __name__ == '__main__':
    main()
