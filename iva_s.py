import time
import requests
from django.core.management.base import BaseCommand
from datetime import datetime


class Command(BaseCommand):
    help = 'Отправляет отложенное сообщение в IVA'

    def add_arguments(self, parser):
        parser.add_argument('chat_id', type=str, help='ID чата из URL (длинная строка с дефисами)')
        parser.add_argument('text', type=str, help='Текст сообщения')
        parser.add_argument('delay_seconds', type=int, help='Задержка в секундах')

    def handle(self, *args, **options):
        chat_id = options['chat_id']
        text = options['text']
        delay = options['delay_seconds']

        # Данные из вашего скриншота
        url = f"https://msk-okb-iva.sukhoi.company/api/rest/chats/{chat_id}/send-message"

        # ВАЖНО: Скопируйте всю строку Cookie из DevTools (вкладка Headers -> Request Headers)
        # Она начинается на "locale=ru; ignoreBrowserCheck=true; ..."
        cookie_string = "locale=ru; ignoreBrowserCheck=true; userSessionId=9068482b-0c25-4645-bf09-0d601cb96fbd; loginToken=l8c2e19e2-7995-4c12-b178-0c1ab224c41b; mediaProfileId=15; allowVideoControl=false; allowAudioControl=false; turnOnCamOnStart=false; turnOnMicOnStart=true; clientSettings=B525%2520HD%2520Webcam%2520(046d%253A0836)%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A-1%253A%253A%253A%253A%253A-1%253A%253A%253A%253A%253Afalse%253A%253A%253A%253A%253A%253A%253A%253A%253A%253Afalse%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A"

        headers = {
            "Cookie": cookie_string,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        }

        # Тело запроса (JSON)
        payload = {
            "message": text
        }

        self.stdout.write(f"[{datetime.now().strftime('%H:%M:%S')}] Ожидание {delay} сек...")
        time.sleep(delay)

        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                self.stdout.write(self.style.SUCCESS(f"Успешно отправлено! Ответ сервера: {response.text}"))
            else:
                self.stdout.write(self.style.ERROR(f"Ошибка {response.status_code}: {response.text}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Ошибка соединения: {e}"))