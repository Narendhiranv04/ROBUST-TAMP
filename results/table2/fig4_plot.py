"""Fig. 4: (a) zero-shot vs in-context examples across the Qwen3 family (Table 2a); (b) the
outcomes of the selected planner's 140 trials (Qwen3-VL-8B-Thinking, Table 4); (c) the kinds of
failure it met, where they were caught, and how often replanning still completed the task.

    python results/table2/fig4_plot.py      (reads fig4_data.json, fig4b_trials.json next to it)
"""
import json
import math
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Wedge

HERE = Path(__file__).resolve().parent
scale_rows = json.load(open(HERE / 'fig4_data.json'))
trials = json.load(open(HERE / 'fig4b_trials.json'))

INK, SOFT, MUTED, FAINT, BAND = '#1d1d1b', '#55544e', '#8f8e86', '#e6e5df', '#f3f2ee'
ZS_C, ICL_C, LINK = '#a9a89f', '#2a78d6', '#b9d3f3'          # zero-shot grey, ICL blue
DONE, FIXED, LOST = '#d9d8d1', '#2a78d6', '#eb6834'           # no failure / replanned and completed / not completed
plt.rcParams.update({'font.family': 'Fira Sans', 'font.size': 6.6, 'pdf.fonttype': 42, 'ps.fonttype': 42,
                     'axes.edgecolor': MUTED, 'axes.labelcolor': SOFT, 'xtick.color': MUTED, 'ytick.color': SOFT,
                     'axes.linewidth': 0.6, 'xtick.major.width': 0.6, 'xtick.major.size': 2.5, 'xtick.major.pad': 2})

fig = plt.figure(figsize=(3.45, 3.85))
outer = fig.add_gridspec(2, 1, height_ratios=[1.0, 0.95], hspace=0.40, left=0.0, right=1.0, top=0.93, bottom=0.10)
row2 = outer[1].subgridspec(1, 2, width_ratios=[0.78, 1.22], wspace=0.04)


def heading(ax, tag, text, x=0.0, gap=0.065):
    ax.text(x, 1.10, tag, transform=ax.transAxes, fontsize=8.5, fontweight='bold', color=INK, va='bottom')
    if text:
        ax.text(x + gap, 1.10, text, transform=ax.transAxes, fontsize=7.4, color=SOFT, va='bottom')


# ---- (a) zero-shot -> ICL, one row per model ---------------------------------------------------
axa = fig.add_subplot(outer[0])
models = [('4B', 'LLM', 'Qwen3-4B'), ('4B', 'VLM', 'Qwen3-VL-4B'), ('8B', 'LLM', 'Qwen3-8B'),
          ('8B', 'VLM', 'Qwen3-VL-8B'), ('32B', 'LLM', 'Qwen3-32B'), ('32B', 'VLM', 'Qwen3-VL-32B')]
ys = [0, 1, 2.35, 3.35, 4.7, 5.7]
for y, (scale, mod, name) in zip(ys, models):
    zs = next(r for r in scale_rows if (r['scale'], r['mod'], r['prompt']) == (scale, mod, 'ZS'))
    icl = next(r for r in scale_rows if (r['scale'], r['mod'], r['prompt']) == (scale, mod, 'ICL'))
    a, b = 100 * zs['SR'], 100 * icl['SR']
    selected = name == 'Qwen3-VL-8B'
    if selected:
        band_y = y
    axa.plot([a, b], [y, y], color=LINK, lw=2.8, solid_capstyle='round', zorder=1)
    axa.scatter(a, y, s=24, facecolor='white', edgecolor=ZS_C, linewidth=1.4, zorder=3)
    axa.scatter(b, y, s=30, facecolor=ICL_C, edgecolor='white', linewidth=0.7, zorder=4)
    axa.text(b + 3.2, y, f'+{b - a:.0f}', va='center', fontsize=6.4, color=ICL_C, fontweight='bold')
    label = axa.text(-3, y, name, ha='right', va='center', fontsize=6.6, color=INK if selected else SOFT,
                     fontweight='bold' if selected else 'normal')
    if selected:
        band_label = label
    axa.text(146, y, f"{zs['Plan_s']:.0f} → {icl['Plan_s']:.0f} s", ha='right', va='center', fontsize=6.0,
             color=MUTED)
axa.text(146, -0.95, 'planner time', ha='right', va='center', fontsize=5.8, color=MUTED, style='italic')
axa.set_xlim(-38, 146)
axa.set_ylim(6.35, -0.8)
for x in (0, 25, 50, 75, 100):
    axa.plot([x, x], [-0.6, 6.2], color=FAINT, lw=0.6, zorder=0)
axa.set_xticks([0, 25, 50, 75, 100])
axa.set_yticks([])
for side in ('left', 'right', 'top'):
    axa.spines[side].set_visible(False)
axa.spines['bottom'].set_bounds(0, 100)
axa.set_xlabel('Task success (%)', fontsize=6.4)
axa.xaxis.set_label_coords((50 + 38) / 184, -0.12)
axa.scatter([], [], s=30, facecolor='white', edgecolor=ZS_C, linewidth=1.5, label='zero-shot')
axa.scatter([], [], s=34, facecolor=ICL_C, edgecolor='white', label='with ICL')
axa.legend(loc='center left', ncol=2, frameon=False, fontsize=6.4, handletextpad=0.1, columnspacing=0.8,
           borderaxespad=0)

