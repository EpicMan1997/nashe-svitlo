#!/usr/bin/env python3
"""Conservative date-scoped power-outage schedule for Vyshcha Dubechnya group 3.1."""
import json
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from season import update_season

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'state' / 'state.json'
OUTPUT = ROOT / 'site' / 'data.json'
KYIV = ZoneInfo('Europe/Kyiv')
BEZ = 'https://bezsvitla.com.ua/kyivska-oblast/pirnivska-hromada/visa-dubecna/grafik-na-'
BEZ_REGION = 'https://bezsvitla.com.ua/kyivska-oblast/grafik-na-'
MAP_REGION = 'https://mapasvitla.com.ua/kyivska-oblast/dtek-krem/3.1'
MAP_CITY_PREFIX = 'https://mapasvitla.com.ua/kyiv/dtek-kem/'
KOLY = 'https://kolysvitlo.com/schedule/dtek_kyiv_oblast'
KOLBUDE = 'https://kolybude.com/kyiv-oblast'
DTEK = 'https://www.dtek-krem.com.ua/ua/shutdowns'
ALERTS_REGION = 'https://alerts.energy/kyivska-oblast'
ALERTS_CITY = 'https://alerts.energy/kyiv'
KYIVSHCHYNA = 'https://kyivshchyna.info/hrafik-vidkliuchen-svitla-kyivska-oblast/'
SVITLOLIVE = 'https://svitlo.live/selo-vischa-dubechnya'
SVITLOLIVE_FALLBACK = 'https://svitlo.live/pirnivska-gromada'
MONTHS = ['', 'січня', 'лютого', 'березня', 'квітня', 'травня', 'червня',
          'липня', 'серпня', 'вересня', 'жовтня', 'листопада', 'грудня']
PAIR = re.compile(r'(?<!\d)([01]\d|2[0-4]):([0-5]\d)\s*[–—-]\s*([01]\d|2[0-4]):([0-5]\d)(?!\d)')

def minutes(s):
    h, m = map(int, s.split(':'))
    if h > 24 or (h == 24 and m): raise ValueError('invalid time')
    return h * 60 + m

def pairs(s):
    output = []
    for a, b, c, d in PAIR.findall(s):
        start, end = a+':'+b, c+':'+d
        if minutes(start) < minutes(end): output.append([start, end])
    return output

def normalize(ranges):
    merged = []
    for a, b in sorted((minutes(a), minutes(b)) for a,b in ranges):
        if not 0 <= a < b <= 1440: raise ValueError('bad time range')
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(b, merged[-1][1])
        else:
            merged.append([a,b])
    return tuple((f'{a//60:02d}:{a%60:02d}', f'{b//60:02d}:{b%60:02d}') for a,b in merged)

def plain(html):
    soup = BeautifulSoup(html, 'html.parser')
    for x in soup(['script', 'style', 'noscript']): x.decompose()
    return re.sub(r'\s+', ' ', soup.get_text(' ',strip=True))

def parse_bez(html, target):
    s = plain(html)
    label = target.strftime('%d.%m.%Y')
    if label not in s[:1100]: return {'candidates':[], 'updated':'', 'unpublished':False}
    if re.search(r'на\s*'+re.escape(label)+r'\s+ще\s+не\s+опублікован', s[:1100], re.I):
        return {'candidates':[], 'updated':'', 'unpublished':True}
    match = re.search(r'Графік\s+Черга\s+3\.1\b(.*?)(?:Зберегти підчергу|Історія змін|Графік\s+Черга\s+\d+\.\d+)', s, re.I|re.S)
    if not match: return {'candidates':[], 'updated':'', 'unpublished':False}
    blocks = pairs(match.group(1))
    if not blocks or blocks[0][0]!='00:00' or blocks[-1][1]!='24:00' or any(blocks[i][1]!=blocks[i+1][0] for i in range(len(blocks)-1)):
        return {'candidates':[], 'updated':'', 'unpublished':False}
    options = list(dict.fromkeys([normalize(blocks[::2]), normalize(blocks[1::2])]))
    after = s[match.end():match.end()+120]
    history = re.search(r'Історія змін\s*(\d{2}\.\d{2}\.\d{4}\s+\d\d:\d\d)', after)
    page_date = re.search(r'Оновлено:\s*(\d{2}\.\d{2}\.\d{4}\s+\d\d:\d\d)', s[:500])
    return {'candidates':options, 'updated': history.group(1) if history else page_date.group(1) if page_date else '', 'unpublished':False}


