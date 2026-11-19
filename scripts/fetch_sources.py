"""Download the source data used by build_kmz.py.

Run on any machine with normal internet access (standard library only):
    python fetch_sources.py data/

Produces:
    data/rmp/facilities.csv, data/rmp/naics-codes.csv   (EPA RMP via Data Liberation Project)
    data/echo_major_npdes.csv                           (EPA ECHO, all major NPDES permits)
    data/echo_drinking_water.csv                        (EPA ECHO, NPDES permits with SIC 4941)
    data/eia_power_plants.csv                           (EIA power plants >=50 MW + nuclear)
    data/tri2024_facilities.csv                         (EPA TRI basic data, one row per facility)
"""
import csv, io, json, os, sys, time, urllib.parse, urllib.request

OUT = sys.argv[1] if len(sys.argv) > 1 else 'data'
os.makedirs(os.path.join(OUT, 'rmp'), exist_ok=True)

STATES = ('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM '
          'NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR GU VI AS MP').split()
ECHO = 'https://echodata.epa.gov/echo/cwa_rest_services.'
QCOLS = '1,2,3,4,5,7,13,26,27,28,30,53,62'
HEADER = ['CWPName', 'SourceID', 'CWPStreet', 'CWPCity', 'CWPState', 'CWPZip', 'FacCountyName', 'FacLat',
          'FacLong', 'CWPTotalDesignFlowNmbr', 'CWPFacilityTypeIndicator', 'CWPPermitStatusDesc',
          'CWPMajorMinorStatusFlag']
RMP_RAW = 'https://raw.githubusercontent.com/data-liberation-project/epa-rmp-spreadsheets/main/data/output/'
EIA = ('https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/'
       'Power_Plants_in_the_US/FeatureServer/0/query')
EIA_FIELDS = ['Plant_Code', 'Plant_Name', 'Utility_Na', 'Street_Add', 'City', 'County', 'State', 'Zip',
              'PrimSource', 'source_des', 'Total_MW', 'Latitude', 'Longitude']


def get(url, tries=4, timeout=180):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'atak-hazard-kml'}),
                                        timeout=timeout) as r:
                return r.read().decode('utf-8', errors='replace')
        except Exception as e:
            print('  retry', i + 1, e)
            time.sleep(5 * (i + 1))
    raise RuntimeError('failed: ' + url)


def echo_pull(extra_params, out_name):
    rows = []
    for st in STATES:
        for attempt in range(3):
            j = json.loads(get(f'{ECHO}get_facilities?output=JSON&p_st={st}&{extra_params}&qcolumns={QCOLS}'))
            res = j.get('Results', {})
            if not res.get('QueryID') or res.get('QueryRows') == '0':
                got = []
                break
            text = get(f"{ECHO}get_download?output=CSV&qid={res['QueryID']}&qcolumns={QCOLS}")
            if not text.lstrip().startswith('"'):   # proxy/HTML error page -> retry
                time.sleep(10)
                continue
            got = list(csv.reader(io.StringIO(text)))[1:]
            break
        else:
            raise RuntimeError(f'ECHO kept failing for {st}')
        rows += [r for r in got if len(r) == len(HEADER)]
        print(f'{out_name}: {st} {len(got)}')
    with open(os.path.join(OUT, out_name), 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_NONNUMERIC)
        w.writerow(HEADER)
        w.writerows(rows)


def eia_pull():
    where = "(Total_MW>=50 AND PrimSource NOT IN ('solar','wind','batteries')) OR Nuclear_MW>0"
    feats, off = [], 0
    while True:
        q = urllib.parse.urlencode({'where': where, 'outFields': ','.join(EIA_FIELDS), 'returnGeometry': 'false',
                                    'orderByFields': 'Plant_Code', 'resultOffset': off,
                                    'resultRecordCount': 2000, 'f': 'json'})
        j = json.loads(get(EIA + '?' + q))
        batch = [f['attributes'] for f in j['features']]
        feats += batch
        if not j.get('exceededTransferLimit') and len(batch) < 2000:
            break
        off += 2000
    with open(os.path.join(OUT, 'eia_power_plants.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=EIA_FIELDS)
        w.writeheader()
        w.writerows(feats)
    print('eia:', len(feats))


def tri_pull(year='2024'):
    cols = ['id', 'name', 'street', 'city', 'state', 'zip', 'lat', 'lon', 'parent', 'sector', 'naics', 'rel', 'carc', 'chems']
    fac = {}
    for st in STATES:
        text = get(f'https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/{year}_{st}/csv')
        rd = csv.reader(io.StringIO(text))
        hdr = next(rd, None)
        if not hdr or not hdr[0].startswith('1. YEAR'):
            print('tri: no data for', st)
            continue
        ix = lambda n: next(i for i, h in enumerate(hdr) if h.startswith(f'{n}.'))
        I = dict(id=ix(2), name=ix(4), street=ix(5), city=ix(6), state=ix(8), zip=ix(9), lat=ix(12), lon=ix(13),
                 parent=ix(17), sector=ix(23), naics=ix(30), chem=ix(37), cas=ix(40), carc=ix(46), rel=ix(65))
        for p in rd:
            if len(p) <= I['rel']:
                continue
            f = fac.setdefault(p[I['id']], {k: p[I[k]] for k in ('id', 'name', 'street', 'city', 'state', 'zip', 'lat',
                                                                 'lon', 'parent', 'sector', 'naics')} | {'rel': 0.0, 'carc': 0, 'chems': {}})
            f['chems'][p[I['chem']]] = p[I['cas']]
            try:
                f['rel'] += float(p[I['rel']] or 0)
            except ValueError:
                pass
            if p[I['carc']] == 'YES':
                f['carc'] = 1
        print('tri:', st)
    with open(os.path.join(OUT, f'tri{year}_facilities.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for f in fac.values():
            f = dict(f, chems=';'.join(f'{n}|{c}' for n, c in f['chems'].items()))
            w.writerow([f[c] for c in cols])


if __name__ == '__main__':
    for f in ('facilities.csv', 'naics-codes.csv'):
        open(os.path.join(OUT, 'rmp', f), 'w', encoding='utf-8').write(get(RMP_RAW + f))
        print('rmp:', f)
    eia_pull()
    echo_pull('p_maj=Y', 'echo_major_npdes.csv')
    echo_pull('p_sic=4941', 'echo_drinking_water.csv')
    tri_pull('2024')
