# LaTeX paper

The distributed PDF is compiled by **XeLaTeX**, with `latexmk` managing BibTeX and cross-reference passes. ReportLab is not used to lay out or render the paper.

## Source layout

- `main.tex`: document class, typography, geometry, front matter and native LaTeX document assembly.
- `figures/headline.tex`: vector PGFPlots figure, reading the generated score macros and repetition data.
- `equations.tex`: numbered mathematical definitions of the reported metrics.
- `references.bib`: bibliographic records verified against the papers' arXiv pages.
- `benchmark.md`: shared narrative source, retained so the repository specification and website use the same prose.
- `generated/`: complete, tracked TeX body, abstract, booktabs tables, score macros and chart data. These are generated, not manually maintained.

The build generates native `\section`, `\caption`, `\label`, `\ref`, `\citep`, `tabularx` and PGFPlots content. LaTeX controls line breaking, hyphenation, pagination, floats, citations and equations; the old coordinate-drawing renderer is no longer used. Do not edit generated files without updating their source.

## Build from the repository root

Install the Python requirements plus **Pandoc**, **XeLaTeX**, **latexmk**, and the standard LaTeX packages used by `main.tex`.

On Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install pandoc latexmk texlive-xetex \
  texlive-latex-extra texlive-fonts-recommended texlive-pictures
python docs/build_latex.py
```

On macOS, MacTeX supplies the TeX toolchain; install Pandoc separately. A normal full TeX Live installation works on other supported platforms. No shell-escape option is required by the document.

The canonical output is `docs/business-harness-bench-spec.pdf`. Compilation logs, bibliography intermediates and the working PDF stay under ignored `tmp/latex/`.

To regenerate TeX/data only:

```bash
python docs/build_latex.py --generate-only
```

The checked-in TeX source can also be compiled directly without Pandoc or Python:

```bash
cd paper
latexmk -xelatex -interaction=nonstopmode -halt-on-error \
  -outdir=../tmp/latex main.tex
```

Create the output directory first when using the direct command. All body fonts are supplied under their SIL Open Font License in `docs/assets/fonts/`; mathematical and monospaced fonts come from TeX Live. Headline values and tables are generated from the verified frozen-score snapshot, not manually typed into the figure.