def parse_mapasvitla(html, target, today, group):
    """Parse one operator-specific, day-scoped queue page (not the mixed-region grid).
    Reject the wrong group/date, placeholders, and ambiguous intervals.
    """
    empty={'candidates':[],'updated':'','unpublished':False}
    if not html: return empty
    soup=BeautifulSoup(html,'html.parser')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    if not re.search(r'Черга\s*'+re.escape(group)+r'(?!\d)',title):
        return empty
    scope='today' if target==today else 'tomorrow' if target==today+timedelta(days=1) else None
    if not scope:return empty
    section=soup.select_one('[data-day="'+scope+'"]')
    if section is None:return empty
    s=section.get_text(' ',strip=True)
    if re.search(r'Очікуємо графік|ще не опублікован',s,re.I):
        return {**empty,'unpublished':True}
    day=re.search(r'План на\s+(?:сьогодні|завтра)[^0-9]{0,40}(\d{1,2})\.(\d{2})(?!\d)',s[:180],re.I)
    if not day or int(day.group(1))!=target.day or int(day.group(2))!=target.month:return empty
    # The outage list is before the total. Do not read periods from history or explanations.
    if 'Всього без світла' not in s:return empty
    before=s.split('Всього без світла',1)[0]
    intervals=pairs(before)
    if not intervals:
        if re.search(r'Всього без світла\s*(?:0(?:[,.]0)?\s*год|0\s*хв)',s,re.I) or re.search(r'Без відключень|Світло весь день',s,re.I):
            choices=[tuple()]
        else:return empty
    else:
        # A valid summary is necessary to guard against fragments from other widgets.
        choices=[normalize(intervals)]
    return {'candidates':choices,'updated':'','unpublished':False}

def scoped(html, target, today):
    s = plain(html)
    label = f'{target.day} {MONTHS[target.month]}'
    if target == today:
        m = re.search(r'(?:Сьогодні|на сьогодні)[,\s]+(\d{1,2}\s+\w+)(?:\s+(\d{4}))?', s, re.I)
        if not m or m.group(1).lower()!=label or (m.group(2) and int(m.group(2))!=target.year): return None
        tail = s[m.end():]
        end = re.search(r'(?:Завтра[,\s]+\d{1,2}\s+[А-Яа-яІіЇїЄєҐґ]{3,}|Графік на завтра)', tail, re.I)
        return tail[:end.start()] if end else tail
    m = re.search(r'(?:Завтра[,\s]+|на завтра[,\s]+)'+re.escape(f'{label} {target.year}'),s,re.I)
    if not m: return None
    tail = s[m.end():]
    end = re.search(r'(?:Сьогодні[,\s]+\d|Про графік|Часті запитання)',tail,re.I)
    return tail[:end.start()] if end else tail

def parse_kolysvitlo(html, target, today):
    text = scoped(html,target,today)
    if not text: return None
    row = re.search(r'(?<!\d)3\.1\b(.*?)(?<!\d)3\.2\b', text, re.S)
    if not row: return None
    if re.search(r'Без відключень|Відключень немає',row.group(1),re.I): return tuple()
    off = re.search(r'Немає світла:\s*(.*)', row.group(1), re.I)
    if not off: return None
    ranges = pairs(off.group(1))
    return normalize(ranges) if ranges else None

def parse_kolybude(html,target,today):
    text=scoped(html,target,today)
    if not text: return None
    row=re.search(r'Черга\s*3\.1\b\s*:?\s*(.*?)(?:Черга\s*3\.2|Черга\s*4\.1|$)',text,re.I|re.S)
    if not row: return None
    if re.search(r'Без відключень|Відключень немає',row.group(1),re.I): return tuple()
    ranges=pairs(row.group(1))
    return normalize(ranges) if ranges else None


def parse_kyivshchyna(html, target, today):
    """Only a date-verified queue 3.1 block. Do not infer tomorrow's rows."""
    if target != today:
        return None
    page = plain(html)
    # The site publishes the latest DTEK update and a local check timestamp.
    # A previous-day source check is not sufficient evidence for today's graph.
    if target.strftime('%d.%m.%Y') not in page and f'{target.day} {MONTHS[target.month]} {target.year}' not in page:
        return None
    row = re.search(r'Черга\s*3\.1\b(.*?)(?:Черга\s*3\.2\b|Черга\s*4\.1\b)',page,re.I|re.S)
    if not row:
        return None
    cell = row.group(1)
    if re.search(r'без відключень|відключень немає',cell,re.I):
        return tuple()
    off = re.search(r'без світла:\s*(.*)',cell,re.I)
    if not off: return None
    ranges = pairs(off.group(1))
    return normalize(ranges) if ranges else None

