"""Emit audit/content/power/gap-ledger.md from the 138 committed records.

Every line is derived from audit/records/power/*.json -- nothing is hand-entered,
so re-running this after a record changes regenerates a correct ledger.

  py audit/tools/gap_ledger.py
"""
import json, re, collections, pathlib

# audit/tools/gap_ledger.py -> parents[0]=audit/tools, [1]=audit, [2]=repo root.
# Anchored so the ledger reads the same records wherever it is run from.
_REPO = pathlib.Path(__file__).resolve().parents[2]

RECS = {}
for p in sorted((_REPO / 'audit' / 'records' / 'power').glob('*.json')):
    r = json.loads(p.read_text(encoding='utf-8'))
    RECS[r['unit'].split('/')[1]] = r


def entries(rec):
    """(kind, name, verdict, text) for every hook and guard."""
    for name, h in rec.get('hooks', {}).items():
        yield ('hook', name, h['verdict'], h.get('issue') or h.get('rationale') or '')
    for g in rec.get('guards', []):
        yield ('guard', g['what'], g['verdict'], g.get('issue') or g.get('rationale') or '')


def classify(text):
    """LIVE / DORMANT / UNCLASSIFIED, by which marker the auditor wrote first."""
    t = text.upper()
    live = min([m.start() for m in re.finditer(r'\bLIVE\b', t)] or [10 ** 9])
    dorm = min([m.start() for m in re.finditer(r'\bDORMANT\b', t)] or [10 ** 9])
    if live == dorm == 10 ** 9:
        return 'UNCLASSIFIED'
    return 'LIVE' if live < dorm else 'DORMANT'


