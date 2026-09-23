import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (Instruction, AudienceProfile, GuideRequest, InstructionShare,
                     InstructionEvent, ConsentEvent, LeadForm, KeywordAutomation,
                     KeywordAutomationRun)


def permitted(user, code):
    return user.is_authenticated and (user.is_superuser or user.has_perm_code(code))


def staff_training_access(user):
    return (user.is_authenticated and user.is_active
            and getattr(user, 'account_kind', None) == 'staff'
            and permitted(user, 'inbox.view'))


def localized_article_url(instruction, lang):
    candidate = instruction.article_url or ''
    try:
        parts = urlsplit(candidate)
        safe = (parts.scheme == 'https' and parts.netloc == 'wallcov.com.ua'
                and parts.path.startswith('/porady-ta-idei/'))
    except ValueError:
        safe = False
    parts = urlsplit(candidate if safe else instruction.public_url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != 'lang']
    if lang == 'ru':
        query.append(('lang', 'ru'))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def localized_sales_guide(content, lang):
    """Internal editorial fields only; no prices, product facts or arbitrary keys."""
    guides = content.get('sales_guide', {})
    raw = guides.get(lang) if isinstance(guides, dict) else None
    if not isinstance(raw, dict):
        return None
    def text(value, limit):
        return value.strip()[:limit] if isinstance(value, str) else ''
    sections = raw.get('sections', [])
    sections = sections if isinstance(sections, list) else []
    result = {'title': text(raw.get('title'), 160), 'intro': text(raw.get('intro'), 2000),
              'sections': [{'title': text(x.get('title'), 160), 'body': text(x.get('body'), 6000)}
                           for x in sections[:16] if isinstance(x, dict) and text(x.get('body'), 6000)]}
    return result if result['intro'] or result['sections'] else None


def reject_staff_instruction(instruction):
    if instruction.content.get('kind') == 'staff_training':
        raise Http404


def serialize(i,lang="uk"):
    reject_staff_instruction(i)
    from .client_materials import material_article
    article = material_article(i,lang)
    if article:
        return {'slug':i.slug,'title':article['title'],'description':article['intro'],'cover_url':article['cover_url'],
            'article_url':i.article_url,'public_url':i.public_url+('?lang=ru' if lang=='ru' else ''),'version':i.version,'status':i.status,
            'updated_at':article['updated_at'],'product_ids':[p.id for p in i.products.all()]}
    return {'slug':i.slug,'title':i.title,'description':i.description,'cover_url':i.cover_url,
            'article_url':i.article_url,'public_url':i.public_url,'version':i.version,
            'status':i.status,'updated_at':i.updated_at,'product_ids':[p.id for p in i.products.all()]}


