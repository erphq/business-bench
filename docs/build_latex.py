#!/usr/bin/env python3
"""Generate native TeX content from the shared manuscript and compile with XeLaTeX."""
import argparse
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / 'paper'
GENERATED = PAPER / 'generated'
BIB_KEYS = {1: 'workarena', 2: 'spreadsheetbench', 3: 'agentcompany', 4: 'enterpriseclawbench'}


def tex_escape(text):
    mapping = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
               '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(mapping.get(character, character) for character in text)


def inline(text):
    chunks = re.split(r'(\*\*.+?\*\*|`[^`]+`)', text)
    output = []
    for chunk in chunks:
        if chunk.startswith('**') and chunk.endswith('**'):
            output.append(r'\textbf{' + tex_escape(chunk[2:-2]) + '}')
        elif chunk.startswith('`') and chunk.endswith('`'):
            output.append(r'\texttt{' + tex_escape(chunk[1:-1]) + '}')
        else:
            output.append(tex_escape(chunk))
    return ''.join(output)


def native_table(match):
    block, number, caption = match.groups()
    rows = [[cell.strip() for cell in line.strip().strip('|').split('|')] for line in block.strip().splitlines()]
    rows = [rows[0]] + rows[2:]
    weights = [1] * len(rows[0])
    if len(weights) == 3:
        weights = [1.1, .95, .95]
    if rows[0][0] == 'Category' and len(weights) == 3:
        weights = [.75, .30, 1.95]
    elif len(weights) == 5:
        weights = [1.05, .35, 1.45, 1.45, .70]
    elif rows[0][0] == 'Deliverable':
        weights = [.62, 1.12, 1.26]
    elif len(weights) == 2:
        weights = [.54, 1.46]
    columns = ''.join(r'>{\hsize=' + str(weight) + r'\hsize\linewidth=\hsize\RaggedRight\arraybackslash}X' for weight in weights)
    body = [r'\begin{table}[!htbp]', r'\centering\small', r'\setlength{\tabcolsep}{4pt}',
            r'\begin{tabularx}{\linewidth}{@{}' + columns + r'@{}}', r'\toprule']
    for index, row in enumerate(rows):
        cells = [r'\textbf{' + inline(cell) + '}' if index == 0 else inline(cell) for cell in row]
        body.append(' & '.join(cells) + r' \\')
        if index == 0:
            body.append(r'\midrule')
    body.extend([r'\bottomrule', r'\end{tabularx}', r'\caption{' + inline(caption) + '}',
                 r'\label{tab:' + number + '}', r'\end{table}'])
    path = GENERATED / f'table-{number}.tex'
    path.write_text('\n'.join(body) + '\n')
    return '\n```{=latex}\n\\input{generated/table-' + number + '.tex}\n```\n'


@lru_cache(maxsize=8)
def pandoc(text):
    return subprocess.check_output(['pandoc', '--from=markdown+raw_tex', '--to=latex',
        '--wrap=none', '--no-highlight'], input=text, text=True)


def generate():
    from assemble_spec import main as assemble
    assemble()
    GENERATED.mkdir(exist_ok=True)
    source = (ROOT / 'SPEC.md').read_text()
    abstract = re.search(r'## Abstract\s*\n(.*?)\n<!-- headline-figure -->', source, re.S)
    if not abstract:
        raise ValueError('Abstract/figure boundary missing')
    (GENERATED / 'abstract.tex').write_text(pandoc(abstract.group(1).strip()))
    body = source[abstract.end():]
    body = re.sub(r'## References\n.*?(?=## Appendix A\.)',
        lambda _: '\n```{=latex}\n\\FloatBarrier\n\\bibliographystyle{unsrtnat}\n\\bibliography{references}\n\\clearpage\n\\appendix\n```\n\n', body, flags=re.S)
    body = body.replace('<!-- pagebreak -->', '')
    body = re.sub(r'(?m)(^\|[^\n]+\n(?:^\|[^\n]+\n)+)\n\*\*Table (\d+)\.\*\* ([^\n]+)', native_table, body)
    body = re.sub(r'(?m)^## (\d+)\. (.+)$', lambda m: '# ' + m[2] + ' {#sec:' + m[1] + '}', body)
    body = re.sub(r'(?m)^### \d+\.\d+ (.+)$', r'## \1', body)
    body = re.sub(r'(?m)^## Appendix ([AB])\. (.+)$', lambda m: '# ' + m[2] + ' {#app:' + m[1] + '}', body)
    body = re.sub(r'(?m)^### [AB]\.\d+ (.+)$', r'## \1', body)
    for number, key in BIB_KEYS.items():
        body = body.replace(f'[{number}]', r'\citep{' + key + '}')
    body = re.sub(r'Section (\d+)', lambda m: r'Section \ref{sec:' + m[1] + '}', body)
    body = re.sub(r'Figure (\d+)', lambda m: r'Figure \ref{fig:headline}' if m[1] == '1' else m[0], body)
    body = body.replace('# Conclusion {#sec:9}', '```{=latex}\n\\Needspace{7\\baselineskip}\n```\n\n# Conclusion {#sec:9}')
    body += '\n```{=latex}\n\\subsection{Formal definitions}\n\\input{equations.tex}\n```\n'
    (GENERATED / 'body.tex').write_text('% Generated from paper/benchmark.md and the verified ledger.\n' + pandoc(body))
    summary = json.loads((ROOT / 'results/latest/summary.json').read_text())
    proto, codex = summary
    macros = {'ProtoRate': f"{100*proto['pass_rate']:.1f}", 'CodexRate': f"{100*codex['pass_rate']:.1f}",
              'ProtoCost': f"{proto['estimated_cost_sum_usd']:.2f}", 'CodexCost': f"{codex['estimated_cost_sum_usd']:.2f}"}
    (GENERATED / 'metrics.tex').write_text('\n'.join('\\newcommand{\\' + name + '}{' + value + '}' for name, value in macros.items()) + '\n')
    rows = ['rep proto codex'] + [f"{i} {100*proto['by_repetition'][str(i)]/187:.8f} {100*codex['by_repetition'][str(i)]/187:.8f}" for i in (1,2,3)]
    (GENERATED / 'repetitions.dat').write_text('\n'.join(rows) + '\n')


def build(output):
    if not shutil.which('latexmk') or not shutil.which('xelatex'):
        raise SystemExit('Install TeX Live or MacTeX with XeLaTeX and latexmk; see paper/README.md')
    out = ROOT / 'tmp/latex'
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(['latexmk', '-xelatex', '-interaction=nonstopmode', '-halt-on-error',
        '-file-line-error', '-outdir=' + str(out), 'main.tex'], cwd=PAPER, check=True,
        env=dict(os.environ, LC_ALL='C', LANG='C'))
    log = (out / 'main.log').read_text(errors='replace')
    if 'There were undefined references' in log or re.search(r'Citation .+ undefined', log):
        raise SystemExit('Unresolved LaTeX reference/citation in final pass')
    if re.search(r'Overfull \\[hv]box', log):
        raise SystemExit('LaTeX overflow detected; inspect tmp/latex/main.log before publication')
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out / 'main.pdf', output)
    print('Compiled with XeLaTeX:', output)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--generate-only', action='store_true')
    ap.add_argument('--output', type=Path, default=ROOT / 'docs/business-harness-bench-spec.pdf')
    args = ap.parse_args()
    if not shutil.which('pandoc'):
        raise SystemExit('Install Pandoc to generate TeX from the shared Markdown manuscript')
    generate()
    if not args.generate_only:
        build(args.output.resolve())


if __name__ == '__main__':
    main()
