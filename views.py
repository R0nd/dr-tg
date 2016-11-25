import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


class KoImg(object):
    """
    Графическое представление КО.
    Использование:
    ko = KoImg(['1', '2', '1+'])
    ko.img
    """
    code_color = (40, 180, 40)
    pie_color = (180, 40, 40)
    pie_color_closed = (18, 72, 153)
    number_color = (0, 0, 0)
    border_color = (100, 100, 100)
    size = (200, 300)
    font_frac = 0.6  # Процент буквы от клетки

    def __init__(self, ko_list):
        l = len(ko_list)

        if l > 10:
            self.size = self.size[0] * 2, self.size[1] * 2

        self.img = Image.new('RGB', self.size, (255, 255, 255))
        self.draw = ImageDraw.Draw(self.img)
        # self.font_path = 'arial.ttf'
        self.font_path = os.path.abspath('./arial.ttf')

        # Рассчитываем ширину и длину клетки в зависимости от кол-ва кодов. Есть несколько интервалов:
        # 0-10, 10-20, 20-40, 40-80, 80-160

        self.cell_width = self.size[0] // 2
        self.cell_height = self.size[1] // 5
        if l > 10:
            self.cell_height //= 2
        if l > 20:
            self.cell_width //= 2
        if l > 40:
            self.cell_height //= 2
        if l > 80:
            self.cell_width //= 2

        self.row_count = self.size[1] // self.cell_height
        self.font_size = int(self.font_frac * self.cell_height)
        try:
            self.font = ImageFont.truetype(self.font_path, self.font_size)
        except IOError:
            self.font = ImageFont.load_default()
        self.draw_lattice()
        self.draw_numbers(len(ko_list))
        self.write_ko(ko_list)

        f = BytesIO()
        self.img.save(f, format='png')
        self.content = f.getvalue()

    def draw_lattice(self):
        for y in range(int(self.cell_height), self.img.size[1], self.cell_height):
            self.draw.line((0, y, self.img.size[1], y), fill=self.border_color)
        for x in range(self.cell_width, self.img.size[0], self.cell_width):
            self.draw.line((x, 0, x, self.img.size[1]), fill=self.border_color)

    def draw_numbers(self, count):
        for i in range(count):
            x = self.cell_width * (i // self.row_count)
            x += int((1 - self.font_frac) * 0.1 * self.cell_width)

            y = self.cell_height * (i % self.row_count)
            y += int((1 - self.font_frac) * 0.5 * self.cell_height)
            self.draw.text((x, y), '{:2d}'.format(i + 1), font=self.font, fill=self.number_color)

    def write_ko(self, ko_list):
        for i, ko in enumerate(ko_list):
            x = self.cell_width * (i // self.row_count)
            x += int(self.cell_width * 0.3) + int((1 - self.font_frac) * 0.6 * self.cell_width)
            y = self.cell_height * (i % self.row_count) + int((1 - self.font_frac) * 0.5 * self.cell_height)

            code_color = self.code_color
            # Раскрашиваем трешки в красный цвет
            if '3' in ko:
                r = int(self.font_size * 1.3)
                frx = 0.26
                fry = 0.1
                x1, y1 = int(x - r * frx), int(y - r * fry)
                x2, y2 = int(x + r * (1 - frx)), int(y + r * (1 - fry))
                self.draw.pieslice((x1, y1, x2, y2), 0, 360, fill=self.pie_color)
                code_color = (255, 255, 255)
            if 'V' in ko:
                r = int(self.font_size * 1.3)
                frx = 0.26
                fry = 0.1
                x1, y1 = int(x - r * frx), int(y - r * fry)
                x2, y2 = int(x + r * (1 - frx)), int(y + r * (1 - fry))
                self.draw.pieslice((x1, y1, x2, y2), 0, 360, fill=self.pie_color_closed)

            self.draw.text((x, y), '{:2s}'.format(ko), font=self.font, fill=code_color)


def sector_text(sector):
    """
    Вьюха списка KO в виде текста
    Принимает список кодов в формате [{'ko': '1', 'taken': True}, ...]
    """
    code_list = [x for x in sector['code_list'] if not(x['taken'])]
    l = len(code_list)
    rows = 5 if l <= 10 else 10  # Сколько элементов в колонке.
    cols = 2  # Колонок всегда 2
    pages = l // (rows * cols) + 1  # Кол-во страниц

    result = "{}\n".format(sector['name'])
    result += "```\n"

    for page_index, page in enumerate(range(pages)):  # Номер страницы
        for row_index, row in enumerate(range(rows)):
            for col_index, col in enumerate(range(cols)):
                code_index = page * rows * cols + rows * col + row
                if code_index >= l:
                    continue
                try:
                    code = code_list[code_index]
                except IndexError:
                    continue
                result += "{} {}  {}    ".format(
                    str(code_index + 1).rjust(2),
                    code['ko'].strip().ljust(2),
                    'V' if code['taken'] else ' ',
                )
            result += '\n'

        if page_index != pages - 1:
            result += '\n\n'

    result += "```"

    return result