def parse_svitlolive(html, target, today):
    """An hour-resolution reading only; half-hour cells are *not* guessed."""
    page = plain(html)
    heading = 'сьогодні' if target == today else 'завтра'
    row = re.search(
        r'Графік на '+heading+r'\s*[-–]\s*черга\s*3\.1\s*(.*?)'
        r'(?=Графік на (?:сьогодні|завтра)\s*[-–]\s*черга\s*\d+\.\d+|Усі населені пункти|$)',
        page,re.I|re.S)
    if not row or target.strftime('%d.%m.%Y') not in row.group(1)[:110]:
        return None
    marks = re.search(r'Черга\s*3\.1\s*((?:[●✕×%±\-]\s*){24})',row.group(1))
    if not marks: return None
    cells = re.findall(r'[●✕×%±\-]',marks.group(1))
    if len(cells)!=24 or all(x=='-' for x in cells):return None
    if any(x not in {'●','✕','×','%','±','-'} for x in cells):return None
    ranges = [(f'{i:02d}:00',f'{i+1:02d}:00') for i,c in enumerate(cells) if c in ('✕','×')]
    partial = [f'{i:02d}:00–{i+1:02d}:00' for i,c in enumerate(cells) if c in ('%','±')]
    if '-' in cells: return None
    return {'outages':normalize(ranges),'partial':partial,'hourly':True}


def parse_alerts(html, target, group, operator):
    """Read only Angular SSR transfer-state rows for the exact DTEK queue and date.

    Hour codes: 0=power, 1=full outage, 2=first 30m, 3=last 30m.
    Do not infer values from summaries, change logs, other operators or stale dates.
    """
    if not html:
        return None
    tag=BeautifulSoup(html,'html.parser').find('script',id='ng-state')
    if not tag:
        return None
    try: state=json.loads(tag.get_text())
    except (ValueError, TypeError):return None
    outcomes=set()
    def scan(node):
        if isinstance(node,dict):
            if node.get('queue')==group and node.get('initiator')==operator:
                for field in ('today','tomorrow'):
                    if node.get(field+'Date')!=target.isoformat():continue
                    if node.get(field+'Status')!='ScheduleApplies':continue
                    slots=node.get(field)
                    maybe=node.get(field+'Possible',[])
                    if not isinstance(slots,list) or len(slots)!=24 or any(type(v) is not int or v not in (0,1,2,3) for v in slots):
                        continue
                    if isinstance(maybe,list) and any(v!=0 for v in maybe):
                        continue # possible outages cannot be labeled firm
                    ranges=[]
                    for hour,code in enumerate(slots):
                        a=f'{hour:02d}:00'; half=f'{hour:02d}:30'; b=f'{hour+1:02d}:00'
                        if code==1:ranges.append((a,b))
                        elif code==2:ranges.append((a,half))
                        elif code==3:ranges.append((half,b))
                    outcomes.add(normalize(ranges))
            for value in node.values():scan(value)
        elif isinstance(node,list):
            for value in node:scan(value)
    scan(state)
    return next(iter(outcomes)) if len(outcomes)==1 else None

def source_reports(result,bez,koly,bude,region,live,old,alerts=None):
    """Show what each distinct site actually reported, independently of consensus."""
    target = tuple(tuple(x) for x in result.get('outages',[]))
    raw = {
        'Карта світла': {
            'ranges':bez['candidates'][0] if len(bez['candidates'])==1 else None,
            'partial':[], 'url':bez.get('url',MAP_REGION)},
        'КолиСвітло':{'ranges':koly,'partial':[],'url':KOLY},
        'КолиБуде':{'ranges':bude,'partial':[],'url':KOLBUDE},
        'Київщина.info':{'ranges':region,'partial':[],'url':KYIVSHCHYNA},
        'Alerts Energy':{'ranges':alerts,'partial':[],'url':ALERTS_REGION},
    }
    output={}
    old_reports=old.get('source_reports',{})
    for name,entry in raw.items():
        ranges=entry['ranges']
        part=entry['partial']
        prev=old_reports.get(name,{})
        if ranges is None:
            output[name]={'status':'old' if prev.get('outages') is not None else 'unavailable',
                          'outages':prev.get('outages'), 'partial':prev.get('partial',[]),
                          'url':entry['url'], 'fetch_failed': False}
        else:
            outage_list=[list(x) for x in ranges]
            matches=(result['status'] in ('normal','preliminary') and target==ranges and not part)
            output[name]={'status':('match' if result['status']=='normal' else 'preliminary') if matches else 'partial' if part else 'diff',
                          'outages':outage_list,'partial':part,'url':entry['url']}
    return output

def fetch(url, label, errors):
    try:
        r=requests.get(url,timeout=(8,15),headers={'User-Agent':'Mozilla/5.0 (compatible; SvitloDubechnya/1.0)','Accept-Language':'uk-UA,uk;q=0.9'})
        r.raise_for_status()
        return r.text
    except requests.RequestException as exc:
        code=exc.response.status_code if getattr(exc,'response',None) is not None else None
        errors.append(label+': '+type(exc).__name__+(f' HTTP {code}' if code is not None else ''))
        return None