# ---- (b) the 140 trials --------------------------------------------------------------------------
axb = fig.add_subplot(row2[0, 0])
n_clean = sum(1 for t in trials if t['success'] and not t['failures'])
n_fixed = sum(1 for t in trials if t['success'] and t['failures'])
n_lost = sum(1 for t in trials if not t['success'])
total = len(trials)
start = 90.0
for n, color in ((n_fixed, FIXED), (n_clean, DONE), (n_lost, LOST)):
    sweep = 360.0 * n / total
    axb.add_patch(Wedge((0, 0), 1.0, start - sweep, start, width=0.30, facecolor=color, edgecolor='white', linewidth=1.2))
    mid = math.radians(start - sweep / 2)
    axb.text(0.85 * math.cos(mid), 0.85 * math.sin(mid), str(n), ha='center', va='center', fontsize=6.4,
             fontweight='bold', color='white' if color != DONE else INK)
    start -= sweep
axb.text(0, 0.10, f'{100 * (n_clean + n_fixed) / total:.0f}%', ha='center', va='center', fontsize=11, fontweight='bold',
         color=INK)
axb.text(0, -0.24, 'completed', ha='center', va='center', fontsize=6.0, color=SOFT)
axb.set_xlim(-1.08, 1.08)
axb.set_ylim(-1.08, 1.08)
axb.set_aspect('equal')
axb.axis('off')

# ---- (c) kinds of failure --------------------------------------------------------------------------
MODES = [
    ('PLAN CHECK', [
        ('Pick without place', ('orphan_place', 'missing_post_pick_place', 'pick_place_mismatch')),
        ('Inserted too late', ('insertion_too_late',)),
        ('Unreadable plan', ('invalid_corrective_block', 'unknown_action_token', 'planner_output_not_parseable')),
        ('Plan repeated', ('repeated_planner_output',)),
    ]),
    ('EXECUTION', [
        ('Place / grasp failed', ('placement_failed', 'grasp_failed', 'object_did_not_move')),
        ('Lid blocked / closed', ('box_lid_obstructed', 'box_lid_closed')),
        ('No motion plan', ('pddl_no_plan', 'no_ik_solution', 'executor_failure')),
    ]),
]
fixed, lost = Counter(), Counter()
for t in trials:
    for code, _stage in t['failures']:
        (fixed if t['success'] else lost)[code] += 1
known = {c for _, ms in MODES for _, cs in ms for c in cs}
assert set(fixed) | set(lost) <= known, (set(fixed) | set(lost)) - known
axc = fig.add_subplot(row2[0, 1])
y = 0.0
LW = 4.6
for group, modes in MODES:
    axc.text(-2, y - 0.05, group, ha='right', va='center', fontsize=5.4, color=MUTED, fontweight='bold')
    y += 0.95
    for label, codes in modes:
        f, l = sum(fixed[c] for c in codes), sum(lost[c] for c in codes)
        axc.plot([0.9, f + l - 0.9], [y, y], color=LOST, lw=LW, solid_capstyle='round', zorder=2)
        if f:
            axc.plot([0.9, max(f - 0.9, 0.9)], [y, y], color=FIXED, lw=LW, solid_capstyle='round', zorder=3)
        axc.text(f + l + 2.0, y, str(f + l), va='center', fontsize=6.0, color=SOFT)
        axc.text(-3, y, label, ha='right', va='center', fontsize=6.2, color=SOFT)
        y += 0.95
    y += 0.25
axc.set_xlim(-50, 84)
axc.set_ylim(y - 0.4, -0.55)
axc.axis('off')

# one legend for (b) and (c)
fig.legend(handles=[Patch(color=DONE, label='no failure'), Patch(color=FIXED, label='replanned, task completed'),
                    Patch(color=LOST, label='task not completed')],
           loc='lower center', bbox_to_anchor=(0.5, 0.0), ncol=3, frameon=False, fontsize=6.0, handlelength=0.9,
           handleheight=0.9, handletextpad=0.35, columnspacing=0.9)
# panel headings on one line
fig.canvas.draw()
# the selected model's band, from its label's left edge to the planner-time column
from matplotlib.patches import Rectangle
from matplotlib.transforms import blended_transform_factory
lx0 = axa.transAxes.inverted().transform(band_label.get_window_extent())[0][0]
axa.add_patch(Rectangle((lx0 - 0.015, band_y - 0.46), 1.0 - lx0 + 0.015, 0.92, facecolor=BAND, edgecolor='none',
                        transform=blended_transform_factory(axa.transAxes, axa.transData), clip_on=False, zorder=0))
A_HEAD = 0.985
ROW2_HEAD = axb.get_position().y1 + 0.035
for ax, y_head, tag, text in ((axa, A_HEAD, '(a)', None), (axb, ROW2_HEAD, '(b)', f'{total} trials'),
                              (axc, ROW2_HEAD, '(c)', f'{sum(fixed.values()) + sum(lost.values())} failures caught')):
    x0 = 0.0 if ax is not axc else ax.get_position().x0 + 0.02
    fig.text(x0, y_head, tag, fontsize=7.6, fontweight='bold', color=INK, va='center')
    if text:
        fig.text(x0 + 0.06, y_head, text, fontsize=6.4, color=SOFT, va='center')
axa.get_legend().set_bbox_to_anchor((0.06, A_HEAD), transform=fig.transFigure)
for ext in ('pdf', 'png'):
    fig.savefig(HERE / f'fig4_scale_failures.{ext}', dpi=300, bbox_inches='tight', pad_inches=0.02)
print('ok', n_clean, n_fixed, n_lost, sum(fixed.values()), sum(lost.values()))
