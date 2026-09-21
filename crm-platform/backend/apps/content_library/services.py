"""Content requests enrich the existing CRM contact, never create a second CRM."""
import hashlib
import json
import re
import uuid
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from apps.crm.models import Contact
from .models import AudienceProfile, AudienceIdentity, ConsentEvent, GuideRequest, Instruction, InstructionEvent


class IdentityConflict(ValueError):
    pass


PREFERRED_CHANNELS = {'viber', 'whatsapp', 'telegram', 'instagram', 'email'}


def normalize_phone(value):
    raw = str(value or '').strip()
    if not raw:
        return ''
    if not re.fullmatch(r'[+\d\s().-]+', raw):
        raise ValueError('Перевірте номер телефону')
    digits = re.sub(r'\D', '', raw)
    if len(digits)==10 and digits.startswith('0'):
        digits = '38' + digits
    if not 10 <= len(digits) <= 15 or digits.startswith('0'):
        raise ValueError('Перевірте номер телефону, наприклад +380670000000')
    return '+' + digits


def normalize_email(value):
    email = str(value or '').strip().lower()
    if email:
        try: validate_email(email)
        except ValidationError: raise ValueError('Перевірте email')
    return email


def lock(key):
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [int(hashlib.sha256(key.encode()).hexdigest()[:15],16)])


@transaction.atomic
def receive_guide(body):
    slug = str(body.get('lead_magnet_slug',''))
    instruction = Instruction.objects.filter(slug=slug,status='published').first()
    if not instruction: raise ValueError('Інструкцію не знайдено')
    name = str(body.get('name') or '').strip()
    if not name or len(name)>120: raise ValueError('Вкажіть ім’я, до 120 символів')
    phone, email = normalize_phone(body.get('phone')), normalize_email(body.get('email'))
    if not phone and not email: raise ValueError('Вкажіть телефон або email')
    preferred = str(body.get('preferred_channel') or '').strip().lower()
    if not preferred:
        # Backwards compatibility for requests created before the channel chooser.
        preferred = 'email' if email and not phone else 'viber'
    if preferred not in PREFERRED_CHANNELS:
        raise ValueError('Оберіть зручний канал зв’язку')
    if preferred == 'email' and not email:
        raise ValueError('Для зв’язку через email вкажіть email')
    if preferred != 'email' and not phone:
        raise ValueError('Для зв’язку через месенджер вкажіть телефон')
    consent=body.get('marketing_consent',False)
    if type(consent) is not bool: raise ValueError('Некоректна згода')
    submission=str(body.get('submission_id') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}',submission): raise ValueError('Некоректний номер запиту')
    # Only bounded, non-personal attribution. Never accept caller supplied CRM IDs.
    context={k:str(body.get(k) or '')[:500] for k in ['source_platform','source_content_id','source_url','utm_source','utm_medium','utm_campaign','utm_content']}
    for touch in ['first_touch','last_touch']:
        context[touch]={k:str(v)[:300] for k,v in (body.get(touch) if isinstance(body.get(touch),dict) else {}).items() if k in ['utm_source','utm_medium','utm_campaign','utm_content','landing_path','path']}
    visitor=str(body.get('visitor_id') or '')
    if re.fullmatch(r'[a-f0-9]{64}',visitor): context['visitor_id']=visitor
    request_token=str(body.get('guide_token') or '')
    if not re.fullmatch(r'[a-f0-9]{64}',request_token): raise ValueError('Некоректний ключ запиту')
    canonical={'name':name,'phone':phone,'email':email,'preferred_channel':preferred,
               'consent':consent,'slug':slug,'context':context}
    digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    lock('guide-request:'+submission)
    receipt=GuideRequest.objects.filter(submission_id=submission).first()
    if receipt:
        if receipt.payload_hash!=digest: raise IdentityConflict('Цей номер запиту вже використано з іншими даними')
        return receipt, True
    identities=[(k,v) for k,v in [('phone',phone),('email',email)] if v]
    for kind,value in sorted(identities): lock('guide-identity:'+kind+':'+value)
    contact_ids=set(AudienceIdentity.objects.filter(Q(kind='phone',value=phone) if not email else (Q(kind='phone',value=phone)|Q(kind='email',value=email))).values_list('profile__contact_id',flat=True))
    if email: contact_ids.update(Contact.objects.filter(email__iexact=email).values_list('pk',flat=True))
    if phone:
        # Match legacy formatting through the established phone equivalences.
        from apps.inbox.services import _phone_variants
        contact_ids.update(Contact.objects.filter(phone__in=_phone_variants(phone)).values_list('pk',flat=True))
    if len(contact_ids)>1: raise IdentityConflict('Телефон та email пов’язані з різними картками. Потрібна перевірка менеджера.')
    contact=Contact.objects.select_for_update().get(pk=contact_ids.pop()) if contact_ids else Contact.objects.create(first_name=name,phone=phone,email=email,source='site',kinds=['client'])
    # Enrich empty contact fields only; never overwrite an established identity.
    changed=[]
    for field,value in [('phone',phone),('email',email)]:
        if value and not getattr(contact,field): setattr(contact,field,value);changed.append(field)
    if changed: contact.save(update_fields=changed)
    # Do not overwrite existing identity data, portal account, name or permissions.
    profile,created=AudienceProfile.objects.get_or_create(contact=contact,defaults={'first_touch':context})
    profile.last_touch=context
    profile.preferred_channel=preferred
    profile.tags=sorted(set(profile.tags+['microcement_lead' if slug=='microcement' else slug+'_lead']))
    if consent:
        profile.marketing_consent=True;profile.consent_at=timezone.now()
        profile.status='subscribed'
    profile.save()
    for kind,value in identities: AudienceIdentity.objects.get_or_create(kind=kind,value=value,defaults={'profile':profile})
    # The chosen messenger is an addressable preference, but stays unverified until
    # a delivery/incoming reply proves that this number is available in the channel.
    if phone and preferred in {'viber','whatsapp','telegram'}:
        AudienceIdentity.objects.get_or_create(kind=preferred,value=phone,defaults={'profile':profile})
    if consent or created:
        ConsentEvent.objects.create(profile=profile,granted=consent,source='website:'+slug+':'+preferred)
    receipt=GuideRequest.objects.create(submission_id=submission,payload_hash=digest,instruction=instruction,profile=profile,context=context,token=request_token)
    InstructionEvent.objects.create(instruction=instruction,version=instruction.version,profile=profile,name='lead_created' if created else 'guide_requested',context=context)
    if visitor:
        InstructionEvent.objects.filter(instruction=instruction,profile__isnull=True,context__visitor_id=visitor,created_at__gte=timezone.now()-__import__('datetime').timedelta(days=2)).update(profile=profile)
    InstructionEvent.objects.filter(instruction=instruction,profile__isnull=True,context__request_token=request_token).update(profile=profile)
    return receipt,False


