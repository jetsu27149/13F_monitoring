"""Quarter scan: who filed, how each manager traded, and the conviction moves.

Reads the dashboard's processed CSVs, so run a refresh first. Read-only.

    python3 scripts/quarter_scan.py              # newest report date on disk
    python3 scripts/quarter_scan.py 2026-09-30   # a specific quarter

Managers are split by the `tier` field in investors.json. Platform and macro
books trade thousands of names market-neutral or hedged, so their "new
positions" carry little conviction; the scan reports them separately.
"""
import csv, json, sys
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
ETF_WORDS = ("ETF","TRUST","ISHARES","SPDR","INVESCO QQQ","VANGUARD","SELECT SECTOR","PROSHARES","DIREXION","FUND")

investors = json.loads((ROOT/"investors.json").read_text())
TIER = {i["slug"]: i.get("tier", "conviction") for i in investors}
NAME = {i["slug"]: i["investor"] for i in investors}

def f(x):
    try: return float(x)
    except (TypeError, ValueError): return None
def is_fund(issuer):
    u = (issuer or "").upper()
    return any(w in u for w in ETF_WORDS)

# ---- coverage ------------------------------------------------------------
latest = {}
with (PROC/"holdings.csv").open() as fh:
    for r in csv.DictReader(fh):
        s = r["investor_slug"]
        k = (r["report_date"], r["filing_date"])
        if s not in latest or k > latest[s]: latest[s] = k
dates = Counter(v[0] for v in latest.values())
Q = sys.argv[1] if len(sys.argv) > 1 else max(dates)
filed = sorted(s for s,v in latest.items() if v[0] == Q)
missing = sorted(i["slug"] for i in investors if i["slug"] not in filed)

print(f"# Quarter scan: report date {Q}\n")
print(f"Filed {len(filed)}/{len(investors)}  |  report dates present: {dict(sorted(dates.items()))}")
for t in ("conviction","platform","macro"):
    fs = [NAME[s] for s in filed if TIER[s]==t]; ms=[NAME[s] for s in missing if TIER[s]==t]
    print(f"  {t:<10} filed {len(fs):>2}: {', '.join(fs) or '-'}")
    print(f"  {'':<10} not yet {len(ms):>2}: {', '.join(ms) or '-'}")
print()

# ---- changes for this quarter -------------------------------------------
rows = []
with (PROC/"changes.csv").open() as fh:
    for r in csv.DictReader(fh):
        if r["current_report_date"] != Q and not (r["status"]=="exited" and r["previous_report_date"] and r["investor_slug"] in filed): continue
        if r["investor_slug"] not in filed: continue
        if r["category"] != "equity" or r["put_call"]: continue
        rows.append(r)

def w(r, which):  # weight inside the equity book
    return f(r[f"{which}_category_weight"]) or 0.0

# ---- portfolio-level behaviour -------------------------------------------
print("## Manager behaviour this quarter (equity book, filers only)\n")
print(f"{'manager':<30}{'tier':<11}{'new':>5}{'exit':>6}{'turnover':>10}{'top10':>8}{'book $B':>9}{'chg':>8}")
per = defaultdict(list)
for r in rows: per[r["investor_slug"]].append(r)
beh = []
for s, rs in per.items():
    new = sum(1 for r in rs if r["status"]=="new"); ex = sum(1 for r in rs if r["status"]=="exited")
    turnover = sum(abs(w(r,"current")-w(r,"previous")) for r in rs)/2
    cur = sorted((w(r,"current") for r in rs), reverse=True); top10 = sum(cur[:10])
    book = sum(f(r["current_value_usd"]) or 0 for r in rs); prev = sum(f(r["previous_value_usd"]) or 0 for r in rs)
    chg = (book/prev-1) if prev else 0
    beh.append((s,new,ex,turnover,top10,book,chg))
for s,new,ex,t,top,book,chg in sorted(beh, key=lambda x:(TIER[x[0]]!="conviction", -x[3])):
    print(f"{NAME[s][:29]:<30}{TIER[s]:<11}{new:>5}{ex:>6}{t:>9.0%}{top:>8.0%}{book/1e9:>9.1f}{chg:>+8.0%}")
print()

