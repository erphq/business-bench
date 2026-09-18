# Grader helper: recalculate any XLSX with LibreOffice so live formulas from every
# harness are evaluated by a real spreadsheet engine, not a Python approximation.
FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-calc-nogui fonts-dejavu-core ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /x && chmod 777 /x
WORKDIR /x
# usage: docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v <dir>:/x bench-recalc soffice --headless --calc --convert-to xlsx --outdir /x/out /x/in.xlsx
