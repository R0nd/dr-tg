from datetime import datetime
import os
import codecs
from urllib.parse import urlencode, urljoin

import dataset
from grab.base import Grab
import re

import settings

from decorators import throttle

host = 'http://classic.dzzzr.ru/'
start_url = urljoin(host, 'moscow/')
drive_url = urljoin(host, 'moscow/go/?{}'.format(urlencode({
    'nostat': 'on',
    'notext': '',
    'notags': '',
    'refresh': '30',
    'log': '',
    'legend': '',
    'bonus': 'on',
    'kladMap': '',
    'mes': '',
})))

red_span_re = re.compile('<span style="color:red">([123]\+?|N)</span>')


class Parser(object):
    write_log_files = False

    def __init__(self):
        self.g = Grab()
        self.g.setup(timeout=100)
        self.db = dataset.connect(settings.DATASET)

        self.table_code = self.db['code']
        self.table_sector = self.db['sector']
        self.table_tip = self.db['tip']
        self.table_cookies = self.db['cookies']
        self.table_bot = self.db['bot']

        current_bot = self.table_bot.find_one(**{'token': settings.TOKEN})
        if current_bot is None:
            self.table_bot.insert({
                'token': settings.TOKEN,
                'level': None,
                'spoiler': False,
            })

        for cookie_dict in self.db['cookies']:
            del cookie_dict['id']
            try:
                self.g.cookies.set(**cookie_dict)
            except ValueError:
                pass

    def set_cookie(self, cookie):
        self.g.cookies.set(
            name='dozorSiteSession',
            value=cookie,
            domain='.dzzzr.ru',
            path='/',
        )

    def auth(self, login, password):
        """Авторизация на сайте дозора"""
        self.table_cookies.delete()

        self.g.go(start_url)
        self.g.doc.set_input('login', login)
        self.g.doc.set_input('password', password)
        self.g.doc.submit()
        cookie_list = self.g.cookies.get_dict()

        for cookie_dict in cookie_list:
            self.table_cookies.insert(cookie_dict)

    def set_pin(self, userpwd):
        self.g.setup(userpwd=userpwd)

    @throttle(seconds=2)
    def fetch(self, code=None):
        """Загружает страницу движка"""
        n = datetime.utcnow()

        self.g.go(drive_url)
        if code is not None:
            if self.g.doc.select(b'.//*[@name="cod"]').exists():
                self.g.doc.set_input('cod', code)
                self.g.doc.submit()

        if self.write_log_files:
            dir_1 = "./log/{}".format(n.strftime("%H"))
            dir_2 = "{}/{}".format(dir_1, n.strftime("%H_%M"))
            filepath = "{}/log_{}.html".format(dir_2, n.strftime("%H_%M_%S"))
            if not os.path.exists('./log'):
                os.makedirs('./log')
            if not os.path.exists(dir_1):
                os.makedirs(dir_1)
            if not os.path.exists(dir_2):
                os.makedirs(dir_2)
            with codecs.open(filepath, mode='w+', encoding='utf-8') as f:
                html = self.g.doc.body.decode('cp1251')
                f.write(html)

    def parse(self):
        result = {}
        result.update(self._parse_level())
        result.update(self._parse_tip())
        result.update(self._parse_spoiler())
        result.update(self._parse_message())
        result.update(self._parse_clock())
        return result

    def _parse_message(self):
        if not self.g.doc.select('//div[@class="sysmsg"]//b').exists():
            return {
                'message': ''
            }
        message = self.g.doc.select('//div[@class="sysmsg"]//b').html()
        message = message.replace('<b>', '').replace('</b>', '')
        return {
            'message': message
        }

    def _parse_clock(self):
        result = {

        }
        try:
            div = self.g.doc.select('//*[@id="clock"]')[0]
        except IndexError:
            return result

        clock_str = div.text()

        result = {
            'clock': clock_str
        }
        return result

    def _parse_level(self):
        """
        Парсит страницу дозорного движка. Возвращает словарь с инфой об обновлении.
        Подробнее, что такое инфа обновления - в комментариях ниже
        """
        result = {
            'new_level': False,  # Новый уровень?
            'new_code': False,  # Новый пробитый код?
            'sector_list': [],  # Инфо о взятых кодах
        }
        try:
            div = self.g.doc.select('//div[@class="zad"][1]')[0]
        except IndexError:
            return result
        sector_list_str = div.html()
        level_number_str = div.node().getprevious().text
        level_number_str = re.sub('\D', '', level_number_str)
        level = int(level_number_str)

        bot_data = self.table_bot.find_one(**{'token': settings.TOKEN})

        if bot_data.get('level') != level:
            self.table_bot.upsert({
                'token': settings.TOKEN,
                'level': level,
                'spoiler': False,
            }, ['token'])
            self.table_sector.delete()
            self.table_code.delete()
            self.table_tip.delete()
            result['new_level'] = True

        try:
            sector_list_str = sector_list_str.split('<strong>Коды сложности</strong><br>')[1]
        except IndexError:
            return result
        sector_list_str = sector_list_str.split('<br></div>')[0]
        sector_list_str = sector_list_str.replace('null', 'N')
        for sector_index, sector_str in enumerate(sector_list_str.split('<br>')):
            try:
                sector_name, sector_code_str = sector_str.split(': ')
            except ValueError:
                continue
            sector = {
                'id': sector_index + 1,
                'name': sector_name,
                'code_list': [],
            }
            for metka_index, item in enumerate(sector_code_str.split(', ')):
                taken = bool(red_span_re.match(item))
                ko = red_span_re.findall(item)[0] if taken else item

                old_code = self.table_code.find_one(**{
                    'sector_id': sector_index + 1,
                    'metka': metka_index + 1,
                })
                filters = {
                    'ko': ko,
                    'taken': taken,
                    'metka': metka_index + 1,
                    'sector_id': sector_index + 1,
                }
                if old_code is None:
                    self.table_code.insert(filters)
                elif old_code['taken'] != taken:
                    self.table_code.update(filters, ['sector_id', 'metka'])
                    if 'бонусные коды' not in sector['name']:
                        result['new_code'] = True
                    sector['code_list'].append(filters)

            result['sector_list'].append(sector)
            self.table_sector.upsert({
                'id': sector_index + 1,
                'name': sector_name,
            }, ['id'])
        return result

    def _parse_tip(self):
        """
        Парсит текст подсказок. Возвращает объект обновления
        """
        result = {
            'tip_list': [],  # Новые подсказки.
        }

        div_list = self.g.doc.select('//div[@class="title"]')

        for div in div_list:
            for tip_title, tip_index in (
                ('Подсказка l:', 1),  # здесь нет опечатки, в дозором движке используется именно латинская буква l вместо цифры 1.
                ('Подсказка 2:', 2),
            ):
                if tip_title in div.html():
                    tip_node = div.node().getnext()
                    for br in tip_node.xpath("*//br"):
                        br.tail = "\n" + br.tail if br.tail else "\n"
                    tip_text = tip_node.text_content()
                    if 'не предусмотрена' in tip_text.lower():
                        continue
                    old_tip = self.table_tip.find_one(index=tip_index)
                    self.table_tip.upsert({
                        'text': tip_text,
                        'index': tip_index,  # номер подсказки
                    }, ['index'])
                    if old_tip is None:
                        result['tip_list'].append({
                            'text': tip_text,
                            'index': tip_index,
                        })
        return result

    def _parse_spoiler(self):
        """
        Парсит текст спойлера. Возвращает объект обновления
        """
        result = {
            'new_spoiler': False,  # Новый открытый спойлер?
        }

        bot_data = self.table_bot.find_one(**{'token': settings.TOKEN})

        if bot_data.get('spoiler'):
            return result

        try:
            level_div = self.g.doc.select('//div[@class="zad"][1]')[0]
        except IndexError:
            return result

        level_html = level_div.html()
        if '<div class="title" style="padding-left:0">Спойлер</div>' in level_html:
            result['new_spoiler'] = True
            self.table_bot.upsert({
                'token': settings.TOKEN,
                'spoiler': True,
            }, ['token'])

        return result
