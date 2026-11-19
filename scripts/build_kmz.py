"""Build per-state ATAK KMZ files of high-consequence industrial facilities.

Usage:
  python build_kmz.py RMP_DIR OUT_DIR ECHO_MAJOR_NPDES.csv EIA_POWER_PLANTS.csv ECHO_DRINKING_WATER.csv

Sources:
  - EPA Risk Management Program facilities (Data Liberation Project export, active only)
  - EPA ECHO major NPDES permits, POTW type -> wastewater layer
  - EPA ECHO NPDES permits with SIC 4941 (water supply) -> drinking water layer
  - EIA power plants >=50 MW (fossil, hydro, biomass, etc.; no solar/wind/battery) + all nuclear
"""
import csv, math, os, re, sys, zipfile, collections, html
from PIL import Image, ImageDraw

RMP_DIR = sys.argv[1]
OUT = sys.argv[2]
POTW_CSV = sys.argv[3] if len(sys.argv) > 3 and os.path.exists(sys.argv[3]) else None
PP_CSV = sys.argv[4] if len(sys.argv) > 4 and os.path.exists(sys.argv[4]) else None
WATER_CSV = sys.argv[5] if len(sys.argv) > 5 and os.path.exists(sys.argv[5]) else None
TRI_CSV = sys.argv[6] if len(sys.argv) > 6 and os.path.exists(sys.argv[6]) else None

STATES = {
 'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado','CT':'Connecticut',
 'DE':'Delaware','DC':'District of Columbia','FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho','IL':'Illinois',
 'IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland',
 'MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi','MO':'Missouri','MT':'Montana',
 'NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey','NM':'New Mexico','NY':'New York',
 'NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania',
 'RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee','TX':'Texas','UT':'Utah',
 'VT':'Vermont','VA':'Virginia','WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming',
 'PR':'Puerto Rico','GU':'Guam','VI':'US Virgin Islands','AS':'American Samoa','MP':'Northern Mariana Islands'}
NAME2AB = {v.lower(): k for k, v in STATES.items()}

CATS = {  # key: (folder name, RGB)
 'nuke':  ('Nuclear Power Plants', (255, 215, 0)),
 'chem':  ('Chemical / Hazmat (EPA RMP)', (220, 40, 40)),
 'ind':   ('Heavy Industry / Toxic Releases (EPA TRI)', (255, 120, 0)),
 'water': ('Drinking Water Treatment', (30, 110, 230)),
 'waste': ('Wastewater Treatment', (140, 90, 40)),
 'power': ('Power Plants', (245, 190, 0)),
}

def tc(s):
    s = (s or '').strip()
    if s.isupper() or s.islower():
        s = ' '.join(w if len(w) <= 3 and w.upper() in ('LLC','INC','USA','WWTP','WTP','WWTF','POTW','STP','WPCF','LP','CO','II','III','MUD','PUD','FS','US','USA','TVA','LNG','LPG') else w.capitalize() for w in s.split())
    return s

def fnum(v):
    try:
        return float(v)
    except Exception:
        return None

def fix_lon(st, lon):
    if lon is not None and lon > 0 and st not in ('GU', 'MP') and not (st == 'AK' and lon > 170):
        return -lon
    return lon

def ok_coord(lat, lon):
    return lat is not None and lon is not None and -90 < lat < 90 and -180 < lon < 180 and not (lat == 0 and lon == 0)

def dist_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 6371000 * 2 * math.asin(math.sqrt(d))

# ---------- RMP ----------
naics = {r['NAICSCode']: r['Description'] for r in csv.DictReader(open(os.path.join(RMP_DIR, 'naics-codes.csv'), encoding='utf-8'))}

# ---------- ERG 2024 lookup (UN/NA ID + guide) ----------
ERG_TSV = os.environ.get('ERG_TSV', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'erg2024_pubchem.tsv'))
ERG_MAP = os.environ.get('ERG_MAP', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'rmp_to_erg.csv'))
erg_rows = list(csv.DictReader(open(ERG_TSV, encoding='utf-8'), delimiter='\t')) if os.path.exists(ERG_TSV) else []
erg_map = {}
if erg_rows and os.path.exists(ERG_MAP):
    for m in csv.DictReader(open(ERG_MAP, encoding='utf-8')):
        opts = []
        for e in [v.strip() for v in m['erg_names'].split(';') if v.strip()]:
            nm, _, un = e.partition('|')
            hit = next(h for h in erg_rows if h['Name'] == nm and (not un or h['UN'] == un))
            flags = []
            if 'TIH' in hit['Note']: flags.append('TIH')
            if 'Water-reactive' in hit['Note']: flags.append('water-reactive')
            opts.append(f"UN{hit['UN']} (ERG {hit['Guide']}{', ' + ', '.join(flags) if flags else ''})")
        erg_map[m['rmp_name']] = (opts, m['note'])

