import os
import codecs

from grab.error import GrabTimeoutError

import settings

from unittest import TestCase
from unittest.mock import Mock, patch

from bot import DzrBot, HELP_TEXT
from decorators import throttle
from parser import Parser


class BotTestCase(TestCase):
    @patch('parser.settings.DATASET', settings.DATASET_TEST)
    def setUp(self):
        self.parser = Parser()

        settings.CHAT_ID = 'CHAT_ID'
        settings.CHANNEL_ID = 'CHANNEL_ID'
        self.bot = DzrBot(None)
        self.bot.type = True
        self.bot.sendMessage = Mock()
        self.bot.sendLocation = Mock()
        self.bot.sendPhoto = Mock()

        self.bot.parser = self.parser
        self.bot.parser.fetch = Mock()
        self.bot.parser.auth = Mock()

        self.bot.parse = True
        self.bot.code_pattern = None
        self.bot.sentry = None

    def tearDown(self):
        """Очищаем таблицы после прохождения каждого теста"""
        self.parser.table_tip.delete()
        self.parser.table_code.delete()
        self.parser.table_sector.delete()

    def set_html(self, filename):
        """Это метод устанавливает "текущую" страницу дозорного дижка"""
        filepath = os.path.join(os.path.dirname(__file__), filename)
        with codecs.open(filepath, encoding='cp1251') as f:
            html = f.read()
            html_bytes = bytes(html, encoding='cp1251')
            self.parser.g.setup_document(html_bytes)

    def test_help(self):
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/help'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', HELP_TEXT)

    def test_code_pattern(self):
        self.assertEqual(self.bot.code_pattern, None)
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/pattern ['})
        self.bot.sendMessage.assert_any_call('CHAT_ID', 'Шаблон кода не установлен')
        self.bot.sendMessage.reset_mock()

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/pattern \w+\d{2}'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', 'Шаблон кода установлен: \w+\d{2}')
        self.bot.sendMessage.reset_mock()
        self.assertEqual(self.bot.code_pattern, "\w+\d{2}")

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/pattern'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', 'Шаблон кода: \w+\d{2}')
        self.bot.sendMessage.reset_mock()

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/pattern standart'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', 'Установлен стандартный шаблон кода')
        self.bot.sendMessage.reset_mock()
        self.assertEqual(self.bot.code_pattern, None)

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/pattern'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', 'Шаблон кода: стандартный')
        self.bot.sendMessage.reset_mock()

    def test_code_with_pattern(self):
        self.set_html('pages/code_1.html')
        self.parser._parse_message = Mock(return_value={'message': 'код не принят'})
        self.bot.code_pattern = "\w+\d{2}"
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': 'Бла бла бла песок98. Блаблабла', 'message_id': 321})
        self.bot.sendMessage.assert_any_call('CHAT_ID', '00:49. песок98 : код не принят', reply_to_message_id=321)

    def test_code_fail(self):
        """
        Вызываем пробитие кода (dr4).
        Если код неверный, то бот должен послать об этом сообщение в чат
        """
        self.set_html('pages/code_1.html')
        self.parser._parse_message = Mock(return_value={'message': 'код не принят'})
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': 'dr4', 'message_id': 321})
        self.bot.sendMessage.assert_any_call('CHAT_ID', '00:49. dr4 : код не принят', reply_to_message_id=321)

    def test_code_empty(self):
        """
        Нестандартный код пишется через слэш
        """
        self.set_html('pages/code_1.html')
        self.parser._parse_message = Mock(return_value={'message': 'код не принят'})
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/ НЕСТАНДАРТНЫЙКОД1', 'message_id': 321})
        self.bot.sendMessage.assert_any_call('CHAT_ID', '00:49. нестандартныйкод1 : код не принят', reply_to_message_id=321)

    def test_new_level(self):
        """Если наступает новый уровень, то бот должен послать об этом сообщение в канал"""
        self.set_html('pages/tip_1.html')
        self.parser.parse()
        self.set_html('pages/code_1.html')
        self.bot.handle_loop()
        self.bot.sendMessage.assert_any_call('CHANNEL_ID', 'Новый уровень')

    def test_new_tip(self):
        """Если возникает новая подсказка, то бот должен послать об этом сообщение в канал"""
        self.set_html('pages/tip_1.html')
        self.parser.parse()
        self.set_html('pages/tip_2.html')
        self.bot.handle_loop()
        self.bot.sendMessage.assert_any_call('CHANNEL_ID', 'Подсказка: Ответ на спойлер: пустырь')

    def test_new_spoiler(self):
        """Если открывается спойлер, то бот должен послать об этом сообщение в канал"""
        self.set_html('pages/spoiler_1.html')
        self.parser.parse()
        self.set_html('pages/spoiler_2.html')
        self.bot.handle_loop()
        self.bot.sendMessage.assert_any_call('CHANNEL_ID', 'Открыт спойлер')

    def test_new_code(self):
        """
        Если в движке появился новый пробитый код,
        то бот должен послать табличку об этом в канал.
        Обратите внимание на взятый код по 11-й метке.
        """
        self.set_html('pages/code_1.html')
        self.parser.parse()
        self.set_html('pages/code_1.html')
        self.parser.parse()
        self.set_html('pages/code_2.html')
        self.bot.handle_loop()
        self.bot.sendMessage.assert_any_call(
            'CHANNEL_ID',
            ' основные коды\n'
            '```\n'
            ' 1 3   V    11 1+       \n'
            ' 2 2   V    12 1   V    \n'
            ' 3 3   V    13 1+  V    \n'
            ' 4 2   V    14 1   V    \n'
            ' 5 2   V    \n'
            ' 6 1   V    \n'
            ' 7 1   V    \n'
            ' 8 2   V    \n'
            ' 9 1   V    \n'
            '10 1+       \n'
            '```',
            parse_mode='Markdown',
        )

        self.bot.sendMessage.reset_mock()
        self.set_html('pages/code_3.html')
        self.bot.handle_loop()

        self.bot.sendMessage.assert_any_call(
            'CHANNEL_ID',
            ' основные коды\n'
            '```\n'
            ' 1 3   V    11 1+  V    \n'
            ' 2 2   V    12 1   V    \n'
            ' 3 3   V    13 1+  V    \n'
            ' 4 2   V    14 1   V    \n'
            ' 5 2   V    \n'
            ' 6 1   V    \n'
            ' 7 1   V    \n'
            ' 8 2   V    \n'
            ' 9 1   V    \n'
            '10 1+       \n'
            '```',
            parse_mode='Markdown',
        )

    def test_type(self):
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/type'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', 'Режим ввода кодов: Включен')

        self.bot.sendMessage.reset_mock()
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/type off'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', 'Режим ввода кодов: Выключен')

        self.bot.sendMessage.reset_mock()
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/type on'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', 'Режим ввода кодов: Включен')

    def test_clock(self):
        self.set_html('pages/code_1.html')
        result = self.parser.parse()
        self.assertEqual(result['clock'], '00:49')

    def test_auth(self):
        """
        аутентификация через команду /auth
        """
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/auth login parol'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Аутентификация установлена. Логин = login")
        self.assertEqual(self.bot.parser.auth.called, True)
        self.bot.sendMessage.reset_mock()

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/auth login'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Ошибка в параметрах аутентификации")
        self.bot.sendMessage.reset_mock()

    def test_test_error(self):
        with self.assertRaises(Exception):
            self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/test_error'})

    def test_pin(self):
        """
        аутентификация через pin
        """
        self.bot.set_data('pin', '')

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/pin'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Пин отсутствует")
        self.bot.sendMessage.reset_mock()

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/pin moscow_cap:123456'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Пин установлен")
        self.bot.sendMessage.reset_mock()
        self.assertEqual(self.bot.get_data().get('pin'), "moscow_cap:123456")

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/pin'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Пин есть: moscow_cap:123456")
        self.bot.sendMessage.reset_mock()

    def test_bool_params(self):
        """
        установка bool параметров
        """

        self.bot.set_data('parse', False)
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/parse on'})
        self.assertEqual(self.bot.get_data().get('parse'), True)
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/parse off'})
        self.assertEqual(self.bot.get_data().get('parse'), False)

        self.bot.set_data('type', False)
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/type on'})
        self.assertEqual(self.bot.get_data().get('type'), True)
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/type off'})
        self.assertEqual(self.bot.get_data().get('type'), False)

    def test_cookie(self):
        """
        аутентификация через команду /cookie
        """
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/cookie KTerByfGopF5dSgFjkl07x8v'})
        self.assertEqual(self.bot.get_data().get('cookie'), "KTERBYFGOPF5DSGFJKL07X8V")
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Кука установлена")

    def test_link(self):
        """
        хранение ссылки /link
        """
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/link link1'})
        self.assertEqual(self.bot.get_data().get('link'), "link1")
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Установлена ссылка link1")
        self.bot.sendMessage.reset_mock()

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/link link2'})
        self.assertEqual(self.bot.get_data().get('link'), "link2")
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Установлена ссылка link2")
        self.bot.sendMessage.reset_mock()

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/link'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Ссылка: link2")
        self.bot.sendMessage.reset_mock()

    def test_sleep_seconds(self):
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/sleep_seconds 10'})
        self.assertEqual(self.bot.get_data().get('sleep_seconds'), 10)
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Установлена sleep_seconds = 10")
        self.bot.sendMessage.reset_mock()

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/sleep_seconds'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', "sleep_seconds = 10")
        self.bot.sendMessage.reset_mock()

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/sleep_seconds 20'})
        self.assertEqual(self.bot.get_data().get('sleep_seconds'), 20)
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Установлена sleep_seconds = 20")
        self.bot.sendMessage.reset_mock()

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/sleep_seconds к'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Ошибка в установке")
        self.bot.sendMessage.reset_mock()

        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/sleep_seconds 5'})
        self.assertEqual(self.bot.get_data().get('sleep_seconds'), 20)
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Время sleep_seconds должно быть в итервале от 10 до 300 секунд. Если вы хотите выключить парсинг движка, воспользуйтесь командой /parse off")
        self.bot.sendMessage.reset_mock()

    def test_status(self):
        self.set_html('pages/code_1.html')
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/status'})
        self.assertTrue(self.bot.parser.fetch.called)

    def test_connection_error(self):
        self.set_html('pages/code_1.html')
        self.bot.parser.fetch = Mock(side_effect=GrabTimeoutError)
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/status'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', "Проблема подключения к движку")

    def test_get_chat_id(self):
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/get_chat_id'})
        self.bot.sendMessage.assert_any_call('CHAT_ID', 'chat id: CHAT_ID')

    def test_cord(self):
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '55.370 37.550'})
        self.bot.sendLocation.assert_any_call('CHAT_ID', '55.370', '37.550')

    def test_ko(self):
        self.set_html('pages/code_1.html')
        self.parser.parse()
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/ko'})
        self.assertTrue(True)

    def test_img(self):
        self.set_html('pages/code_1.html')
        self.parser.parse()
        self.bot.on_chat_message({'chat': {'id': 'CHAT_ID'}, 'text': '/img'})
        self.assertEqual(self.bot.sendPhoto.called, True)


class ThrottleTestCase(TestCase):
    @throttle(seconds=2)
    def f(self):
        return

    @patch('decorators.sleep')
    def test(self, sleep_mock):
        self.f()
        self.f()
        self.assertEqual(sleep_mock.called, True)
        sleep_mock.assert_any_call(1)