class LibraryView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        if not permitted(request.user,'inbox.view'): return Response(status=403)
        if request.GET.get('calculator') == 'topciment':
            from .topciment import SYSTEMS, calculate
            try:
                data = calculate(request.GET.get('system', SYSTEMS[0]['id']), request.GET.get('area', '25'), request.GET.get('reserve', '10'), request.GET.get('basis', 'sale'))
            except (ValueError, ArithmeticError):
                return Response({'error': 'Перевірте систему, площу та запас (0–50%).'}, status=400)
            data['systems'] = [{'id':s['id'],'name':s['name']} for s in SYSTEMS]
            response = Response(data)
            response['Cache-Control'] = 'private, no-store'
            return response
        lang='ru' if request.GET.get('lang')=='ru' else 'uk'
        from .client_materials import product_texts
        from apps.warehouse.technical_facts import technical_data
        article_links = {}
        for article_instruction in Instruction.objects.filter(status='published', content__kind='client_material').prefetch_related('products'):
            primary_id = article_instruction.content.get('primary_product_id')
            if any(p.pk == primary_id and p.is_active for p in article_instruction.products.all()):
                article_links[primary_id] = localized_article_url(article_instruction, lang)
        training = []
        training_entries = Instruction.objects.filter(status='draft', content__kind='staff_training').prefetch_related('products__images').order_by('title') if staff_training_access(request.user) else []
        for i in training_entries:
            products = []
            for p in i.products.all():
                if not p.is_active:
                    continue
                localized=product_texts(p,lang)
                products.append({'id': p.id, 'name': localized['name'], 'price': str(p.price),
                    'currency': p.currency, 'unit': p.unit, 'description': localized['description'],
                    'technical': technical_data(p),
                    'short_description': localized['short_description'],
                    'full_description': localized['full_description'],
                    'benefits': p.shop_benefits, 'consumption': str(p.consumption_per_m2) if p.consumption_per_m2 else None,
                    'instruction_url': p.shop_instruction_url, 'video_url': p.shop_video_url,
                    'article_url': article_links.get(p.id, ''),
                    'updated_at': p.updated_at.isoformat(),
                    'images': [{'id': im.id, 'url': '/api/products/%d/image/%d/' % (p.id, im.id),
                        'alt_text': im.alt_text, 'is_primary': im.is_primary} for im in p.images.all()]})
            training.append({'id': i.id, 'sales_guide': localized_sales_guide(i.content, lang), 'date': i.updated_at.date().isoformat(),
                'title': (products[0]['name'] if lang=='ru' and products else i.title), 'products': products,
                'category': i.content.get('category', ''), 'section_key': i.content.get('section_key', 'materials_prep')})
        data={'items':[serialize(i,lang) for i in Instruction.objects.filter(status='published').exclude(content__kind='staff_training').prefetch_related('products__images')], 'training': training}
        import hashlib
        from django.core.serializers.json import DjangoJSONEncoder
        version=hashlib.sha256(json.dumps(data,cls=DjangoJSONEncoder,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        response = Response({'unchanged':True,'version':version} if request.GET.get('version')==version else {**data,'version':version})
        response['Cache-Control'] = 'private, no-store'
        return response


@ensure_csrf_cookie
def guide(request,slug):
    lang='ru' if request.GET.get('lang')=='ru' else 'uk'
    i=get_object_or_404(Instruction,slug=slug,status='published')
    reject_staff_instruction(i)
    if i.content.get('kind') == 'client_material':
        from .client_materials import material_article
        article = material_article(i,lang)
        if not article: return HttpResponse(status=404)
        response = render(request, 'content_library/material.html', {'article':article})
        response['Cache-Control'] = 'private, no-store'
        response['X-Robots-Tag'] = 'noindex, follow'
        return response
    # Stable public document. Tracking tokens never gate reading it.
    params={k:request.GET[k][:300] for k in ['r','s','utm_source','utm_medium','utm_campaign','utm_content'] if k in request.GET}
    receipt=GuideRequest.objects.filter(token=params.get('r',''),instruction=i).first()
    calculation_params={'article':'microcement-shower'}
    if receipt:
        calculation_params['r']=receipt.token
    response=render(request,'content_library/guide.html',{'instruction':i,'content':i.content,
      'version':i.version,'tracking':json.dumps(params),
      'calculation_url':'https://wallcov.com.ua/rozrakhunok?'+urlencode(calculation_params),
      'show_print':permitted(request.user,'inbox.view')})
    response['X-Robots-Tag']='noindex, follow'
    response['Referrer-Policy']='no-referrer'
    response['Cache-Control']='private, no-store'
    return response


@require_POST
def guide_contact(request):
    """Resolve an opaque guide receipt for the shop without exposing contact data in URLs."""
    timestamp=request.headers.get('X-Wallcov-Timestamp','')
    signature=request.headers.get('X-Wallcov-Signature','')
    secret=settings.SHOP_WEBHOOK_SECRET
    if (not secret or not timestamp.isdigit()
            or abs(int(time.time())-int(timestamp))>300):
        return JsonResponse({'detail':'Підпис недійсний'},status=403)
    expected=hmac.new(secret.encode(),timestamp.encode()+b'.'+request.body,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature):
        return JsonResponse({'detail':'Підпис недійсний'},status=403)
    try:
        data=json.loads(request.body)
        token=str(data.get('guide_token') or '')
        article=str(data.get('article') or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{40,64}',token): raise ValueError()
        receipt=(GuideRequest.objects.select_related('profile__contact','instruction')
                 .filter(token=token,instruction__slug='microcement').first())
        if not receipt or article not in ('','microcement-shower'):
            return JsonResponse({'found':False},status=404)
    except (ValueError,TypeError,json.JSONDecodeError):
        return JsonResponse({'found':False},status=404)
    contact=receipt.profile.contact
    display_name=(contact.first_name or str(contact) or 'Клієнт').strip()[:120]
    preferred=receipt.profile.preferred_channel or ('email' if contact.email and not contact.phone else 'phone')
    return JsonResponse({'found':True,'display_name':display_name,
                         'preferred_channel':preferred,'guide_token':receipt.token})


def resolve_tracking(i,params):
    receipt=GuideRequest.objects.filter(token=params.get('r',''),instruction=i).first()
    share=InstructionShare.objects.filter(token=params.get('s',''),instruction=i,message__isnull=False).first()
    profile=receipt.profile if receipt else None
    if not profile and share and share.contact_id:
        profile=AudienceProfile.objects.filter(contact_id=share.contact_id).first()
    return profile,share


@require_POST
def track(request,slug):
    i=get_object_or_404(Instruction,slug=slug,status='published')
    reject_staff_instruction(i)
    from django.core.cache import cache
    import hashlib
    key='guide-track:'+hashlib.sha256(request.META.get('REMOTE_ADDR','').encode()).hexdigest()
    cache.add(key,0,60)
    if cache.incr(key)>120: return JsonResponse({'ok':False},status=429)
    try:
        if len(request.body)>4096: return JsonResponse({'ok':False},status=413)
        data=json.loads(request.body)
        if not isinstance(data,dict): raise ValueError()
        name=data.get('event')
        if name not in ['instruction_open','calculation_click','product_click']: raise ValueError()
        event_id=uuid.UUID(str(data['event_id']))
        profile,share=resolve_tracking(i,data)
        InstructionEvent.objects.get_or_create(event_id=event_id,defaults={'instruction':i,'version':i.version,'name':name,'profile':profile,'share':share,'context':{'request_token':str(data.get('r',''))[:64]}})
    except (ValueError,KeyError,TypeError): return JsonResponse({'ok':False},status=400)
    return JsonResponse({'ok':True})



@require_POST
def unsubscribe(request,token):
    with transaction.atomic():
        p=get_object_or_404(AudienceProfile.objects.select_for_update(),unsubscribe_token=token)
        p.marketing_consent=False;p.status='unsubscribed';p.save()
        ConsentEvent.objects.create(profile=p,granted=False,source='unsubscribe')
    return JsonResponse({'ok':True})


class AudienceView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        if not permitted(request.user,'marketing.view'): return Response(status=403)
        req=GuideRequest.objects.all()
        if request.GET.get('instruction'):
            req=req.filter(instruction__slug=request.GET['instruction'][:200])
        if request.GET.get('source'):
            req=req.filter(context__source_platform=request.GET['source'][:200])
        if request.GET.get('campaign'):
            req=req.filter(context__utm_campaign__icontains=request.GET['campaign'][:200])
        if request.GET.get('content'):
            value=request.GET['content'][:200]
            req=req.filter(Q(context__source_content_id__icontains=value)|Q(context__utm_content__icontains=value))
        profiles=AudienceProfile.objects.filter(pk__in=req.values('profile_id')).distinct()
        total=profiles.count();now=timezone.now()
        kinds={kind:profiles.filter(identities__kind=kind).distinct().count() for kind in ['phone','email','viber','whatsapp','telegram','instagram']}
        reachable=profiles.exclude(status__in=['invalid','unsubscribed']).filter(identities__isnull=False).distinct().count()
        events=InstructionEvent.objects.filter(profile__in=profiles)
        if request.GET.get('instruction'): events=events.filter(instruction__slug=request.GET['instruction'])
        counts={r['name']:r['n'] for r in events.values('name').annotate(n=Count('profile_id',distinct=True))}
        # Payments cannot be attributed causally to a download. Report a defined cohort,
        # and exclude deals that predate that person's first content request.
        from apps.crm.models import Deal,Payment
        from django.db.models import F
        deals=Deal.objects.filter(contact_id__in=profiles.values('contact_id'),created_at__gte=F('contact__content_audience__first_touch_at'))
        customers=deals.filter(stage__is_won=True).values('contact_id').distinct().count()
        revenue=None
        if permitted(request.user,'marketing.money'):
            revenue=str(Payment.objects.filter(deal__in=deals,is_paid=True,checkbox_return_id='').aggregate(v=Sum('amount'))['v'] or 0)
        multi=profiles.annotate(n=Count('identities__kind',distinct=True)).filter(n__gte=2).count()
        anonymous=InstructionEvent.objects.filter(profile__isnull=True)
        if request.GET.get('instruction'): anonymous=anonymous.filter(instruction__slug=request.GET['instruction'])
        for query,key in [('source','context__source_platform'),('campaign','context__utm_campaign'),('content','context__source_content_id')]:
            if request.GET.get(query): anonymous=anonymous.filter(**{key:request.GET[query][:200]})
        anonymous_counts={r['name']:r['n'] for r in anonymous.values('name').annotate(n=Count('id'))}
        rows=[]
        if permitted(request.user,'contact.view'):
            for p in profiles.select_related('contact').prefetch_related('identities','requests__instruction').order_by('-last_touch_at')[:100]:
                identities=[{'kind':identity.kind,'value':identity.value,'verified':bool(identity.verified_at)}
                            for identity in p.identities.all()]
                rows.append({'id':p.contact_id,'name':str(p.contact),'phone':p.contact.phone,'email':p.contact.email,
                    'source':p.first_touch.get('source_platform',''),'campaign':p.first_touch.get('utm_campaign',''),
                    'content':p.first_touch.get('source_content_id') or p.first_touch.get('utm_content',''),
                    'preferred_channel':p.preferred_channel,'identities':identities,
                    'interests':sorted(set(p.tags or [])),
                    'instructions':sorted(set(request.instruction.title for request in p.requests.all())),
                    'consent':p.marketing_consent,'consent_at':p.consent_at,
                    'status':p.status,'last_touch_at':p.last_touch_at})
        shared=InstructionEvent.objects.filter(name='instruction_shared')
        if request.GET.get('instruction'): shared=shared.filter(instruction__slug=request.GET['instruction'])
        return Response({'total':total,'contactable':reachable,'contact_verification':'Контакти вказані клієнтом; доставка підтверджується після першого повідомлення або відповіді',
          'channels':kinds,'multichannel':multi,'marketing_consent':profiles.filter(marketing_consent=True).exclude(status__in=['unsubscribed','invalid']).count(),
          'no_contact':profiles.filter(identities__isnull=True).count(),'no_consent':profiles.filter(marketing_consent=False).count(),
          'unsubscribed':profiles.filter(status='unsubscribed').count(),'invalid':profiles.filter(status='invalid').count(),
          'new_today':profiles.filter(first_touch_at__date=timezone.localdate()).count(),
          'new_7d':profiles.filter(first_touch_at__gte=now-timedelta(days=7)).count(),
          'new_30d':profiles.filter(first_touch_at__gte=now-timedelta(days=30)).count(),
          'events':counts,'anonymous_events':anonymous_counts,'contacts':rows,'manager_shares':shared.count(),'manager_opened':InstructionEvent.objects.filter(name='instruction_open',share__in=shared.values('share_id')).values('share_id').distinct().count(),'customers':customers,'orders':deals.filter(stage__is_won=True).count(),
          'repeat_customers':deals.filter(stage__is_won=True).values('contact_id').annotate(n=Count('id')).filter(n__gte=2).count(),
          'paid_amount':revenue,'attribution_note':'Оплати за угодами, створеними після першого контент-запиту. Не доводить вплив гайда; платежі з позначкою повернення виключені.',
          'external_events_available':False,
          'sources':list(req.values('context__source_platform').annotate(contacts=Count('profile_id',distinct=True))),
          'instructions':list(req.values('instruction__slug').annotate(contacts=Count('profile_id',distinct=True)))})


def public_instruction(request,slug):
    lang='ru' if request.GET.get('lang')=='ru' else 'uk'
    if slug == 'material-index':
        entries=Instruction.objects.filter(status='published',content__kind='client_material').prefetch_related('products__images')
        response=JsonResponse({'items':[serialize(i,lang) for i in entries]})
        response['Cache-Control']='no-store'
        return response
    i=get_object_or_404(Instruction,slug=slug,status='published')
    reject_staff_instruction(i)
    data=serialize(i,lang)
    from .client_materials import material_article
    article=material_article(i,lang)
    if article:data['article']=article
    data['steps']=[{'title':s['title']} for s in i.content.get('steps',[])]
    response=JsonResponse(data)
    response['Cache-Control']='no-store'
    return response


def serialize_form(form):
    return {
        'id': form.id, 'slug': form.slug, 'name': form.name, 'title': form.title,
        'intro': form.intro, 'instruction_id': form.instruction_id,
        'instruction_slug': form.instruction.slug, 'fields': form.fields,
        'channels': form.channels, 'consent_text': form.consent_text,
        'submit_text': form.submit_text, 'enabled': form.enabled,
        'updated_at': form.updated_at,
    }


def serialize_keyword_automation(rule):
    return {
        'id': rule.id, 'title': rule.title, 'keywords': rule.keywords,
        'match_mode': rule.match_mode, 'platforms': rule.platforms,
        'form_id': rule.form_id, 'reply_text': rule.reply_text,
        'public_replies': rule.public_replies, 'direct_enabled': rule.direct_enabled,
        'comment_enabled': rule.comment_enabled, 'enabled': rule.enabled,
        'chatplace_bot_id': rule.chatplace_bot_id,
        'chatplace_automation_id': rule.chatplace_automation_id,
        'chatplace_status': rule.chatplace_status,
        'chatplace_error': rule.chatplace_error,
        'synced_at': rule.synced_at, 'last_triggered_at': rule.last_triggered_at,
    }


def public_form(request, slug):
    form = get_object_or_404(LeadForm.objects.select_related('instruction'), slug=slug,
                             enabled=True, instruction__status='published')
    reject_staff_instruction(form.instruction)
    response = JsonResponse(serialize_form(form))
    response['Cache-Control'] = 'public, max-age=60'
    return response


class ContentAutomationView(APIView):
    permission_classes = [IsAuthenticated]

    def _allowed(self, request):
        return permitted(request.user, 'settings.automations') or permitted(request.user, 'roles.manage')

    def get(self, request):
        if not self._allowed(request):
            return Response(status=403)
        forms = LeadForm.objects.select_related('instruction').all()
        rules = KeywordAutomation.objects.select_related('form__instruction').all()
        return Response({
            'forms': [serialize_form(x) for x in forms],
            'automations': [serialize_keyword_automation(x) for x in rules],
            'instructions': list(Instruction.objects.filter(status='published').values('id', 'slug', 'title')),
            'recent': {
                'captured_30d': KeywordAutomationRun.objects.filter(
                    status='captured', created_at__gte=timezone.now()-timedelta(days=30)).count(),
                'failed_30d': KeywordAutomationRun.objects.filter(
                    status='failed', created_at__gte=timezone.now()-timedelta(days=30)).count(),
            },
        })

    def post(self, request):
        if not self._allowed(request):
            return Response(status=403)
        action = str(request.data.get('action') or '')
        try:
            if action == 'save_form':
                return self._save_form(request)
            if action == 'save_automation':
                return self._save_automation(request)
            if action == 'sync_automation':
                rule = get_object_or_404(KeywordAutomation.objects.select_related('form__instruction'),
                                         pk=request.data.get('id'))
                if not rule.enabled:
                    return Response({'detail': 'Спочатку увімкніть правило'}, status=400)
                from .chatplace_automation import sync_to_chatplace
                result = sync_to_chatplace(rule)
                rule.refresh_from_db()
                return Response({'automation': serialize_keyword_automation(rule), 'result': result})
            if action == 'pause_automation':
                rule = get_object_or_404(KeywordAutomation, pk=request.data.get('id'))
                from .chatplace_automation import pause_in_chatplace
                pause_in_chatplace(rule)
                rule.enabled = False
                rule.updated_by = request.user
                rule.save(update_fields=['enabled', 'updated_by', 'updated_at'])
                return Response({'automation': serialize_keyword_automation(rule)})
        except (ValueError, TypeError) as exc:
            return Response({'detail': str(exc)}, status=400)
        except Exception as exc:
            rule = locals().get('rule')
            if rule:
                rule.chatplace_error = str(exc)[:500]
                rule.save(update_fields=['chatplace_error', 'updated_at'])
            return Response({'detail': str(exc)}, status=502)
        return Response({'detail': 'Невідома дія'}, status=400)

    def _save_form(self, request):
        data = request.data
        instruction = get_object_or_404(Instruction, pk=data.get('instruction_id'), status='published')
        slug = str(data.get('slug') or '').strip().lower()
        if not slug or not re.match(r'^[a-z0-9-]+$', slug):
            raise ValueError('Slug: лише латинські літери, цифри та дефіс')
        fields = [x for x in data.get('fields', []) if x in ('name', 'phone', 'email')]
        channels = [x for x in data.get('channels', []) if x in ('viber', 'whatsapp', 'telegram', 'email')]
        if 'name' not in fields or not ({'phone', 'email'} & set(fields)):
            raise ValueError('Форма має містити ім’я і хоча б телефон або email')
        if not channels:
            raise ValueError('Оберіть хоча б один канал')
        if 'email' in channels and 'email' not in fields:
            raise ValueError('Для каналу Email увімкніть поле Email')
        if ({'viber', 'whatsapp', 'telegram'} & set(channels)) and 'phone' not in fields:
            raise ValueError('Для месенджерів увімкніть поле Телефон')
        form = LeadForm.objects.filter(pk=data.get('id')).first() if data.get('id') else LeadForm()
        form.slug = slug
        form.name = str(data.get('name') or '').strip()[:160]
        form.title = str(data.get('title') or '').strip()[:240]
        form.intro = str(data.get('intro') or '').strip()
        form.instruction = instruction
        form.fields = fields
        form.channels = channels
        form.consent_text = str(data.get('consent_text') or '').strip()[:300]
        form.submit_text = str(data.get('submit_text') or '').strip()[:120]
        form.enabled = bool(data.get('enabled', True))
        form.updated_by = request.user
        if not form.name or not form.title or not form.submit_text:
            raise ValueError('Заповніть назву, заголовок і текст кнопки')
        form.save()
        return Response({'form': serialize_form(form)})

    def _save_automation(self, request):
        data = request.data
        form = get_object_or_404(LeadForm, pk=data.get('form_id'))
        rule = KeywordAutomation.objects.filter(pk=data.get('id')).first() if data.get('id') else KeywordAutomation()
        keywords = [str(x).strip()[:120] for x in data.get('keywords', []) if str(x).strip()]
        public_replies = [str(x).strip()[:300] for x in data.get('public_replies', []) if str(x).strip()]
        if not keywords:
            raise ValueError('Додайте кодове слово')
        rule.title = str(data.get('title') or '').strip()[:180]
        rule.keywords = keywords
        rule.match_mode = data.get('match_mode') if data.get('match_mode') in ('exact', 'contains') else 'exact'
        rule.platforms = ['instagram']
        rule.form = form
        rule.reply_text = str(data.get('reply_text') or '').strip()
        rule.public_replies = public_replies
        rule.direct_enabled = bool(data.get('direct_enabled', True))
        rule.comment_enabled = bool(data.get('comment_enabled', True))
        rule.enabled = bool(data.get('enabled', False))
        rule.updated_by = request.user
        if not rule.title or not rule.reply_text:
            raise ValueError('Заповніть назву і повідомлення в Direct')
        if not rule.direct_enabled and not rule.comment_enabled:
            raise ValueError('Увімкніть Direct або коментарі')
        if rule.comment_enabled and not public_replies:
            raise ValueError('Додайте публічну відповідь під коментарем')
        rule.save()
        return Response({'automation': serialize_keyword_automation(rule)})