DTEK_TELEGRAM = 'https://t.me/s/dtek_ua'
EMERGENCY_MAX_AGE = timedelta(hours=36)
EMERGENCY_FALLBACK_AGE = timedelta(hours=8)


def parse_dtek_notice(text):
    """Classify explicit official operator notices, never generic news or forecasts."""
    line = re.sub(r'^[^\wА-Яа-яІіЇїЄєҐґ]*', '', text.strip().lower())
    # Telegram uses emoji headings. Only a notice headed with a location is actionable.
    combined = bool(re.match(r'київ\s+(?:та|і)\s+київськ(?:а область|ій області)', line))
    oblast = combined or bool(re.match(r'(?:київщина|київська область)\s*[:–,\s]', line))
    city = combined or bool(re.match(r'київ\s*[:–,]', line)) or bool(
        re.match(r'(?:правий|лівий)\s+берег\s+києва\s*[:–,]', line))
    if not city and not oblast:
        return None
    # An explicit cancellation is stronger than generic mentions of past emergencies.
    cancelled = bool(re.search(
        r'(?:екстрен\w*\s+відключенн\w*\s+скасован|'
        r'поверта[єй]мось\s+до\s+графік|повертаємось\s+до\s+графік|'
        r'графіки\s+відновлен|відновлен[оі]\s+графік)', line))
    emergency = bool(re.search(
        r'екстрен\w*\s+відключ|аварійн\w*\s+відключ|аварія\s+на\s+'
        r'|графіки\s+(?:тимчасово\s+|наразі\s+)?не\s+діють'
        r'|графіки\s+відключень\s+.+?\s+не\s+діють', line))
    if not cancelled and not emergency:
        return None
    city_partial = city and bool(re.search(
        r'правий\s+берег|лівий\s+берег|(?:частин\w*\s+)?'
        r'(?:оболонськ|дарницьк|деснянськ|подільськ|голосіївськ|'
        r'шевченківськ|печерськ|солом.?янськ|святошинськ|дніпровськ)'
        r'|(?:окремих|цих|деяких)\s+район', line))
    oblast_partial = oblast and bool(re.search(
        r'(?:у|в|по)\s+[\w,\s–-]{0,120}район(?:і|ах)|'
        r'вишгородськ|бучанськ|броварськ|бориспільськ|'
        r'обухівськ|фастівськ|білоцерківськ', line))
    return {
        'kind': 'clear' if cancelled else 'emergency',
        'city': city, 'oblast': oblast,
        'city_partial': city_partial,
        'oblast_partial': oblast_partial,
        # The dacha is in Vyshhorod district. Don't apply notices naming other
        # oblast districts to this location.
        'dacha_affected': not oblast_partial or 'вишгородськ' in line,
    }


def parse_dtek_telegram(html, now):
    """Read timestamped original DTEK Telegram posts; prefer latest per geography."""
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    messages = []
    for post in soup.select('.tgme_widget_message[data-post]'):
        text_node = post.select_one('.tgme_widget_message_text')
        time_node = post.select_one('time[datetime]')
        identifier = post.get('data-post', '')
        if not text_node or not time_node or not re.fullmatch(r'dtek_ua/\d+', identifier):
            continue
        try:
            published = datetime.fromisoformat(time_node['datetime'].replace('Z', '+00:00'))
            if published.tzinfo is None:
                continue
            published = published.astimezone(KYIV)
        except (ValueError, KeyError, TypeError):
            continue
        if not -timedelta(minutes=5) <= now - published <= EMERGENCY_MAX_AGE:
            continue
        body = text_node.get_text(' ', strip=True)
        classification = parse_dtek_notice(body)
        if classification:
            messages.append((published, int(identifier.split('/')[1]), body, classification, identifier))
    messages.sort(key=lambda item: (item[0], item[1]), reverse=True)
    result = {}
    for loc in ('city', 'dacha'):
        for published, post_id, body, notice, identifier in messages:
            if loc == 'city' and not notice['city']:
                continue
            if loc == 'dacha' and (not notice['oblast'] or not notice['dacha_affected']):
                continue
            if notice['kind'] == 'clear':
                result[loc] = None
            else:
                partial = notice['city_partial'] if loc == 'city' else notice['oblast_partial']
                result[loc] = {
                    'level': 'partial' if partial else 'active',
                    'text': body[:300],
                    'url': 'https://t.me/' + identifier,
                    'published_at': published.isoformat(timespec='minutes'),
                    'source': 'ДТЕК, офіційний Telegram',
                    'source_checked': True
                }
            break
    return result