def first_sentences(text, budget=420):
    """Enough of the issue text to be useful without reproducing the record."""
    if len(text) <= budget:
        return text
    cut = text[:budget]
    stop = max(cut.rfind('. '), cut.rfind('; '))
    return (cut[:stop + 1] if stop > budget // 2 else cut.rstrip()) + ' […]'


gaps = []  # (unit, kind, name, status, text)
for unit, rec in RECS.items():
    for kind, name, verdict, text in entries(rec):
        if verdict == 'gap':
            gaps.append((unit, kind, name, classify(text), text))

by_status = collections.Counter(g[3] for g in gaps)
units_with_gaps = len({g[0] for g in gaps})
all_entries = sum(1 for r in RECS.values() for _ in entries(r))
verdicts = collections.Counter(v for r in RECS.values() for _, _, v, _ in entries(r))
rollups = collections.Counter(r['verdict'] for r in RECS.values())

L = []
w = L.append
w('# Power tier — gap ledger')
w('')
w('Every `gap`-verdict entry in the 138 committed power audit records, in one')
w('place. **Generated from `audit/records/power/*.json`, not hand-written** — each line')
w("traces to a record, and the record carries the full reasoning and the file:line")
w('citations. Regenerate after any record changes rather than editing this file.')
w('')
w('Companion documents: `.superpowers/sdd/content-power-report.md` (the stream')
w('report — cross-cutting analysis, census results, cost data),')
w('`content-power-report-a.md` (41 player-side units) and')
w('`content-power-report-b.md` (48 enemy units) for the per-unit evidence.')
w('')
w('## Counts')
w('')
w('| | |')
w('|---|---|')
w(f'| units audited | {len(RECS)} |')
w(f'| unit rollups | ' + ', '.join(f'{n} {k}' for k, n in rollups.most_common()) + ' |')
w(f'| entries (hooks + guards) | {all_entries} — '
  + ', '.join(f'{n} {k}' for k, n in verdicts.most_common()) + ' |')
w(f'| **gap entries** | **{len(gaps)}**, across {units_with_gaps} units |')
w('| of which LIVE | **' + str(by_status['LIVE']) + '** |')
w('| of which DORMANT | ' + str(by_status['DORMANT']) + ' |')
w('| unclassified | ' + str(by_status['UNCLASSIFIED']) + ' |')
w('')
w('LIVE / DORMANT is read from the auditor\'s own wording in each entry (whichever')
w('marker appears first). An entry counted DORMANT names a trigger — the thing')
w('that would make it observable. **`waiver` entries are NOT in this file**: per')
w('binding rule 1 a waiver means genuinely out of scope, whereas "nothing ported')
w('triggers this" is a dormant gap and is included below.')
w('')
w('### Three caveats on these numbers, so they are not over-read')
w('')
w('1. **An entry is not a distinct bug.** Binding rule 3 gives one mechanism one')
w('   verdict at every site, so a mechanism shared by sibling units is recorded')
w('   once per unit. The eight `TemporaryStrength`/`TemporaryDexterity` units all')
w('   carry the same `AfterSideTurnEnd` slot gap, for instance — eight entries,')
w('   one defect, one one-line fix. The count of *distinct* live mechanisms is')
w('   roughly 28; they are enumerated in the stream report\'s sections 0 and 4,')
w('   which is the right place to plan fixes from. Use this file to find every')
w('   site a mechanism touches.')
w('2. **The unclassified bucket UNDER-reports live gaps** — it is a labelling')
w('   artifact, not a severity judgement. Those entries simply never write the')
w('   word LIVE or DORMANT. Several are known-live from the stream report; the')
w('   wrong-RNG-stream class is the clearest case, where `aggression`\'s entry')
w('   describes `combat._rng.sample` against C#\'s')
w('   `UnstableShuffle(Rng.CombatCardSelection)` and is live per report section 0')
w('   item 4, yet lands here unclassified. **Treat the report, not this bucket, as')
w('   authoritative on severity.** Classifying these entry by entry is outstanding')
w('   work.')
w('3. **Two of these findings would change a committed seam record**')
w('   (`turn_structure` G8 and `power_cmd` G6 flipping to live) and rest on')
w('   witnesses executed by continuation sessions rather than re-derived. Re-run')
w('   those before amending the seam docs.')
w('')
w('## How to read a dormant gap')
w('')
w('Dormant does not mean harmless. It means no *currently ported* content reaches')
w('the divergent path. Every dormant entry below is a latent bug that activates')
w('the moment its trigger is ported — which is why they are recorded as gaps')
w('rather than waived. When porting new content, grep this file for the mechanism')
w('first.')
w('')

# ------------------------------------------------------------------ live first
w('## LIVE gaps')
w('')
w('These diverge from the game on content that is already ported. Ordered by')
w('unit. Full text, because these are the actionable ones.')
w('')
live = [g for g in gaps if g[3] == 'LIVE']
for unit, kind, name, _, text in sorted(live):
    w(f'### `{unit}` — {name}')
    w('')
    w(f'*({kind}; record: `audit/records/power/{unit}.json`)*')
    w('')
    w(text)
    w('')

# --------------------------------------------------------------- then the rest
w('## DORMANT gaps')
w('')
w('Trimmed to the opening of each entry; the record has the rest, including the')
w('named trigger. Ordered by unit.')
w('')
cur = None
for unit, kind, name, status, text in sorted(g for g in gaps if g[3] == 'DORMANT'):
    if unit != cur:
        cur = unit
        w(f'### `{unit}`')
        w('')
    w(f'- **{name}** *({kind})* — {first_sentences(text)}')
w('')

unc = [g for g in gaps if g[3] == 'UNCLASSIFIED']
if unc:
    w('## Unclassified gaps')
    w('')
    w('The entry does not state LIVE or DORMANT in those words. Listed separately')
    w('rather than assumed either way — settling them is outstanding work.')
    w('')
    cur = None
    for unit, kind, name, status, text in sorted(unc):
        if unit != cur:
            cur = unit
            w(f'### `{unit}`')
            w('')
        w(f'- **{name}** *({kind})* — {first_sentences(text)}')
    w('')

w('## Regenerating')
w('')
w('```')
w('py audit/tools/gap_ledger.py > audit/content/power/gap-ledger.md')
w('```')

dest = _REPO / 'audit/content/power/gap-ledger.md'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text('\n'.join(L) + '\n', encoding='utf-8')
print(f'wrote {dest} — {len(L)} lines, {len(gaps)} gap entries')