def chem_label(name):
    base = re.sub(r'\s*\[.*$', '', name).strip()
    if base not in erg_map:
        return base
    opts, note = erg_map[base]
    if not opts:
        return f"{base}: no UN number ({note})" if note else base
    s = f"{base}: {' or '.join(opts)}"
    return s + (f" [{note}]" if note and len(opts) > 1 else '')

def chem_list(s):
    names = []
    for part in (s or '').split('•'):
        n = re.sub(r'\{.*?\}', '', part).strip()
        if n and n not in names:
            names.append(n)
    return names

facs = []  # dict: state, cat, name, addr, lat, lon, desc_lines, src
for r in csv.DictReader(open(os.path.join(RMP_DIR, 'facilities.csv'), encoding='utf-8')):
    if r['LatestDeregDate']:
        continue
    lat, lon = fnum(r['Lat']), fix_lon(r['State'], fnum(r['Lng']))
    if not ok_coord(lat, lon) or r['State'] not in STATES:
        continue
    codes = [c for c in (r['NAICSCodesInLatest'] or '').replace('•', ',').split(',') if c.strip()]
    codes = [c.strip() for c in codes]
    first = codes[0] if codes else ''
    if first.startswith('22131'):
        cat = 'water'
    elif first.startswith('22132'):
        cat = 'waste'
    elif first.startswith('2211'):
        cat = 'power'
    else:
        cat = 'chem'
    chems = chem_list(r['ChemicalsInLatest'])
    acts = [naics.get(c, c) for c in codes]
    op = tc(r['LatestOperator'] or r['LatestCompany1'])
    addr = ', '.join(x for x in [tc(r['Addr1']), tc(r['Addr2']), tc(r['City']), f"{r['State']} {r['ZipCode']}".strip()] if x)
    desc = [('Type', '; '.join(dict.fromkeys(acts)) or 'Not listed')]
    desc += [('Chemical', chem_label(c)) for c in chems[:10]]
    if len(chems) > 10:
        desc.append(('Chemical', f'+{len(chems) - 10} more (see EPA RMP record)'))
    if op:
        desc.append(('Operator', op))
    if r['NumAccidentsInLatest'] and r['NumAccidentsInLatest'] != '0':
        desc.append(('Accidents in 5-yr RMP history', r['NumAccidentsInLatest']))
    desc.append(('Source', f"EPA RMP, facility ID {r['EPAFacilityID']}, last update {r['LatestReceiptDate']}"))
    facs.append(dict(state=r['State'], cat=cat, name=tc(r['Name']), addr=addr, lat=lat, lon=lon, desc=desc, nuke=False, src='rmp'))

rmp_count = len(facs)

def near_existing(state, cat, lat, lon, radius):
    for f in by_state_cat[(state, cat)]:
        if abs(f['lat']-lat) < 0.02 and abs(f['lon']-lon) < 0.03 and dist_m((f['lat'], f['lon']), (lat, lon)) < radius:
            return True
    return False

by_state_cat = collections.defaultdict(list)
for f in facs:
    by_state_cat[(f['state'], f['cat'])].append(f)

# ---------- ECHO POTWs ----------
potw_added = 0
if POTW_CSV:
    for r in csv.DictReader(open(POTW_CSV, encoding='utf-8', errors='replace')):
        if r.get('CWPFacilityTypeIndicator') != 'POTW':
            continue
        if (r.get('CWPPermitStatusDesc') or '') in ('Terminated', 'Expired', 'Not Needed', 'Retired', 'Pending'):
            continue
        st = r.get('CWPState')
        lat, lon = fnum(r.get('FacLat')), fix_lon(st, fnum(r.get('FacLong')))
        if st not in STATES or not ok_coord(lat, lon):
            continue
        if near_existing(st, 'waste', lat, lon, 800):
            continue
        flow = fnum(r.get('CWPTotalDesignFlowNmbr'))
        addr = ', '.join(x for x in [tc(r.get('CWPStreet')), tc(r.get('CWPCity')), f"{st} {(r.get('CWPZip') or '')[:5]}".strip()] if x)
        desc = [('Type', 'Publicly owned wastewater treatment plant (major NPDES permit)')]
        if flow:
            desc.append(('Design flow', f'{flow:g} million gallons/day'))
        desc.append(('Source', f"EPA ECHO, NPDES permit {r.get('SourceID')} ({r.get('CWPPermitStatusDesc')})"))
        f = dict(state=st, cat='waste', name=tc(r.get('CWPName')), addr=addr, lat=lat, lon=lon, desc=desc, nuke=False)
        facs.append(f); by_state_cat[(st, 'waste')].append(f); potw_added += 1