def select_emergency(parsed, key, previous, now, fetched):
    """Keep an unverified recent operator notice through a transient fetch failure."""
    # A recent explicit cancellation clears the alert. If the Telegram page
    # is truncated or unavailable, preserve a recent alert as unverified.
    if key in parsed:
        return parsed[key]
    if not isinstance(previous, dict):
        return None
    try:
        published = datetime.fromisoformat(previous['published_at']).astimezone(KYIV)
    except (KeyError, TypeError, ValueError):
        return None
    if now - published > EMERGENCY_FALLBACK_AGE:
        return None
    return {**previous, 'source_checked': False}


def choose(day,bez,koly,bude,old,additional=None,primary_source='БезСвітла',allow_early=False):
    votes=defaultdict(set)
    if koly is not None:votes[koly].add('КолиСвітло')
    if bude is not None:votes[bude].add('КолиБуде')
    for source,intervals in (additional or {}).items():
        if intervals is not None:
            votes[intervals].add(source)
    for option in bez['candidates']: votes[option].add(primary_source)
    confirmed=sorted(((len(s),off,s) for off,s in votes.items() if len(s)>=2),key=lambda x:x[0],reverse=True)
    base={'date':day.isoformat(),'url':bez.get('url',BEZ+day.isoformat()),'source_updated':bez['updated']}
    if confirmed and (len(confirmed)==1 or confirmed[0][0]>confirmed[1][0]):
        _,ranges,sources=confirmed[0]
        return {**base,'status':'normal','outages':[list(x) for x in ranges],'sources':sorted(sources),'detail':'Зіставлено незалежні джерела'}
    why='Графік ще не опубліковано' if bez['unpublished'] else 'Суперечливі джерела' if confirmed else 'Очікуємо незалежне підтвердження' if votes else 'Немає підтверджених даних'
    if old.get('date')==day.isoformat() and old.get('status') in ('normal','stale') and 'outages' in old:
        return {**base,'status':'stale','outages':old['outages'],'sources':old.get('sources',[]),'detail':why}
    # Show fresh, date-scoped first reports for tomorrow instead of hiding them
    # while a second independent provider has not caught up.
    # An ambiguous alternating BeZ/map page must not be trusted on its own.
    provisional_votes={off:set(srcs) for off,srcs in votes.items()}
    if len(bez.get('candidates',[]))!=1:
        for srcs in provisional_votes.values():srcs.discard(primary_source)
    provisional_votes={off:srcs for off,srcs in provisional_votes.items() if srcs}
    if allow_early and provisional_votes:
        preferred=['Alerts Energy','Карта світла','КолиСвітло','КолиБуде','Київщина.info','БезСвітла']
        def rank(item):
            off,srcs=item
            first=min((preferred.index(src) if src in preferred else len(preferred)) for src in srcs)
            return (-len(srcs),first,str(off))
        ordered=sorted(provisional_votes.items(),key=rank)
        selected,sources=ordered[0]
        alternatives=[{'sources':sorted(srcs),'outages':[list(x) for x in off]}
                      for off,srcs in ordered[1:]]
        detail=('Джерела показують різні години. Потрібне підтвердження.'
                if alternatives else 'Перші дані з одного джерела. Потрібне підтвердження.')
        return {**base,'status':'preliminary','outages':[list(x) for x in selected],
                'sources':sorted(sources),'alternatives':alternatives,'detail':detail}
    return {**base,'status':'unknown','outages':[],'sources':[],'detail':why}

def change(old,new):
    if new['status']!='normal': return None
    if old.get('status') in ('normal','stale') and old.get('outages')==new['outages']: return None
    def fmt(r): return ', '.join(a+'–'+b for a,b in r) if r else 'відключень немає'
    if 'outages' not in old or old.get('status')=='unknown': return 'Опубліковано графік: '+fmt(new['outages'])
    return 'Змінено графік: '+fmt(old['outages'])+' → '+fmt(new['outages'])


def record_source_observations(now, previous, entry):
    """Persist first observation of each source's currently published interval set."""
    seen=previous.get('source_observations',{})
    observed={}
    stamp=now.isoformat(timespec='minutes')
    for name,report in entry.get('source_reports',{}).items():
        # A carried-over 'old' value is NOT a newly checked source report.
        if report.get('status') in ('old','unavailable') or not isinstance(report.get('outages'),list):
            continue
        fingerprint=json.dumps(report['outages'],ensure_ascii=False,sort_keys=True)
        prior=seen.get(name,{})
        observed[name]={'fingerprint':fingerprint,
                         'first_seen':prior['first_seen'] if prior.get('fingerprint')==fingerprint and prior.get('first_seen') else stamp}
    entry['source_observations']=observed
    return entry

def earliest_observed_source(entry):
    """A single first observed signal, only if there was no timestamp tie."""
    target=json.dumps(entry.get('outages',[]),ensure_ascii=False,sort_keys=True)
    candidates=[(x['first_seen'],name) for name,x in entry.get('source_observations',{}).items()
                if x.get('fingerprint')==target and name in entry.get('sources',[])]
    if not candidates:return None
    best=min(t for t,_ in candidates)
    leaders=[name for stamp,name in candidates if stamp==best]
    return leaders[0] if len(leaders)==1 else None