# ---- conviction moves ----------------------------------------------------
conv = [r for r in rows if TIER[r["investor_slug"]]=="conviction" and not is_fund(r["issuer"])]
def line(r):
    d = f(r["share_delta_pct"])
    return (f"  {NAME[r['investor_slug']][:26]:<27}{r['issuer'][:34]:<35}"
            f"{w(r,'previous'):>6.1%} -> {w(r,'current'):>6.1%}"
            + (f"  shares {d:+.0%}" if d is not None and r['status']=='added' else ""))
new_big = sorted([r for r in conv if r["status"]=="new" and w(r,"current")>=0.01], key=lambda r:-w(r,"current"))
add_big = sorted([r for r in conv if r["status"]=="added" and (f(r["share_delta_pct"]) or 0)>=0.25 and w(r,"current")>=0.01], key=lambda r:-(w(r,"current")-w(r,"previous")))
exit_big = sorted([r for r in conv if r["status"]=="exited" and w(r,"previous")>=0.01], key=lambda r:-w(r,"previous"))
trim_big = sorted([r for r in conv if r["status"]=="reduced" and w(r,"previous")>=0.02 and (f(r["share_delta_pct"]) or 0)<=-0.4], key=lambda r:-(w(r,"previous")-w(r,"current")))
for title, lst in (("Conviction NEW positions >=1% of equity book", new_big), ("Conviction ADDS >=25% shares, now >=1%", add_big),
                   ("Conviction EXITS of positions that were >=1%", exit_big), ("Conviction TRIMS >=40% of a >=2% position", trim_big)):
    print(f"## {title}  ({len(lst)})\n")
    for r in lst[:25]: print(line(r))
    print()

# ---- consensus vs crowding ----------------------------------------------
buys = defaultdict(set); sells = defaultdict(set); pbuys = defaultdict(set)
for r in rows:
    if is_fund(r["issuer"]): continue
    key = r["issuer"].upper().split(" CL ")[0].split(" CLASS ")[0].strip()
    t = TIER[r["investor_slug"]]
    if r["status"] in ("new","added"):
        (buys if t=="conviction" else pbuys)[key].add(NAME[r["investor_slug"]])
    if r["status"] in ("exited","reduced") and t=="conviction" and w(r,"previous")>=0.005:
        sells[key].add(NAME[r["investor_slug"]])
print("## Names bought by 2+ conviction managers\n")
for k,v in sorted(buys.items(), key=lambda kv:-len(kv[1])):
    if len(v)>=2: print(f"  {k[:38]:<39}{len(v)}  {', '.join(sorted(v))}" + (f"   | sold by: {', '.join(sorted(sells[k]))}" if sells.get(k) else ""))
print()
print("## Names conviction managers were net sellers of (2+ sellers)\n")
for k,v in sorted(sells.items(), key=lambda kv:-len(kv[1])):
    if len(v)>=2: print(f"  {k[:38]:<39}{len(v)}  {', '.join(sorted(v))}")
print()
print("## Platform/macro crowding: most-bought names (context, not conviction)\n")
for k,v in sorted(pbuys.items(), key=lambda kv:-len(kv[1]))[:12]:
    print(f"  {k[:38]:<39}{len(v)}")

# ---- data quality --------------------------------------------------------
print("\n## Data checks\n")
from statistics import median
prices = defaultdict(list)
for r in rows:
    v, s = f(r["current_value_usd"]), f(r["current_shares"])
    if v and s and r["status"] != "exited": prices[r["cusip"]].append((v/s, r))
odd = []
for cusip, lst in prices.items():
    if len(lst) < 3: continue
    m = median(p for p,_ in lst)
    for p, r in lst:
        if m and (p/m > 3 or p/m < 1/3): odd.append((r["issuer"], NAME[r["investor_slug"]], p, m))
print(f"  Implied-price outliers (>3x off the cross-holder median, a value-scale red flag): {len(odd)}")
for o in odd[:10]: print(f"    {o[0][:30]:<31}{o[1][:26]:<27} ${o[2]:,.2f} vs median ${o[3]:,.2f}")
stale = [(NAME[s], latest[s][0]) for s in latest if latest[s][0] < sorted(dates)[-2 if len(dates)>1 else -1]]
print(f"  Managers with no filing for the prior quarter either (data gap, not just late): {stale or 'none'}")
