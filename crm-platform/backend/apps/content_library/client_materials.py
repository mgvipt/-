"""Public editorial view of a canonical Product; no article-body or image copies."""
from django.utils.html import escape

def product_texts(product,lang='uk'):
 data={'name':product.name,'description':product.description,'short_description':product.shop_short_description,'full_description':product.shop_full_description}
 translated=product.shop_specs.get('translations',{}).get(lang,{}) if lang=='ru' else {}
 if translated:
  data.update({k:v for k,v in translated.items() if k in data and isinstance(v,str)})
 data['language_available']=lang!='ru' or bool(translated)
 return data

def material_article(instruction,lang='uk'):
 if instruction.content.get('kind')!='client_material':return None
 linked=list(instruction.products.all())
 p=next((item for item in linked if item.pk==instruction.content.get('primary_product_id') and item.is_active),None)
 if not p:return None
 localized=product_texts(p,lang)
 text=localized['full_description'].strip()
 if not text:return None
 images=[im for im in p.images.all() if im.is_approved];images.sort(key=lambda im:(not im.is_primary,im.order,im.id))
 cover=('https://crm.wallcovdec.com.ua/api/products/%d/image/%d/'%(p.id,images[0].id)) if images else ''
 title=(p.shop_specs.get('translations',{}).get('ru',{}).get('article_title') if lang=='ru' else None) or p.seo_h1 or instruction.title
 paragraphs=text.split('\n\n')
 sections=[]
 for para in paragraphs:
  if '\n' in para:
   heading,body=para.split('\n',1);sections.append({'title':heading,'text':body})
  else:sections.append({'title':'','text':para})
 body=''.join(('<h2>'+str(escape(s['title']))+'</h2>' if s['title'] else '')+'<p>'+str(escape(s['text'])).replace('\n','<br>')+'</p>' for s in sections)
 return {'title':title,'intro':localized['short_description'],'sections':sections,'body_html':body,'cover_url':cover,'updated_at':p.updated_at.isoformat(),'product_id':p.id,'products':[{'id':q.id,'name':q.name,'url':q.shop_remote_url} for q in linked if q.is_active and q.shop_remote_url.startswith('https://wallcov.com.ua/')],'technical_url':p.shop_instruction_url,'lang':lang,'language_available':localized['language_available']}