def preliminary_event(now,target,entry):
    """Record that tomorrow's first date-scoped report was seen, not confirmed."""
    ranges=', '.join(a+'–'+b for a,b in entry.get('outages',[])) or 'без відключень'
    return {'at':now.isoformat(timespec='minutes'),'date':target.isoformat(),
            'kind':'preliminary','before':None,'after':entry['outages'],
            'message':'Попередній графік: '+ranges,
            'sources_confirmed':[],
            'first_observed_source':earliest_observed_source(entry)}

def make_log_event(now,target,old,new,message):
    """Log the time this checker DETECTED a change, not an inferred source publish time."""
    changed=(old.get('status') in ('normal','stale') and 'outages' in old
             and old.get('outages') != new.get('outages'))
    return {
        'at':now.isoformat(timespec='minutes'),
        'date':target.isoformat(),
        'kind':'changed' if changed else 'published',
        'before':old.get('outages') if changed else None,
        'after':new.get('outages',[]),
        'message':message,
        'sources_confirmed':new.get('sources',[]),
        'first_observed_source':earliest_observed_source(new)
    }


CITY_KOLY = 'https://kolysvitlo.com/schedule/dtek_kyiv'
CITY_BUDE = 'https://kolybude.com/kyiv'
CITY_LOCATIONS = {
    'home': {'name':'Дім','group':'4.1','address_verified':False},
    'solovky': {'name':'Соловки','group':'4.1','address_verified':False},
    'naumenky': {'name':'Науменки','group':'10.1','address_verified':False}
}

def parse_city_bez(html, target, group):
    """Adapt the alternating, full-day BeZ light/off block to any Kyiv queue."""
    raw = plain(html)
    if target.strftime('%d.%m.%Y') not in raw[:1300]:
        return {'candidates':[], 'updated':'', 'unpublished':False}
    if re.search(r'Графік відключень на\s*'+re.escape(target.strftime('%d.%m.%Y'))+r'\s+ще не опублікован',raw[:2000],re.I):
        return {'candidates':[], 'updated':'', 'unpublished':True}
    section=re.search(r'Графік\s+Черга\s+'+re.escape(group)+r'\b(.*?)(?:Зберегти підчергу|Історія змін|Графік\s+Черга\s+\d+\.\d+)',raw,re.I|re.S)
    if not section:
        return {'candidates':[], 'updated':'', 'unpublished':False}
    blocks=pairs(section.group(1))
    if not blocks or blocks[0][0]!='00:00' or blocks[-1][1]!='24:00' or any(blocks[i][1]!=blocks[i+1][0] for i in range(len(blocks)-1)):
        return {'candidates':[],'updated':'','unpublished':False}
    # Alternation direction is not documented; corroboration chooses between candidates.
    options=list(dict.fromkeys([normalize(blocks[::2]),normalize(blocks[1::2])]))
    return {'candidates':options,'updated':'','unpublished':False}

def city_scope(html,target,today):
    page=plain(html)
    label=f'{target.day} {MONTHS[target.month]}'
    if target==today:
        match=re.search(r'Сьогодні[, ]+(\d{1,2}\s+[А-Яа-яІіЇїЄєҐґ]+)(?:\s+(\d{4}))?',page,re.I)
        if not match or match.group(1).lower()!=label or (match.group(2) and int(match.group(2))!=target.year):return None
        rest=page[match.end():]
        # The tab label "Завтра" is NOT a date section boundary.
        finish=re.search(r'Завтра[, ]+\d{1,2}\s+[А-Яа-яІіЇїЄєҐґ]+|Графік на завтра ще',rest,re.I)
        return rest[:finish.start()] if finish else rest
    match=re.search(r'Завтра[, ]+'+re.escape(label)+r'\s+'+str(target.year),page,re.I)
    if not match:return None
    rest=page[match.end():]
    finish=re.search(r'Про графік|Часті запитання|Сьогодні[, ]+\d',rest,re.I)
    return rest[:finish.start()] if finish else rest

def parse_city_koly(html,target,today,group):
    portion=city_scope(html,target,today)
    if not portion:return None
    row=re.search(r'(?<![\d.])'+re.escape(group)+r'\b(.*?)(?=\s+\d{1,2}\.\d\b|$)',portion,re.S)
    if not row:return None
    content=row.group(1)
    if re.search('Без відключень|Відключень немає',content,re.I):return tuple()
    part=re.search(r'Немає світла:\s*(.*)',content,re.I)
    if not part:return None
    found=pairs(part.group(1))
    return normalize(found) if found else None

