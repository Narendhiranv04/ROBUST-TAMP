# Supplementary material (draft)

Anonymous supplementary material for the AAMAS 2027 submission "Deciding If, When, and Where to
Replan for Robust Manipulation" (submission 2220).

```
supplementary/
  README.md               this file
  supplementary_latex/    the supplementary document (technical appendix)
    supplementary.tex       main file (aamas class, anonymous mode, S-numbering)
    supplementary.pdf       compiled output (7 pages)
    aamas.cls, by.pdf       conference class and licence logo (unchanged copies from the paper source)
    style/                  the paper's preamble (packages.tex, commands.tex)
    sections/               contents (S1), tasks_and_variants (S2), implementation (S3),
                            prompts_and_icl (S4), baseline_implementations (S5),
                            experimental_configuration (S6)
    figures/                empty
  videos/                 intentionally empty (videos will be added later)
  code/                   intentionally empty (the implementation will be added later)
```



## Document structure

| Section | Pages | Contents |
|---|---|---|
| S1 Overview | 1 | what the supplement provides |
| S2 Task Details | 1 | goal instructions, goal evaluation, placement areas, Table S1 (hidden contents and reference decisions), trial randomization |
| S3 Implementation Details | 1-3 | perception and memory (Eq. S1), IF trigger (Eq. S2), WHEN eligibility and dependency propagation (Eq. S3), WHERE insertion (Eq. S4), validation and recovery, termination, simulation controllers, real-robot setup |
| S4 Prompts and In-Context Examples | 4, 5, 6 | exactly three single-column pages: shared prompt without ICL; the three in-context examples; a recorded discovery correction and a recorded rejection with feedback |
| S5 Baseline Details | 7 | adaptations and limitations that affect the comparison; ICL differences |
| S6 Experimental Configuration | 7 | Table S2 (inference settings), trial protocol, ablations |

Page 3 is only partly filled: S4 starts on a new page by design (single-column pages with a clear boundary).

## Compiling

From `supplementary_latex/`:

```sh
latexmk -pdf -interaction=nonstopmode -halt-on-error supplementary.tex
latexmk -c          # remove auxiliary files, keep supplementary.pdf
```

Use `TZ=UTC latexmk ...` for a local build so the machine's timezone does not enter the PDF metadata.

Overleaf: upload the contents of `supplementary_latex/`, set `supplementary.tex` as the main document,
compiler pdfLaTeX. The folder is self-contained; there is no bibliography (the baselines are cited in the
main paper) and nothing is generated at build time.

## Unresolved items

- **Real-robot details (S3.4):** only the setup stated in the main paper is given (xArm, three D435
  cameras, SAM2.1 masks, region association into the shared memory, point-cloud grasp generation). A red
  placeholder marks where the five settings, region definitions, perception/grasping pipeline and trials
  are to be added.
- **Server settings (Table S2, marked \*):** context length 32,768, GPU-memory utilization 0.90 and the
  reasoning parser / image limit come from the server command recorded for the ICL runs. The zero-shot runs
  used the same model and sampling (logged requests), but their server command was not recorded.
- **Rejected correction in S4.3:** for the G1-n1 example only the rejected anchor (`after a5`) was
  recorded, not the full rejected answer; the panel shows only that fragment.
- **Recorded corrective outputs in S4.3** are the block fields parsed from the model's answers (the trial
  logs keep parsed blocks, not the raw text of corrective answers); the panels say so.
- **Not covered in the document:** the run records of six planner-comparison rows of the main paper's Table 2
  (Qwen3-VL-4B zero-shot, the four 4B/32B ICL rows, InternVL3.5-8B and Qwen2.5-7B-Instruct reruns) were not
  available when this supplement was prepared; the supplement makes no claim about them.
- **Paper preamble:** the paper's `packages.tex` loads `algpseudocode` twice with different options (an
  option clash that stops a strict `-halt-on-error` build). The supplement's copy passes the option before
  the first load; the paper itself was not changed.

## Checks performed

- Compiled with the command above (TeX Live 2026, pdfTeX): no errors, no undefined references, no
  overfull boxes, one underfull line. Not checked on Overleaf itself.
- Every page rendered and inspected: S4 occupies exactly pages 4-6, panels are aligned and kept together,
  long lines wrap inside panels, no clipped text; tables S1 and S2 fit their columns.
- Searched all sources (text, prompt panels, tables, captions) for file paths, source file names,
  identifiers, command-line flags, commit hashes, ZIP/package language and citations: none remain.
- Anonymity: sources, comments and PDF text scanned for author names, affiliation, user/machine names,
  server addresses, absolute paths, personal URLs and tokens: no hits. PDF metadata: empty author, XMP
  creator "Anonymous Author(s)", dates in UTC. Title and submission ID kept.
- Prompt panels are copied from the recorded prompts and trial logs of one evaluated ICL run; condensed
  panels are labelled "summary", shortened ones "excerpt". The shared system prompt shown in S4.1 is the
  text both conditions share (the ICL examples appended in that trial are omitted and the panel says so).

