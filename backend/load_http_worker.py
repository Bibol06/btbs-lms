"""HTTP generator subprocess. Input contains disposable test sessions; never log it."""
import concurrent.futures
import json
import shutil
import sys
import time
import urllib.request
from collections import Counter

config = json.load(sys.stdin)
paths, cookies = config['paths'], config['cookies']

def request(i, path):
    req = urllib.request.Request(config['url'] + path, headers={'Cookie': cookies[i]})
    with urllib.request.urlopen(req, timeout=12) as response:
        assert response.status == 200
        json.loads(response.read())
        return float(response.headers.get('X-Bench-App-Ms', 0)), float(response.headers.get('X-Bench-Sql-Ms', 0))

for attempt in range(30):
    try:
        request(0, paths[0])
        break
    except Exception:
        if attempt == 29:
            raise
        time.sleep(1)
for i in range(len(cookies)):
    for path in paths:
        request(i, path)

stages = []
for count in config['stages']:
    start = time.monotonic()
    until = start + config['seconds']
    def worker(i):
        values, errors, kinds, timings = [], 0, Counter(), []
        k = 0
        while time.monotonic() < until:
            if shutil.disk_usage(config['disk_root']).free < 3 * 1024**3:
                break
            began = time.monotonic()
            try:
                app_ms, sql_ms = request(i, paths[k % len(paths)])
                timings.append((paths[k % len(paths)], app_ms, sql_ms, (time.monotonic()-began)*1000))
            except Exception as exc:
                errors += 1
                kinds[type(exc).__name__] += 1
            values.append((time.monotonic() - began) * 1000)
            k += 1
            time.sleep(.2)
        return values, errors, kinds, timings
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
        results = list(pool.map(worker, range(count)))
    values = sorted(v for vs, _, _, _ in results for v in vs)
    if not values:
        raise RuntimeError('Disk guard stopped test')
    errors = sum(e for _, e, _, _ in results)
    kinds = Counter()
    for _, _, counts, _ in results:
        kinds.update(counts)
    elapsed = time.monotonic() - start
    timings = [row for _, _, _, rows in results for row in rows]
    endpoints = {}
    for path in paths:
        rows = [row for row in timings if row[0] == path]
        if rows:
            endpoints[path] = dict(requests=len(rows), app_mean_ms=round(sum(r[1] for r in rows)/len(rows)),
                sql_mean_ms=round(sum(r[2] for r in rows)/len(rows)),
                outside_app_mean_ms=round(sum(max(0,r[3]-r[1]) for r in rows)/len(rows)))
    stages.append(dict(clients=count, requests=len(values), errors=errors, endpoints=endpoints,
        error_types=dict(kinds), seconds=round(elapsed, 2), rps=round(len(values)/elapsed, 2),
        p50_ms=round(values[len(values)//2]), p95_ms=round(values[min(len(values)-1, int(len(values)*.95))])))
    if errors or stages[-1]['p95_ms'] > 5000:
        break
print(json.dumps({'stages': stages}))