# ---------- ECHO drinking water plants (SIC 4941 NPDES permits) ----------
water_added = 0
if WATER_CSV:
    for r in csv.DictReader(open(WATER_CSV, encoding='utf-8', errors='replace')):
        if re.search(r'Terminated|Expired|Not Needed|Retired|Pending|Denied|Withdrawn', r.get('CWPPermitStatusDesc') or ''):
            continue
        st = r.get('CWPState')
        lat, lon = fnum(r.get('FacLat')), fix_lon(st, fnum(r.get('FacLong')))
        if st not in STATES or not ok_coord(lat, lon):
            continue
        if r.get('CWPFacilityTypeIndicator') == 'POTW':
            continue
        if near_existing(st, 'water', lat, lon, 500):
            continue
        addr = ', '.join(x for x in [tc(r.get('CWPStreet')), tc(r.get('CWPCity')), f"{st} {(r.get('CWPZip') or '')[:5]}".strip()] if x)
        desc = [('Type', 'Drinking water treatment plant'),
                ('Source', f"EPA ECHO, NPDES permit {r.get('SourceID')} ({r.get('CWPPermitStatusDesc')})")]
        f = dict(state=st, cat='water', name=tc(r.get('CWPName')), addr=addr, lat=lat, lon=lon, desc=desc, nuke=False)
        facs.append(f); by_state_cat[(st, 'water')].append(f); water_added += 1

# ---------- EIA power plants ----------
pp_added = 0
if PP_CSV:
    for r in csv.DictReader(open(PP_CSV, encoding='utf-8', errors='replace')):
        st = NAME2AB.get((r.get('State') or '').lower(), r.get('State'))
        lat, lon = fnum(r.get('Latitude')), fnum(r.get('Longitude'))
        if st not in STATES or not ok_coord(lat, lon):
            continue
        src = (r.get('PrimSource') or '').lower()
        nuke = 'nuclear' in src or 'Nuclear' in (r.get('source_des') or '')
        mw = fnum(r.get('Total_MW')) or 0
        # drop RMP duplicate of the same plant (keep the EIA record, it has capacity info; merge chems)
        rmp_dup = None
        for f in by_state_cat[(st, 'power')]:
            if f.get('src') == 'rmp' and dist_m((f['lat'], f['lon']), (lat, lon)) < 1500:
                rmp_dup = f; break
        zip_ = str(r.get('Zip') or '').split('.')[0].zfill(5) if r.get('Zip') else ''
        addr = ', '.join(x for x in [tc(r.get('Street_Add')), tc(r.get('City')), f'{st} {zip_}'.strip()] if x)
        desc = [('Type', f"{'Nuclear' if nuke else src.replace('_',' ').title()} power plant, {mw:,.0f} MW"),
                ('Generation mix', r.get('source_des') or '')]
        if r.get('Utility_Na'):
            desc.append(('Operator', r['Utility_Na']))
        if rmp_dup:
            for k, v in rmp_dup['desc']:
                if k == 'Chemical':
                    desc.append((k, v))
            by_state_cat[(st, 'power')].remove(rmp_dup); facs.remove(rmp_dup)
        if nuke:
            desc.append(('Emergency planning zones (NRC)', '10-mile plume exposure EPZ; 50-mile ingestion pathway EPZ'))
        desc.append(('Source', f"EIA-860/860M, plant code {r.get('Plant_Code')}"))
        f = dict(state=st, cat='nuke' if nuke else 'power', name=r.get('Plant_Name') or '', addr=addr, lat=lat, lon=lon, desc=desc, nuke=nuke)
        facs.append(f); by_state_cat[(st, f['cat'])].append(f); pp_added += 1

# ---------- EPA TRI heavy industry (facilities not already pinned) ----------
TRI_HEAVY = {'Chemicals', 'Petroleum', 'Petroleum Bulk Terminals', 'Chemical Wholesalers', 'Metal Mining',
             'Primary Metals', 'Coal Mining', 'Hazardous Waste', 'Paper', 'Natural Gas Processing', 'Electric Utilities'}
