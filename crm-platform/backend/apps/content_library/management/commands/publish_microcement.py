import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from apps.content_library.models import Instruction

class Command(BaseCommand):
    help = "Publish the reviewed single Microcement instruction; refuses to overwrite a changed version."
    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
    def handle(self, *args, **options):
        content = json.loads((Path(__file__).resolve().parents[2] / 'microcement.json').read_text())
        existing = Instruction.objects.filter(slug='microcement').first()
        if existing:
            if existing.content != content: raise CommandError('Existing content differs: review and version it before updating')
            self.stdout.write('Already published; unchanged'); return
        if not options['apply']:
            self.stdout.write('DRY_RUN: create one Microcement instruction linked to 1632/1633'); return
        i = Instruction.objects.create(slug='microcement',title='Microcement — повна технологічна карта',
            description='Підготовка, армування, ґрунти, шари Microcement, шліфування та захист. Покрокова інструкція Wallcov.',
            cover_url='https://wallcov.com.ua/media/crm-catalog/1632/55987574f9fca17dd86d2344d3f4c0334939582ab5aa2f8efe338b436c10437d.jpg',
            article_url='https://wallcov.com.ua/articles/microcement-shower',status='published',content=content)
        from apps.warehouse.models import Product
        i.products.set(Product.objects.filter(pk__in=[1632,1633],is_active=True))
        self.stdout.write(f'Published instruction {i.pk} version {i.version}')
