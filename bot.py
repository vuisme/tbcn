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
from urllib.parse import urlparse

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
    await get_reply_func(update)('Xin chào! Hãy gửi mã kiện hàng của bạn để tôi tra cứu.')
    logging.info('Bot started.')

# Hàm lấy hàm phản hồi phù hợp dựa trên loại tin nhắn
def get_reply_func(update: Update):
    if hasattr(update, 'business_message') and update.business_message:
        return update.business_message.reply_text
    elif hasattr(update, 'message') and update.message:
        return update.message.reply_text

def get_reply_media_group_func(update: Update):
    if hasattr(update, 'business_message') and update.business_message:
        return update.business_message.reply_media_group
    elif hasattr(update, 'message') and update.message:
        return update.message.reply_media_group

# Hàm xử lý tin nhắn nhận được
async def handle_message(update: Update, context: CallbackContext) -> None:
    reply_func = get_reply_func(update)
    reply_media_group_func = get_reply_media_group_func(update)
    message_text = None

    # Kiểm tra và xử lý tin nhắn từ tài khoản business
    if hasattr(update, 'business_message') and update.business_message:
        message_text = update.business_message.text
        if not message_text.startswith('/tb'):
            return  # Bỏ qua nếu tin nhắn không bắt đầu bằng "/tb"
        message_text = message_text[3:].strip()  # Bỏ "/tb" khỏi đầu tin nhắn

    # Kiểm tra và xử lý tin nhắn trực tiếp
    elif hasattr(update, 'message') and update.message:
        message_text = update.message.text
    
    if message_text:
        # Loại bỏ khoảng trắng đầu và cuối chuỗi
        message_text = message_text.strip()
        await reply_func("Đang phân tích liên kết...")

        if message_text.startswith('https://item.taobao.com/'):
            taobao_id = extract_taobao_id(message_text)
            if taobao_id:
                url = API_TB
                payload = {'id': taobao_id}
                headers = {'Content-Type': 'application/json'}
                response = requests.post(url, headers=headers, data=json.dumps(payload))

                if response.status_code == 200:
                    data = response.json()
                    logger.info(data)
                    img_urls = data.get('images', []) + data.get('skubaseImages', []) + data.get('video', [])
                    logger.info(img_urls)
                    cleaned_urls = []
                    for item in img_urls:
                        logger.info(item)
                        
                        # Xác định kiểu dữ liệu và xử lý
                        if isinstance(item, dict) and 'url' in item and isinstance(item['url'], str):
                            cleaned_url = clean_image_url(item['url'])
                            cleaned_urls.append(cleaned_url)
                        else:
                            logger.info(f"Invalid data structure or type: {item}")
                            pass
                    await download_and_send_media(update, cleaned_urls, reply_func, reply_media_group_func)
                else:
                    await reply_func('Failed to fetch image details.')
            else:
                await reply_func('Invalid Taobao link format.')
        
        elif message_text.startswith('https://mobile.yangkeduo.com/'):
            pattern = re.compile(r'goods\d*\.html')
            if pattern.search(message_text):
                urlpdd = API_PDD
                payload = {'linksp': message_text}
                headers = {'Content-Type': 'application/json'}
                response = requests.post(urlpdd, headers=headers, data=json.dumps(payload))

                if response.status_code == 200:
                    data = response.json()
                    img_urls = data.get('topGallery', []) + data.get('viewImage', []) + data.get('detailGalleryUrl', []) + data.get('videoGallery', []) + data.get('liveVideo', [])
                    cleaned_urls = list(set(clean_image_url(url) for url in img_urls))
                    await download_and_send_media(update, cleaned_urls, reply_func, reply_media_group_func)
                else:
                    await reply_func('Failed to fetch image details.')
            else:
                await reply_func('Invalid Pindoudou link format.')
        else:
            # Lọc ra các mã vận đơn có độ dài từ 10 đến 20 ký tự
            tracking_numbers = re.findall(r'\b\w{10,20}\b', message_text)
    
            if not tracking_numbers:
                await reply_func('Không tìm thấy mã vận đơn hợp lệ trong tin nhắn của bạn.')
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
                            await send_tracking_info(update, tracking_info, reply_func)
                    else:
                        await reply_func(f'Không tìm thấy mã kiện hàng: {tracking_number}')
            else:
                await reply_func('Không thể kết nối đến API. Vui lòng thử lại sau.')

def extract_taobao_id(url: str) -> str:
    # Implement logic to extract Taobao ID from the URL
    taobao_id = url.split('=')[-1]
    return taobao_id

def clean_image_url(url: str) -> str:
    match = re.match(r'(https://.*?(\.jpg|\.jpeg|\.png|\.gif|\.bmp|\.webp|\.mp4))', url)
    if match:
        cleaned_url = match.group(1)
        return cleaned_url
    return url

async def download_and_send_media(update: Update, media_urls: list, reply_func, reply_media_group_func) -> None:
    await reply_func("Đang tải ảnh lên...")

    temp_dir = tempfile.mkdtemp()
    try:
        downloaded_files = []
        for media_url in media_urls:
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
                        success = True
                    elif response.status_code == 420:
                        time.sleep(1)  # Chờ 1 giây trước khi thử lại
                    else:
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

        await reply_func("Gửi tin nhắn hoàn tất.")
    except Exception as e:
        await reply_func("Đã xảy ra lỗi trong quá trình gửi tin nhắn.")
        logging.error('Error during media download or send: %s', str(e))
    finally:
        shutil.rmtree(temp_dir)

async def send_tracking_info(update: Update, tracking_info: dict, reply_func) -> None:
    tracking = tracking_info.get('tracking', 'Không có mã')
    imgurl = tracking_info.get('imgurl', 'Không có ảnh')
    imgurl = re.sub(r'_(\d+x\d+\.jpg)$', '', imgurl)
    rec = tracking_info.get('rec', False)
    var = tracking_info.get('var', 'Không có thuộc tính')
    sl = tracking_info.get('sl', 'Không có số lượng')
    status = "Đã nhận hàng" if rec else "Chưa nhận hàng"
    message = f"Mã kiện hàng: {tracking}\nTrạng thái đơn hàng: {status}\nSố lượng: {sl}\nThuộc Tính: {var}\nHình ảnh: {imgurl}"
    await reply_func(message)
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
