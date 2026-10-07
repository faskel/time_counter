import time
import requests
from django.core.management.base import BaseCommand
from datetime import datetime
from python313.datetime import timedelta


class Command(BaseCommand):
    help = 'Отправляет отложенное сообщение в IVA'



    def add_arguments(self, parser):
        parser.add_argument('chat_id', type=str, help='ID чата из URL (длинная строка с дефисами)')
        parser.add_argument('text', type=str, help='Текст сообщения')
        parser.add_argument('delay_seconds', type=int, help='Задержка в секундах')
        parser.add_argument('delay_log',type=int, help='как часто выводить печать')
    def handle(self, *args, **options):
        chat_id = options['chat_id']
        # text = options['text']
        delay_log = options['delay_log']
        text = ("Прошу поставить отработки на ПНМ:\n"
                "Понедельник\n"
                "14:00-16:00 – КС РСО/ГУП (201, 41, 57, ЦЗ)\n"                 
                "Вторник\n"
                "14:00-16:00 – КС РСО/ГУП (201, 41, 57, ЦЗ)\n" 
                "Среда \n"
                "14:00-16:00 – КС РСО/ГУП (201, 41, 57, ЦЗ)\n"
                )

        text = text.replace('\n', '\n')
        delay = options['delay_seconds']
        start_time = datetime.now()
        self.stdout.write(f"[{start_time.strftime('%H:%M:%S')}] Таймер запущен, вывод будет каждые {delay_log} сек.")
        end_time = start_time+timedelta(seconds=delay)
        url = f"https://msk-okb-iva.sukhoi.company/api/rest/chats/{chat_id}/send-message"
        # Цикл обратного отсчета

        for remaining in range(delay, 0, -1):
            # Печатаем статус в начале и каждые 600 секунд
            if remaining == delay or remaining % delay_log == 0:
                self.stdout.write(f"[{datetime.now().strftime('%H:%M:%S')}] Сообщение будет отправлено через {remaining} сек., {end_time.strftime('%d.%m.%y %H:%M:%S')}")
            time.sleep(1)

            # Опционально: можно добавить прерывание через Ctrl+C, чтобы выходило красиво

            # Сама отправка
        url = f"https://msk-okb-iva.sukhoi.company/api/rest/chats/{chat_id}/send-message"

        # Не забудьте обновить cookie_string, если она протухла
        cookie_string = "locale=ru; mediaProfileId=15; allowVideoControl=false; allowAudioControl=false; turnOnCamOnStart=false; turnOnMicOnStart=true; clientSettings=B525%2520HD%2520Webcam%2520(046d%253A0836)%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A-1%253A%253A%253A%253A%253A-1%253A%253A%253A%253A%253Afalse%253A%253A%253A%253A%253A%253A%253A%253A%253A%253Afalse%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A; micLevel=50; speakerLevel=100; ignoreBrowserCheck=true; userSessionId=f7212c21-5077-42f8-a854-f6115780da0e; loginToken=se7062781-cd3a-4650-860b-e6c17ac978f4"

        headers = {
            "Cookie": cookie_string,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        }

        payload = {"message": text}

        try:
            # verify=False для обхода ошибки SSL во внутренней сети
            response = requests.post(url, json=payload, headers=headers, verify=False)
            if response.status_code == 200:
                self.stdout.write(self.style.SUCCESS(f"[{datetime.now().strftime('%H:%M:%S')}] Успешно отправлено!"))
            else:
                self.stdout.write(self.style.ERROR(f"Ошибка {response.status_code}: {response.text}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Ошибка соединения: {e}"))


