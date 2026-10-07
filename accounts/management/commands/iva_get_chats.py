import requests
import urllib3

# Отключаем предупреждения об SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_chats():
    url = "https://msk-okb-iva.sukhoi.company/api/rest/contacts?"

    cookie_string = "locale=ru; ignoreBrowserCheck=true; userSessionId=9068482b-0c25-4645-bf09-0d601cb96fbd; loginToken=l8c2e19e2-7995-4c12-b178-0c1ab224c41b; mediaProfileId=15; allowVideoControl=false; allowAudioControl=false; turnOnCamOnStart=false; turnOnMicOnStart=true; clientSettings=B525%2520HD%2520Webcam%2520(046d%253A0836)%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A-1%253A%253A%253A%253A%253A-1%253A%253A%253A%253A%253Afalse%253A%253A%253A%253A%253A%253A%253A%253A%253A%253Afalse%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A%253A"

    headers = {
        "Cookie": cookie_string,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            # data = response.json()
            # # Обычно список чатов лежит в ключе 'items' или прямо в корне
            # chats = data.get('items', data)
            raw_response = response.json()

            chats_list = raw_response.get('data', [])
            print(f"{'Название чата':<40} | {'ID чата'}")
            print("-" * 80)
            if isinstance(chats_list, list):
                for chat in chats_list:
                    name = chat.get('chatRoomName') or chat.get('name') or 'empty'
                    chat_id = chat.get('chatRoomId') or chat.get('id') or 'empty'
            print(f"{str(name):<45} | {str(chat_id)}")
            # for chat in chats:
            #     # Проверяем, что chat это словарь, прежде чем вызывать .get()
            #     name = chat
            #     print(name)
        else:
            print(f"Ошибка: {response.status_code}")
    except Exception as e:
        print(f"Произошла ошибка: {e}")


if __name__ == "__main__":
    get_chats()
