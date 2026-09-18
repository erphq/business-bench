#!/usr/bin/env python3
"""Render the benchmark paper in a compact serif research-paper layout."""
import html, json, re, sys
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether, Flowable, Preformatted

ROOT=Path(__file__).resolve().parents[1]
WIDTH=A4[0]-44*mm
INK=colors.HexColor('#17212B'); ACCENT=colors.HexColor('#078C9F'); MUTED=colors.HexColor('#586570'); WASH=colors.HexColor('#F0F3F5')
BODY=ParagraphStyle('body',fontName='Times-Roman',fontSize=10.7,leading=14.1,spaceAfter=7,alignment=TA_JUSTIFY,allowWidows=0,allowOrphans=0)
H2=ParagraphStyle('heading',parent=BODY,fontName='Times-Bold',fontSize=13.2,leading=16,spaceBefore=11,spaceAfter=7,keepWithNext=True,alignment=0)
H3=ParagraphStyle('subheading',parent=BODY,fontName='Times-Bold',fontSize=11.1,leading=14,spaceBefore=8,spaceAfter=4,keepWithNext=True,alignment=0)
CAPTION=ParagraphStyle('caption',parent=BODY,fontSize=9.3,leading=12,spaceBefore=5,spaceAfter=9,alignment=0)
CELL=ParagraphStyle('cell',parent=BODY,fontSize=9.4,leading=12,spaceAfter=0,alignment=0)

def inline(s):
    s=html.escape(s)
    s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'`([^`]+)`',r'<font name="Courier" size="8.7">\1</font>',s)
    return s

class ResultsFigure(Flowable):
    def __init__(self): super().__init__(); self.width=WIDTH; self.height=128
    def draw(self):
        c=self.canv; left=143; plot=WIDTH-left-41; top=94
        c.setFont('Times-Bold',10.5); c.setFillColor(INK); c.drawString(0,116,'Full desk evaluation: 187 tasks × 3 attempts per system')
        for t in (0,25,50,75,100):
            x=left+plot*t/100; c.setStrokeColor(colors.HexColor('#DCE2E5')); c.setLineWidth(.4); c.line(x,34,x,top+5)
            c.setFont('Helvetica',7); c.setFillColor(MUTED); c.drawCentredString(x,23,str(t))
        rows=json.loads((ROOT/'results/latest/summary.json').read_text())
        for i,r in enumerate(rows):
            y=top-22-i*35; color=ACCENT if i==0 else colors.HexColor('#6E8094')
            c.setFillColor(INK); c.setFont('Times-Bold',10); c.drawString(0,y+10,'Proto + DeepSeek V4.1 Flash' if i==0 else 'Codex + GPT-5.6-sol')
            c.setFont('Times-Roman',8.2); c.setFillColor(MUTED)
            c.drawString(0,y-2,f"{r['passed']}/561 passes; ${r['estimated_cost_sum_usd']:.2f} estimated")
            c.setFillColor(color); c.rect(left,y,plot*r['pass_rate'],19,fill=1,stroke=0)
            c.setFont('Times-Bold',11); c.drawString(left+plot*r['pass_rate']+5,y+5,f"{r['pass_rate']:.1%}")
        c.setFont('Times-Roman',8.5); c.setFillColor(MUTED); c.drawCentredString(left+plot/2,7,'Frozen-scorer pass rate (%)  ·  zero-based scale')

def furniture(c,doc):
    c.saveState(); w,h=A4; x=22*mm
    c.setStrokeColor(ACCENT if doc.page==1 else colors.HexColor('#C2CDD2'))
    c.setLineWidth(1.4 if doc.page==1 else .5); c.line(x,h-23*mm,w-x,h-23*mm)
    if doc.page==1:
        c.setFillColor(INK); c.setFont('Helvetica-Bold',12); c.drawString(x,h-18*mm,'ERP · AI  /  RESEARCH')
        c.setFont('Times-Roman',9); c.drawRightString(w-x,h-18*mm,'18 September 2026')
    else:
        c.setFillColor(MUTED); c.setFont('Times-Roman',9); c.drawCentredString(w/2,h-19*mm,'Business Harness Bench: Evaluating Agents on Business Deliverables')
    c.setStrokeColor(colors.HexColor('#C2CDD2')); c.setLineWidth(.4); c.line(x,17*mm,w-x,17*mm)
    c.setFillColor(MUTED); c.setFont('Times-Roman',8); c.drawString(x,12*mm,'ERP AI  |  Technical report  |  Full desk comparison')
    c.drawRightString(w-x,12*mm,str(doc.page)); c.restoreState()

