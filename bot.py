import logging
import os
import re
import asyncio
import tempfile
import shutil
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo
import requests
import json
import time
from urllib.parse import urlparse, parse_qs

# Lấy bot token và API URL từ biến môi trường
API_URL = os.getenv('API_URL')
API_TB = os.getenv('API_TB')
API_PDD = os.getenv('API_PDD')
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')

# Thiết lập logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Pyrogram client
app = Client("my_bot", api_id=TELEGRAM_API_ID, api_hash=TELEGRAM_API_HASH, bot_token=TELEGRAM_BOT_TOKEN)

# Start command handler
@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text('Xin chào! Hãy gửi mã kiện hàng của bạn để tôi tra cứu.')
    logger.info('Bot started.')

# Message handler
@app.on_message(filters.text & ~filters.command)
async def handle_message(client, message):
    message_text = message.text.strip()
    if message_text.startswith('https://item.taobao.com/'):
        taobao_id = extract_taobao_id(message_text)
        if taobao_id:
            url = API_TB
            payload = {'idsp': taobao_id}
            headers = {'Content-Type': 'application/json'}
            async with app.http_client.post(url, headers=headers, json=payload) as response:
                if response.status_code == 200:
                    data = response.json()
                    img_urls = data.get('imageLinks', []) + data.get('skuImages', []) + data.get('videoLinks', []) + data.get('descIMG', []) + data.get('descVideo', [])
                    cleaned_urls = [clean_image_url(url) for url in img_urls]
                    await download_and_send_media(message, cleaned_urls)
                else:
                    await message.reply_text('Failed to fetch image details.')
                    logger.error('Failed to fetch image details from API_TB.')
        else:
            await message.reply_text('Invalid Taobao link format.')
            logger.warning('Invalid Taobao link format.')
    elif message_text.startswith('https://mobile.yangkeduo.com/'):
        pattern = re.compile(r'goods\d*\.html')
        if pattern.search(message_text):
            urlpdd = API_PDD
            payload = {'linksp': message_text}
            headers = {'Content-Type': 'application/json'}
            async with app.http_client.post(urlpdd, headers=headers, json=payload) as response:
                if response.status_code == 200:
                    data = response.json()
                    img_urls = data.get('topGallery', []) + data.get('viewImage', []) + data.get('detailGalleryUrl', []) + data.get('videoGallery', []) + data.get('liveVideo', [])
                    cleaned_urls = [clean_image_url(url) for url in img_urls]
                    await download_and_send_media(message, cleaned_urls)
                else:
                    await message.reply_text('Failed to fetch image details.')
                    logger.error('Failed to fetch image details from API_PDD.')
        else:
            await message.reply_text('Invalid Pindoudou link format.')
            logger.warning('Invalid Pindoudou link format.')
    else:
        tracking_numbers = re.findall(r'\b\w{10,20}\b', message_text)
        if not tracking_numbers:
            await message.reply_text('Không tìm thấy mã vận đơn hợp lệ trong tin nhắn của bạn.')
            logger.warning('No valid tracking numbers found.')
            return

        if len(tracking_numbers) == 1:
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

        async with app.http_client.get(url) as response:
            if response.status_code == 200:
                data = response.json()
                for tracking_number in tracking_numbers:
                    tracking_infos = [item for item in data if tracking_number in str(item.get('tracking'))]
                    if tracking_infos:
                        for tracking_info in tracking_infos:
                            await send_tracking_info(message, tracking_info)
                    else:
                        await message.reply_text(f'Không tìm thấy mã kiện hàng: {tracking_number}')
                        logger.warning('No tracking info found for %s.', tracking_number)
            else:
                await message.reply_text('Không thể kết nối đến API. Vui lòng thử lại sau.')
                logger.error('Failed to connect to API_URL.')

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
                        # Xóa các tham số query sau dấu "?"
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

    # Chạy bot
    application.run_polling()

if __name__ == '__main__':
    main()
