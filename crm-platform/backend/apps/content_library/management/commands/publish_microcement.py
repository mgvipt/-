import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.content_library.models import Instruction

class Command(BaseCommand):
    help = "Publish or version the reviewed Microcement instruction."
    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
    def handle(self, *args, **options):
        content = json.loads((Path(__file__).resolve().parents[2] / 'microcement.json').read_text())
        title = 'Microcement — повна технологічна карта'
        description = 'Ґрунти, сітка 2×2 мм, шари Microcement, шліфування та захист. Покрокова інструкція Wallcov.'
        cover_url = 'https://wallcov.com.ua/media/crm-catalog/1632/55987574f9fca17dd86d2344d3f4c0334939582ab5aa2f8efe338b436c10437d.jpg'
        article_url = 'https://wallcov.com.ua/articles/microcement-shower'
        existing = Instruction.objects.filter(slug='microcement').first()
        if existing and existing.content == content:
            self.stdout.write('Already published; unchanged'); return
        action = f'update instruction {existing.pk} from version {existing.version} to {existing.version + 1}' if existing else 'create one Microcement instruction linked to 1632/1633'
        if not options['apply']:
            self.stdout.write(f'DRY_RUN: {action}'); return
        with transaction.atomic():
            i = Instruction.objects.select_for_update().filter(slug='microcement').first()
            if i:
                if i.content == content:
                    self.stdout.write('Already published; unchanged'); return
                i.title = title
                i.description = description
                i.cover_url = cover_url
                i.article_url = article_url
                i.status = 'published'
                i.content = content
                i.version += 1
                i.save()
            else:
                i = Instruction.objects.create(slug='microcement', title=title, description=description,
                    cover_url=cover_url, article_url=article_url, status='published', content=content)
            from apps.warehouse.models import Product
            i.products.set(Product.objects.filter(pk__in=[1632,1633],is_active=True))
        self.stdout.write(f'Published instruction {i.pk} version {i.version}')