def parse_city_bude(html,target,today,group):
    page=plain(html)
    heading=re.search(r'на сьогодні[, ]+(\d{1,2})\s+([А-Яа-яІіЇїЄєҐґ]+)',page,re.I)
    if target!=today or not heading or int(heading.group(1))!=target.day or heading.group(2).lower()!=MONTHS[target.month]:
        return None
    row=re.search(r'Черга\s+'+re.escape(group)+r'\s*:\s*(.*?)(?=\s+Черга\s+\d{1,2}\.\d\b|$)',page,re.I|re.S)
    if not row:return None
    result=pairs(row.group(1))
    return normalize(result) if result else None

def city_sources(entry,bez,koly,bude,street,prev,alerts=None):
    """Only independently parsed schedules count; DTEK uses address-level AJAX, not public page HTML."""
    targets={'Карта світла':street,'КолиСвітло':CITY_KOLY,'КолиБуде':CITY_BUDE,'Alerts Energy':ALERTS_CITY}
    data={'Карта світла':bez['candidates'][0] if len(bez['candidates'])==1 else None,
          'КолиСвітло':koly,'КолиБуде':bude,'Alerts Energy':alerts}
    previous=prev.get('source_reports',{})
    compare=tuple(tuple(x) for x in entry.get('outages',[]))
    out={}
    for name,url in targets.items():
        value=data[name]
        if value is not None:
            out[name]={'status':('match' if entry['status']=='normal' else 'preliminary') if entry['status'] in ('normal','preliminary') and value==compare else 'diff',
                       'outages':[list(x) for x in value],'url':url,'partial':[]}
        else:
            older=previous.get(name,{})
            out[name]={'status':'old' if older.get('outages') is not None else 'unavailable',
                       'outages':older.get('outages'),'url':url,'partial':[]}
    return out

def update_city_locations(now,today,old,errors):
    """Separate city operator, street address, queue, and history; never reuse dacha data."""
    groups={config['group'] for config in CITY_LOCATIONS.values()}
    urls={'koly':(CITY_KOLY,'КолиСвітло Київ'),
          'bude':(CITY_BUDE,'КолиБуде Київ'),
          'alerts':(ALERTS_CITY,'Alerts Energy Київ')}
    urls.update({group:(MAP_CITY_PREFIX+group,'Карта світла Київ '+group) for group in groups})
    with ThreadPoolExecutor(max_workers=len(urls)) as pool:
        jobs={key:pool.submit(fetch,url,label,errors) for key,(url,label) in urls.items()}
        pages={key:job.result() for key,job in jobs.items()}
    city_koly,city_bude,city_alerts=pages['koly'],pages['bude'],pages['alerts']
    city_map_pages={group:pages[group] for group in groups}
    result={}
    old_locations=old.get('locations',{})
    for key,config in CITY_LOCATIONS.items():
        old_loc=old_locations.get(key,{})
        days={k:v for k,v in old_loc.get('days',{}).items()
              if k>=(today-timedelta(days=2)).isoformat()}
        logs=list(old_loc.get('logs',[]))
        for target in (today,today+timedelta(days=1)):
            url=MAP_CITY_PREFIX+config['group']
            bez=parse_mapasvitla(city_map_pages[config['group']],target,today,config['group'])
            bez['url']=url
            koly=parse_city_koly(city_koly,target,today,config['group']) if city_koly else None
            bude=parse_city_bude(city_bude,target,today,config['group']) if city_bude else None
            prev=old_loc.get('days',{}).get(target.isoformat(),{})
            # Uses same two-source quorum as the dacha, but the city sources are distinct.
            alerts=parse_alerts(city_alerts,target,config['group'],'kyiv_oblenergo')
            entry=choose(target,bez,koly,bude,prev,{'Alerts Energy':alerts},primary_source='Карта світла',allow_early=target>today)
            entry['url']=url
            entry['source_reports']=city_sources(entry,bez,koly,bude,url,prev,alerts)
            record_source_observations(now,prev,entry)
            entry['group']=config['group']
            days[target.isoformat()]=entry
            msg=change(prev,entry)
            if msg:logs.insert(0,make_log_event(now,target,prev,entry,msg))
            elif entry['status']=='preliminary' and (prev.get('status')!='preliminary' or prev.get('outages')!=entry['outages']):
                logs.insert(0,preliminary_event(now,target,entry))
        logs=[x for x in logs if x.get('date','0000')>=(today-timedelta(days=6)).isoformat()][:60]
        result[key]={'name':config['name'],'group':config['group'],'address_verified':config['address_verified'],
                     'days':days,'logs':logs,'operator':'ДТЕК Київські електромережі'}
    return result

