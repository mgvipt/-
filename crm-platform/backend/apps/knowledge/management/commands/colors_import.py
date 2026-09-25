# -*- coding: utf-8 -*-
"""Завантажити довідник кольорів RAL Classic і NCS у CRM (разова дія, можна повторювати)."""
import json
import os

from django.core.management.base import BaseCommand

from apps.knowledge.colors import hex_to_rgb, rgb_to_lab
from apps.knowledge.models import ColorRef

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

# назви RAL українською/російською — складаємо зі слів англійської назви, щоб менеджер шукав по-своєму
WORDS = {
    "green": ("зелений", "зелёный"), "beige": ("бежевий", "бежевый"), "yellow": ("жовтий", "жёлтый"),
    "orange": ("помаранчевий", "оранжевый"), "red": ("червоний", "красный"), "violet": ("фіолетовий", "фиолетовый"),
    "blue": ("синій", "синий"), "grey": ("сірий", "серый"), "gray": ("сірий", "серый"),
    "brown": ("коричневий", "коричневый"), "white": ("білий", "белый"), "black": ("чорний", "чёрный"),
    "light": ("світлий", "светлый"), "dark": ("темний", "тёмный"), "pale": ("блідий", "бледный"),
    "pure": ("чистий", "чистый"), "signal": ("сигнальний", "сигнальный"), "traffic": ("транспортний", "транспортный"),
    "pastel": ("пастельний", "пастельный"), "olive": ("оливковий", "оливковый"), "silver": ("сріблястий", "серебристый"),
    "gold": ("золотий", "золотой"), "copper": ("мідний", "медный"), "pearl": ("перламутровий", "перламутровый"),
    "sand": ("піщаний", "песочный"), "sky": ("небесний", "небесный"), "ocean": ("океанський", "океанский"),
    "moss": ("моховий", "моховой"), "turquoise": ("бірюзовий", "бирюзовый"), "purple": ("пурпуровий", "пурпурный"),
    "pink": ("рожевий", "розовый"), "cream": ("кремовий", "кремовый"), "ivory": ("слонова кістка", "слоновая кость"),
    "anthracite": ("антрацитовий", "антрацитовый"), "graphite": ("графітовий", "графитовый"),
    "concrete": ("бетонний", "бетонный"), "basalt": ("базальтовий", "базальтовый"), "slate": ("сланцевий", "сланцевый"),
    "mouse": ("мишачий", "мышиный"), "stone": ("камʼяний", "каменный"), "window": ("віконний", "оконный"),
    "chocolate": ("шоколадний", "шоколадный"), "wine": ("винний", "винный"), "ruby": ("рубіновий", "рубиновый"),
    "salmon": ("лососевий", "лососевый"), "lemon": ("лимонний", "лимонный"), "honey": ("медовий", "медовый"),
    "melon": ("динний", "дынный"), "maize": ("кукурудзяний", "кукурузный"), "broom": ("дроковий", "дроковый"),
    "night": ("нічний", "ночной"), "steel": ("сталевий", "стальной"), "cobalt": ("кобальтовий", "кобальтовый"),
    "capri": ("капрі", "капри"), "gentian": ("тирличевий", "генциановый"), "azure": ("лазурний", "лазурный"),
    "brilliant": ("яскравий", "яркий"), "reed": ("очеретяний", "тростниковый"), "fern": ("папоротевий", "папоротниковый"),
    "bottle": ("пляшковий", "бутылочный"), "fir": ("ялиновий", "еловый"), "grass": ("травʼяний", "травяной"),
    "mint": ("мʼятний", "мятный"), "emerald": ("смарагдовий", "изумрудный"), "opal": ("опаловий", "опаловый"),
    "papyrus": ("папірусний", "папирусный"), "clay": ("глиняний", "глиняный"), "mahogany": ("червоне дерево", "красное дерево"),
    "beaver": ("бобровий", "бобровый"), "sepia": ("сепія", "сепия"), "fawn": ("оленячий", "оленевый"),
    "terra": ("теракотовий", "терракотовый"), "nut": ("горіховий", "ореховый"),
}


def translate(name_en):
    uk, ru = [], []
    for w in (name_en or "").replace("-", " ").split():
        k = w.lower().strip(",.")
        pair = WORDS.get(k)
        uk.append(pair[0] if pair else w)
        ru.append(pair[1] if pair else w)
    return " ".join(uk), " ".join(ru)


class Command(BaseCommand):
    help = "Завантажити RAL Classic і NCS у довідник кольорів"

    def handle(self, *args, **opts):
        total = 0
        ral = json.load(open(os.path.join(DATA, "ral_classic.json")))
        for r in ral:
            lab = rgb_to_lab(hex_to_rgb(r["hex"]))
            uk, ru = translate(r.get("name_en"))
            ColorRef.objects.update_or_create(
                system="ral", code=r["code"],
                defaults=dict(name_uk=uk[:80], name_ru=ru[:80], name_en=(r.get("name_en") or "")[:80],
                              hex=r["hex"], lab_l=lab[0], lab_a=lab[1], lab_b=lab[2]))
            total += 1
        ncs = json.load(open(os.path.join(DATA, "ncs.json")))
        for r in ncs:
            ColorRef.objects.update_or_create(
                system="ncs", code=r["code"],
                defaults=dict(hex=r["hex"], lab_l=r["L"], lab_a=r["a"], lab_b=r["b"]))
            total += 1
        self.stdout.write("кольорів у довіднику: %d (RAL %d + NCS %d)"
                          % (ColorRef.objects.count(), ColorRef.objects.filter(system="ral").count(),
                             ColorRef.objects.filter(system="ncs").count()))