TRI_NAICS = ('327310', '327410', '325920')   # cement, lime, explosives
TRI_RELEASE_LB = 10000                         # any sector with >= this many lb on-site releases
erg_by_name = collections.defaultdict(set)
for h in erg_rows:
    erg_by_name[re.sub(r'[^a-z0-9]', '', h['Name'].lower())].add((h['UN'], h['Guide'], h['Note']))

def tri_chem_label(n):
    base = re.sub(r'\s*\(.*?\)', '', n).strip()
    base = re.sub(r'\s+', ' ', base)
    if base in erg_map:
        return chem_label(base)
    hits = erg_by_name.get(re.sub(r'[^a-z0-9]', '', base.lower()), set())
    if len(hits) == 1:
        un, guide, note = next(iter(hits))
        flags = [f for f, k in (('TIH', 'TIH'), ('water-reactive', 'Water-reactive')) if k in note]
        return f"{base}: UN{un} (ERG {guide}{', ' + ', '.join(flags) if flags else ''})"
    return base

tri_added = 0
if TRI_CSV:
    for r in csv.DictReader(open(TRI_CSV, encoding='utf-8', errors='replace')):
        rel = fnum(r['rel']) or 0
        if not (r['sector'] in TRI_HEAVY or r['naics'][:6] in TRI_NAICS or rel >= TRI_RELEASE_LB):
            continue
        st = r['state']
        lat, lon = fnum(r['lat']), fix_lon(st, fnum(r['lon']))
        if st not in STATES or not ok_coord(lat, lon):
            continue
        if any(near_existing(st, c, lat, lon, 400) for c in ('chem', 'power', 'nuke', 'water', 'waste', 'ind')):
            continue
        chems = [c.split('|')[0] for c in r['chems'].split(';') if c]
        addr = ', '.join(v for v in [tc(r['street']), tc(r['city']), f"{st} {r['zip'][:5]}".strip()] if v)
        desc = [('Type', f"{r['sector']} - {naics.get(r['naics'], 'NAICS ' + r['naics'])}")]
        desc += [('Chemical', tri_chem_label(c)) for c in chems[:10]]
        if len(chems) > 10:
            desc.append(('Chemical', f'+{len(chems) - 10} more (see TRI record)'))
        if r['carc'] == '1':
            desc.append(('Carcinogens reported', 'Yes'))
        desc.append(('On-site releases (2024)', f'{rel:,.0f} lb'))
        if r['parent'] and r['parent'] != 'NA':
            desc.append(('Parent company', tc(r['parent'])))
        desc.append(('Source', f"EPA TRI 2024, facility ID {r['id']}"))
        f = dict(state=st, cat='ind', name=tc(r['name']), addr=addr, lat=lat, lon=lon, desc=desc, nuke=False)
        facs.append(f); by_state_cat[(st, 'ind')].append(f); tri_added += 1
    print('TRI added', tri_added)

# ---------- icons ----------
def icon(kind, rgb):
    """Distinct shapes so categories read at a glance: triangle=chem, hexagon=industry,
    circle=water, square=wastewater, diamond+bolt=power, trefoil=nuclear."""
    S = 96
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    W, F = (255, 255, 255, 255), rgb + (255,)
    c = S / 2
    if kind == 'chem':
        d.polygon([(c, 4), (S-4, S-8), (4, S-8)], fill=W)
        d.polygon([(c, 16), (S-14, S-14), (14, S-14)], fill=F)
        d.rectangle((c-4, 36, c+4, 62), fill=W); d.ellipse((c-5, 68, c+5, 78), fill=W)
    elif kind == 'ind':
        hexa = lambda r: [(c + r*math.cos(math.radians(60*i)), c + r*math.sin(math.radians(60*i))) for i in range(6)]
        d.polygon(hexa(44), fill=W); d.polygon(hexa(36), fill=F)
        d.rectangle((c-18, c-6, c+18, c+18), fill=W); d.rectangle((c-14, c-22, c-6, c-6), fill=W)
    elif kind == 'water':
        d.ellipse((6, 6, S-6, S-6), fill=W); d.ellipse((14, 14, S-14, S-14), fill=F)
        d.polygon([(c, 26), (c+14, c+8), (c-14, c+8)], fill=W); d.ellipse((c-14, c-6, c+14, c+22), fill=W)
    elif kind == 'waste':
        d.rectangle((8, 8, S-8, S-8), fill=W); d.rectangle((16, 16, S-16, S-16), fill=F)
        for yy in (34, 48, 62):
            d.line([(26, yy), (38, yy-6), (50, yy), (62, yy-6), (70, yy)], fill=W, width=5)
    elif kind == 'power':
        d.polygon([(c, 2), (S-2, c), (c, S-2), (2, c)], fill=W)
        d.polygon([(c, 12), (S-12, c), (c, S-12), (12, c)], fill=F)
        d.polygon([(c+6, 18), (c-14, c+4), (c-1, c+4), (c-6, S-18), (c+14, c-4), (c+1, c-4)], fill=(0, 0, 0, 255))
    elif kind == 'nuke':
        d.ellipse((2, 2, S-2, S-2), fill=(0, 0, 0, 255)); d.ellipse((7, 7, S-7, S-7), fill=F)
        for start in (-120, 0, 120):
            d.pieslice((12, 12, S-12, S-12), start - 30 - 90, start + 30 - 90, fill=(0, 0, 0, 255))
        d.ellipse((c-17, c-17, c+17, c+17), fill=F); d.ellipse((c-9, c-9, c+9, c+9), fill=(0, 0, 0, 255))
    return im