def main():
    now=datetime.now(KYIV);today=now.date();tomorrow=today+timedelta(days=1)
    try: old=json.loads(STATE.read_text(encoding='utf-8'))
    except (FileNotFoundError,ValueError): old={'days':{},'logs':[]}
    errors=[]
    sources={
        'koly':(KOLY,'КолиСвітло'),
        'bude':(KOLBUDE,'КолиБуде'),
        'official':(DTEK,'ДТЕК'),
        'region_html':(KYIVSHCHYNA,'Київщина.info'),
        'region_alerts':(ALERTS_REGION,'Alerts Energy Київська область'),
        'map_region_html':(MAP_REGION,'Карта світла Київська область 3.1'),
        'dtek_telegram':(DTEK_TELEGRAM,'ДТЕК оперативні повідомлення'),
    }
    with ThreadPoolExecutor(max_workers=len(sources)+1) as pool:
        jobs={key:pool.submit(fetch,url,label,errors) for key,(url,label) in sources.items()}
        city_job=pool.submit(update_city_locations,now,today,old,errors)
        results={key:job.result() for key,job in jobs.items()}
        city=city_job.result()
    koly,bude,official=results['koly'],results['bude'],results['official']
    region_html=results['region_html']
    region_alerts,map_region_html=results['region_alerts'],results['map_region_html']
    telegram_html=results['dtek_telegram']
    emergency_posts=parse_dtek_telegram(telegram_html,now)
    old_dacha=old.get('emergency')
    dacha_emergency=select_emergency(emergency_posts,'dacha',old_dacha,now,telegram_html is not None)
    old_city_locations=old.get('locations',{})
    for city_key,city_location in city.items():
        previous=old_city_locations.get(city_key,{}).get('emergency')
        city_location['emergency']=select_emergency(
            emergency_posts,'city',previous,now,telegram_html is not None)

    days={};logs=list(old.get('logs',[]))
    for target in (today,tomorrow):
        bez=parse_mapasvitla(map_region_html,target,today,'3.1')
        bez['url']=MAP_REGION
        a=parse_kolysvitlo(koly,target,today) if koly else None
        
        b=parse_kolybude(bude,target,today) if bude else None
        region=parse_kyivshchyna(region_html,target,today) if region_html else None
        live=None  # Svitlo.live is no longer treated as a current reference
        previous=old.get('days',{}).get(target.isoformat(),{})
        alerts=parse_alerts(region_alerts,target,'3.1','kyivska_oblast_oblenergo')
        entry=choose(target,bez,a,b,previous,{'Київщина.info':region,'Alerts Energy':alerts},primary_source='Карта світла',allow_early=target>today)
        entry['source_reports']=source_reports(entry,bez,a,b,region,live,previous,alerts)
        record_source_observations(now,previous,entry)
        days[target.isoformat()]=entry
        event=change(previous,entry)
        if event:logs.insert(0,make_log_event(now,target,previous,entry,event))
        elif entry['status']=='preliminary' and (previous.get('status')!='preliminary' or previous.get('outages')!=entry['outages']):
            logs.insert(0,preliminary_event(now,target,entry))
    logs=[x for x in logs if x.get('date','0000')>=(today-timedelta(days=6)).isoformat()][:60]
    save={'days':{k:v for k,v in old.get('days',{}).items() if k>=(today-timedelta(days=2)).isoformat()},'logs':logs}
    save['days'].update(days)
    save['locations']=city
    save['emergency']=dacha_emergency
    hb=old.get('last_heartbeat','')
    save['last_heartbeat']=today.isoformat() if not hb or hb<=(today-timedelta(days=7)).isoformat() else hb
    STATE.parent.mkdir(exist_ok=True,parents=True)
    content=json.dumps(save,ensure_ascii=False,indent=2,sort_keys=True)+'\n'
    if not STATE.exists() or STATE.read_text(encoding='utf-8')!=content:STATE.write_text(content,encoding='utf-8')
    update_season(save, today)
    # Publish an archived yesterday snapshot for the historic summary card.
    # The front end never treats yesterday's stored prediction as a live sensor.
    visible_days={k:v for k,v in old.get('days',{}).items()
                  if k==(today-timedelta(days=1)).isoformat()}
    visible_days.update(days)
    payload={'updated_at':now.isoformat(timespec='seconds'),'today_date':today.isoformat(),'tomorrow_date':tomorrow.isoformat(),'days':visible_days,'logs':logs,'locations':{'dacha':{'name':'Дача','group':'3.1','address_verified':True,'days':visible_days,'logs':logs,'emergency':dacha_emergency,'operator':'ДТЕК Київські регіональні електромережі'},**city},'source_health':{'dtek_reachable':official is not None,'issues':errors}}
    OUTPUT.parent.mkdir(exist_ok=True,parents=True)
    OUTPUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Checked:',now.isoformat(timespec='minutes'),[(d,e['status'],e['outages']) for d,e in days.items()])
    if errors:print('Warnings:',errors,file=sys.stderr)
if __name__=='__main__':main()
