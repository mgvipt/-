import json
import uuid
from datetime import timedelta
from urllib.parse import urlencode
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Instruction, AudienceProfile, GuideRequest, InstructionShare, InstructionEvent, ConsentEvent


def permitted(user, code):
    return user.is_authenticated and (user.is_superuser or user.has_perm_code(code))


def serialize(i):
    return {'slug':i.slug,'title':i.title,'description':i.description,'cover_url':i.cover_url,
            'article_url':i.article_url,'public_url':i.public_url,'version':i.version,
            'status':i.status,'updated_at':i.updated_at,'product_ids':list(i.products.values_list('id',flat=True))}


class LibraryView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        if not permitted(request.user,'inbox.view'): return Response(status=403)
        return Response({'items':[serialize(i) for i in Instruction.objects.filter(status='published').prefetch_related('products')]})


@ensure_csrf_cookie
def guide(request,slug):
    i=get_object_or_404(Instruction,slug=slug,status='published')
    # Stable public document. Tracking tokens never gate reading it.
    params={k:request.GET[k][:300] for k in ['r','s','utm_source','utm_medium','utm_campaign','utm_content'] if k in request.GET}
    response=render(request,'content_library/guide.html',{'instruction':i,'content':i.content,
      'version':i.version,'tracking':json.dumps(params)})
    response['X-Robots-Tag']='noindex, follow'
    response['Referrer-Policy']='strict-origin-when-cross-origin'
    response['Cache-Control']='private, no-store'
    return response


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
    i=get_object_or_404(Instruction,slug=slug,status='published')
    data=serialize(i)
    data['steps']=[{'title':s['title']} for s in i.content.get('steps',[])]
    return JsonResponse(data)