def prepare_share(instruction_slug,conversation,user):
    from .models import InstructionShare
    instruction=Instruction.objects.get(slug=instruction_slug,status='published')
    share=InstructionShare.objects.create(instruction=instruction,conversation=conversation,manager=user,contact=conversation.contact)
    text=f'{instruction.title} 👇\n{instruction.description}\n\n{instruction.public_url}?s={share.token}'
    return share,text


def record_shared(message,conversation,user):
    """The existing send path is the only sender; draft insertion is not a send."""
    from .models import InstructionShare
    if not message: return
    if message.internal or message.status not in ['sent','delivered','read']: return
    tokens=re.findall(r'https://wallcov\.com\.ua/instructions/[a-z0-9-]+\?s=([A-Za-z0-9_-]{40,64})',message.text)
    for value in tokens:
        with transaction.atomic():
            share=InstructionShare.objects.select_for_update().filter(token=value,conversation=conversation,manager=user).first()
            if share and share.message_id is None:
                share.message=message;share.save(update_fields=['message'])
                profile=None
                if share.contact_id:
                    context={'source_platform':'manager','manager_id':user.pk}
                    profile,_=AudienceProfile.objects.get_or_create(contact_id=share.contact_id,defaults={'first_touch':context,'last_touch':context})
                    GuideRequest.objects.get_or_create(submission_id='manager-share-'+str(share.pk),defaults={'payload_hash':'manager-share','instruction':share.instruction,'profile':profile,'context':context})
                InstructionEvent.objects.create(instruction=share.instruction,version=share.instruction.version,share=share,
                    profile=profile,name='instruction_shared')


EVENTS = {'article_view','article_scroll_50','article_scroll_90','lead_cta_view','lead_cta_click','web_option_click','lead_form_start','lead_form_submit','instruction_open','calculation_click','product_click','product_view','calculation_request'}

@transaction.atomic
def receive_event(body):
    i = Instruction.objects.get(slug=body.get('lead_magnet_slug'), status='published')
    name = body.get('event')
    if name not in EVENTS: raise ValueError('Невідома подія')
    event_id = uuid.UUID(str(body.get('event_id')))
    visitor = str(body.get('visitor_id') or '')
    if not re.fullmatch(r'[a-f0-9]{64}', visitor): raise ValueError('Некоректний відвідувач')
    profile = AudienceProfile.objects.filter(requests__context__visitor_id=visitor).order_by('-last_touch_at').first()
    context = {k:str(body.get(k) or '')[:300] for k in ['visitor_id','source_platform','source_content_id','utm_source','utm_medium','utm_campaign','utm_content']}
    event, created = InstructionEvent.objects.get_or_create(event_id=event_id,defaults={'instruction':i,'version':i.version,'name':name,'profile':profile,'context':context})
    return event, not created