def make_table(lines):
    cells=[[x.strip() for x in line.strip('|').split('|')] for line in lines]
    cells=[cells[0]]+cells[2:]
    cols=len(cells[0]); widths=([WIDTH*.39,WIDTH*.305,WIDTH*.305] if cols==3 else [WIDTH/cols]*cols)
    data=[[Paragraph(inline(cell),CELL) for cell in row] for row in cells]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),.8,INK),('LINEBELOW',(0,0),(-1,0),.5,INK),
        ('LINEBELOW',(0,-1),(-1,-1),.8,INK),('BACKGROUND',(0,0),(-1,0),WASH),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    return t

def story(text):
    lines=text.splitlines(); result=[]; i=0
    while i<len(lines):
        line=lines[i].strip(); i+=1
        if not line: continue
        if line.startswith('# '):
            title=ParagraphStyle('title',parent=BODY,fontName='Times-Bold',fontSize=23,leading=26,alignment=TA_CENTER,spaceAfter=13)
            result += [Spacer(1,8),Paragraph(inline(line[2:]),title),Paragraph('ERP AI<br/><font size="9">Benchmark and evaluation infrastructure</font>',ParagraphStyle('byline',parent=BODY,alignment=TA_CENTER,fontName='Times-Bold',spaceAfter=8)),
                Paragraph('<link href="https://github.com/erphq/business-bench" color="#078C9F">github.com/erphq/business-bench</link>',ParagraphStyle('link',parent=BODY,alignment=TA_CENTER,fontSize=9.5,spaceAfter=12))]
        elif line=='## Abstract':
            parts=[]
            while i<len(lines) and not lines[i].startswith(('##','<!--')):
                if lines[i].strip(): parts.append(lines[i].strip())
                i+=1
            p=Paragraph('<b>Abstract</b> <font color="#078C9F">|</font> '+inline(' '.join(parts)),ParagraphStyle('abstract',parent=BODY,fontSize=10,leading=13.2,spaceAfter=0))
            t=Table([[p]],colWidths=[WIDTH]); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),WASH),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12)]))
            result += [t,Spacer(1,10)]
        elif line=='<!-- headline-figure -->':
            result += [ResultsFigure(),Paragraph('<b>Figure 1</b> <font color="#078C9F">|</font> Complete desk comparison under one frozen scorer. All 1,122 attempts are retained. Cost annotations are captured-usage API-equivalent estimates, not billed charges.',CAPTION)]
        elif line=='<!-- pagebreak -->': result.append(Spacer(1,5))
        elif line.startswith('### '): result.append(Paragraph(inline(line[4:]),H3))
        elif line.startswith('## '): result.append(Paragraph('<font color="#078C9F">|</font> '+inline(line[3:]),H2))
        elif line.startswith('|'):
            table=[line]
            while i<len(lines) and lines[i].strip().startswith('|'): table.append(lines[i].strip()); i+=1
            result.append(KeepTogether([make_table(table)]))
        elif line.startswith('```'):
            code=[]
            while i<len(lines) and not lines[i].startswith('```'): code.append(lines[i]); i+=1
            i+=1; result.append(Preformatted('\n'.join(code),ParagraphStyle('code',fontName='Courier',fontSize=8.3,leading=11,spaceAfter=8)))
        else:
            paragraph=[line]
            while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','<!--','```')):
                paragraph.append(lines[i].strip()); i+=1
            s=' '.join(paragraph); result.append(Paragraph(inline(s),CAPTION if s.startswith('**Table') else BODY))
    return result

def main():
    src=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'SPEC.md'
    out=Path(sys.argv[2]) if len(sys.argv)>2 else ROOT/'docs/business-harness-bench-spec.pdf'
    doc=SimpleDocTemplate(str(out),pagesize=A4,leftMargin=22*mm,rightMargin=22*mm,topMargin=28*mm,bottomMargin=22*mm,
        title='Business Harness Bench: Evaluating Agents on Business Deliverables',author='ERP AI')
    doc.build(story(src.read_text()),onFirstPage=furniture,onLaterPages=furniture)
    from pypdf import PdfReader
    print(f'Wrote {out}: {len(PdfReader(out).pages)} pages')

if __name__=='__main__': main()
