#!/usr/bin/env python3
"""Aggregate the compact trial-level results (results/trial_level/*.csv) per label.

    python summarize_trial_results.py results/trial_level/main_results.csv
    python summarize_trial_results.py results/trial_level/baselines.csv --combine vlm_tamp_zero_shot:vlm_tamp_icl_grill

SR and PGC (%) for the kitchen (K), grill (G) and all trials, mean planner calls, planner time and
trial time per trial. ``--combine ZS:ICL`` reports an ICL row as the paper does: the kitchen trials of
the zero-shot label (kitchen prompts are identical with and without ICL) with the grill trials of the
ICL label. Median per-call latency and idle time need the full trial logs and are not in these CSVs.
"""
import argparse
import collections
import csv


def stats(rows):
    k = [r for r in rows if r['variant'].startswith('FINAL.K')]
    g = [r for r in rows if r['variant'].startswith('FINAL.G')]
    sr = lambda t: 100 * sum(int(r['success']) for r in t) / len(t) if t else float('nan')
    pgc = lambda t: 100 * sum(float(r['pgc']) for r in t) / len(t) if t else float('nan')
    mean = lambda key: sum(float(r[key] or 0) for r in rows) / len(rows)
    return (f'n={len(rows):3d}  SR K {sr(k):5.1f} G {sr(g):5.1f} All {sr(rows):5.1f}  '
            f'PGC K {pgc(k):5.1f} G {pgc(g):5.1f} All {pgc(rows):5.1f}  '
            f'Calls {mean("planner_calls"):4.1f}  Plan {mean("planner_time_s"):5.0f}  Time {mean("trial_time_s"):5.0f}')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('csv', nargs='+')
    parser.add_argument('--combine', action='append', default=[], metavar='ZS_LABEL:ICL_LABEL')
    parser.add_argument('--variants', nargs='*', help='restrict to these variant ids (e.g. FINAL.K1 FINAL.K2)')
    args = parser.parse_args()
    by = collections.defaultdict(list)
    for path in args.csv:
        for row in csv.DictReader(open(path, encoding='utf-8')):
            if not args.variants or row['variant'] in args.variants:
                by[row['label']].append(row)
    for label, rows in by.items():
        print(f'{label:42s} {stats(rows)}')
    for pair in args.combine:
        zs, icl = pair.split(':')
        rows = [r for r in by[zs] if r['variant'].startswith('FINAL.K')] + \
               [r for r in by[icl] if r['variant'].startswith('FINAL.G')]
        print(f'{zs + " + " + icl + " (grill)":42s} {stats(rows)}')


if __name__ == '__main__':
    main()