os.makedirs(OUT, exist_ok=True)
icon_bytes = {}
import io
for k, (_, rgb) in CATS.items():
    b = io.BytesIO(); icon(k, rgb).save(b, 'PNG'); icon_bytes[k] = b.getvalue()

def x(s):
    return html.escape(s or '', quote=True)

def placemark(f):
    style = f['cat']
    lines = [f"<b>{x(k)}:</b> {x(v)}" for k, v in f['desc'] if v]
    d = f"{x(f['addr'])}<br/><br/>" + "<br/>".join(lines)
    return (f"<Placemark><name>{x(f['name'])}</name><address>{x(f['addr'])}</address>"
            f"<styleUrl>#{style}</styleUrl><description><![CDATA[{d}]]></description>"
            f"<Point><coordinates>{f['lon']:.6f},{f['lat']:.6f},0</coordinates></Point></Placemark>")

def style(k):
    scale, label = (1.6, 0.9) if k == 'nuke' else (1.0, 0)
    return (f'<Style id="{k}"><IconStyle><scale>{scale}</scale><Icon><href>files/{k}.png</href></Icon></IconStyle>'
            f'<LabelStyle><scale>{label}</scale></LabelStyle></Style>')

import statistics
out_log = open(os.path.join(OUT, '..', 'outliers.txt'), 'w')
for st in STATES:
    sf = [f for f in facs if f['state'] == st]
    if len(sf) < 3: continue
    mlat = statistics.median(f['lat'] for f in sf); mlon = statistics.median(f['lon'] for f in sf)
    lim = 2500000 if st in ('AK', 'TX', 'CA', 'HI') else 900000
    for f in sf:
        if dist_m((f['lat'], f['lon']), (mlat, mlon)) > lim:
            out_log.write(f"{st}\t{f['name']}\t{f['lat']},{f['lon']}\n"); facs.remove(f)
out_log.close()
summary = {}
for st, sname in STATES.items():
    sf = [f for f in facs if f['state'] == st]
    if not sf:
        continue
    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
             f'<name>{x(sname)} - High-Consequence Facilities</name>', '<open>1</open>',
             f'<description>Public EPA/EIA data. Built {__import__("datetime").date.today()}.</description>']
    parts += [style(k) for k in CATS]
    counts = {}
    for k, (fname, _) in CATS.items():
        items = sorted([f for f in sf if f['cat'] == k], key=lambda f: f['name'])
        counts[k] = len(items)
        if not items:
            continue
        parts.append(f'<Folder><name>{x(fname)} ({len(items)})</name>')
        parts += [placemark(f) for f in items]
        parts.append('</Folder>')
    parts.append('</Document></kml>')
    kml = '\n'.join(parts)
    fn = os.path.join(OUT, f'{st}_{sname.replace(" ", "_")}.kmz')
    with zipfile.ZipFile(fn, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('doc.kml', kml)
        for k, b in icon_bytes.items():
            z.writestr(f'files/{k}.png', b)
    summary[st] = counts

print('RMP', rmp_count, 'POTW added', potw_added, 'water added', water_added, 'EIA added', pp_added, 'total', len(facs))
with open(os.path.join(OUT, '..', 'summary.csv'), 'w') as fh:
    fh.write('state,' + ','.join(CATS) + '\n')
    for st, c in summary.items():
        fh.write(st + ',' + ','.join(str(c[k]) for k in CATS) + '\n')
