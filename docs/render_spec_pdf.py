#!/usr/bin/env python3
"""Render the benchmark paper in a compact serif research-paper layout."""
import html, json, re, sys
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether, Flowable, Preformatted

ROOT=Path(__file__).resolve().parents[1]
for name, filename in [('Paper','Regular'),('Paper-Bold','Bold'),('Paper-Italic','Italic')]:
    pdfmetrics.registerFont(TTFont(name,str(ROOT/'docs/assets/fonts'/f'LibertinusSerif-{filename}.ttf')))
pdfmetrics.registerFontFamily('Paper',normal='Paper',bold='Paper-Bold',italic='Paper-Italic',boldItalic='Paper-Bold')
WIDTH=A4[0]-44*mm-12
INK=colors.HexColor('#152631'); ACCENT=colors.HexColor('#087E8B'); MUTED=colors.HexColor('#65717A'); WASH=colors.HexColor('#F2F5F6')
BODY=ParagraphStyle('body',fontName='Paper',fontSize=10.7,leading=13.4,spaceAfter=6,alignment=TA_JUSTIFY,allowWidows=0,allowOrphans=0)
H2=ParagraphStyle('heading',parent=BODY,fontName='Paper-Bold',fontSize=13.1,leading=16,spaceBefore=12,spaceAfter=6,keepWithNext=True,alignment=0)
H3=ParagraphStyle('subheading',parent=BODY,fontName='Paper-Bold',fontSize=10.8,leading=13.4,spaceBefore=8,spaceAfter=4,keepWithNext=True,alignment=0)
CAPTION=ParagraphStyle('caption',parent=BODY,fontSize=9.1,leading=11.6,spaceBefore=5,spaceAfter=8,alignment=0)
CELL=ParagraphStyle('cell',parent=BODY,fontSize=9.6,leading=11.6,spaceAfter=0,alignment=0)

def inline(s):
    s=html.escape(s)
    s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'`([^`]+)`',r'<font name="Courier" size="8.7">\1</font>',s)
    return s

class ResultsFigure(Flowable):
    def __init__(self): super().__init__(); self.width=WIDTH; self.height=155
    def draw(self):
        c=self.canv; panel=WIDTH*.49; right=WIDTH*.59
        c.setFont('Paper-Bold',10); c.setFillColor(INK)
        c.drawString(0,143,'A   Overall task success'); c.drawString(right,143,'B   Success by repetition')
        rows=json.loads((ROOT/'results/latest/summary.json').read_text())
        palette=[ACCENT,colors.HexColor('#8493A5')]
        for i,r in enumerate(rows):
            y=97-i*48; c.setFillColor(INK); c.setFont('Paper',8.8)
            c.drawString(0,y+21,'Proto + DeepSeek V4.1 Flash' if i==0 else 'Codex + GPT-5.6-sol')
            c.setFillColor(WASH); c.rect(0,y,panel,15,fill=1,stroke=0)
            c.setFillColor(palette[i]); c.rect(0,y,panel*r['pass_rate'],15,fill=1,stroke=0)
            c.setFont('Paper-Bold',10); c.drawRightString(panel,y+21,f"{r['pass_rate']:.1%}")
            c.setFillColor(MUTED); c.setFont('Paper',7.9)
            c.drawString(0,y-11,f"{r['passed']}/561 passes  ·  ${r['estimated_cost_sum_usd']:.2f} estimated cost")
        c.setFont('Paper',7.8); c.drawString(0,14,'Bar scale: 0-100%')
        plot_x=right+24; plot_w=WIDTH-plot_x-12; base=38; plot_h=76
        for value in (70,80,90,100):
            y=base+(value-70)/30*plot_h; c.setStrokeColor(colors.HexColor('#DFE6E9')); c.setLineWidth(.4); c.line(plot_x,y,plot_x+plot_w,y)
            c.setFillColor(MUTED); c.setFont('Paper',7.8); c.drawRightString(plot_x-6,y-2,str(value))
        for j,r in enumerate(rows):
            points=[(plot_x+i*plot_w/2,base+(r['by_repetition'][str(i+1)]/187*100-70)/30*plot_h) for i in range(3)]
            c.setStrokeColor(palette[j]); c.setLineWidth(1.25)
            for a,b in zip(points,points[1:]): c.line(*a,*b)
            for i,(x,y) in enumerate(points):
                c.setFillColor(palette[j]); c.circle(x,y,2.7,stroke=0,fill=1)
                c.setFont('Paper-Bold',7.8); c.drawCentredString(x,y+(8 if j==0 else -12),f"{r['by_repetition'][str(i+1)]/187*100:.1f}")
        c.setFillColor(MUTED); c.setFont('Paper',8)
        for i in range(3): c.drawCentredString(plot_x+i*plot_w/2,25,f'R{i+1}')
        c.drawString(right,8,'Percent; vertical scale 70-100%')

def furniture(c,doc):
    c.saveState(); w,h=A4; x=22*mm
    c.setStrokeColor(ACCENT if doc.page==1 else colors.HexColor('#C2CDD2'))
    c.setLineWidth(1.4 if doc.page==1 else .5); c.line(x,h-23*mm,w-x,h-23*mm)
    if doc.page==1:
        c.setFillColor(INK); c.setFont('Paper-Bold',11); c.drawString(x,h-18*mm,'ERP AI')
        c.setFont('Paper',9); c.setFillColor(MUTED); c.drawString(x+43,h-18*mm,'RESEARCH')
        c.drawRightString(w-x,h-18*mm,'Technical report · September 2026')
    else:
        c.setFillColor(MUTED); c.setFont('Paper',8.4); c.drawString(x,h-19*mm,'BUSINESS HARNESS BENCH')
        c.drawRightString(w-x,h-19*mm,'Evaluating agents on business deliverables')
    c.setStrokeColor(colors.HexColor('#C2CDD2')); c.setLineWidth(.4); c.line(x,17*mm,w-x,17*mm)
    c.setFillColor(MUTED); c.setFont('Paper',8); c.drawString(x,12*mm,'ERP AI  ·  Business Harness Bench')
    c.drawRightString(w-x,12*mm,str(doc.page)); c.restoreState()

def make_table(lines):
    cells=[[x.strip() for x in line.strip('|').split('|')] for line in lines]
    cells=[cells[0]]+cells[2:]
    cols=len(cells[0]); widths=([WIDTH*.39,WIDTH*.305,WIDTH*.305] if cols==3 else [WIDTH/cols]*cols)
    if cells[0][0]=='Category': widths=[WIDTH*.25,WIDTH*.10,WIDTH*.65]
    if cols==5: widths=[WIDTH*x for x in (.21,.08,.27,.27,.17)]
    if cells[0][0]=='Deliverable': widths=[WIDTH*.21,WIDTH*.38,WIDTH*.41]
    if cols==2: widths=[WIDTH*.27,WIDTH*.73]
    data=[[Paragraph('<b>'+inline(cell)+'</b>' if i==0 else inline(cell),CELL) for cell in row] for i,row in enumerate(cells)]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),.8,INK),('LINEBELOW',(0,0),(-1,0),.5,INK),
        ('LINEBELOW',(0,-1),(-1,-1),.8,INK),('BACKGROUND',(0,0),(-1,0),WASH),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    return t

def story(text):
    lines=text.splitlines(); result=[]; i=0
    while i<len(lines):
        line=lines[i].strip(); i+=1
        if not line: continue
        if line.startswith('# '):
            title=ParagraphStyle('title',parent=BODY,fontName='Paper-Bold',fontSize=25.5,leading=28.5,alignment=TA_CENTER,spaceAfter=12)
            result += [Spacer(1,4),Paragraph('Business Harness Bench',title),
                Paragraph('Evaluating Agents on Business Deliverables',ParagraphStyle('subtitle',parent=BODY,fontSize=16,leading=19,alignment=TA_CENTER,spaceAfter=13)),
                Paragraph('ERP AI',ParagraphStyle('byline',parent=BODY,alignment=TA_CENTER,fontName='Paper-Bold',fontSize=10.5,spaceAfter=5)),
                Paragraph('<link href="https://github.com/erphq/business-bench" color="#087E8B">Code, tasks and evaluation evidence</link>',ParagraphStyle('link',parent=BODY,alignment=TA_CENTER,fontSize=9.3,spaceAfter=14))]
        elif line=='## Abstract':
            parts=[]
            while i<len(lines) and not lines[i].startswith(('##','<!--')):
                if lines[i].strip(): parts.append(lines[i].strip())
                i+=1
            p=Paragraph('<b>Abstract.</b> '+inline(' '.join(parts)),ParagraphStyle('abstract',parent=BODY,fontSize=9.8,leading=12.2,spaceAfter=0))
            t=Table([[p]],colWidths=[WIDTH]); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),WASH),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12)]))
            result += [t,Spacer(1,10)]
        elif line=='<!-- headline-figure -->':
            result += [ResultsFigure(),Paragraph('<b>Figure 1.</b> Full desk comparison under the shared frozen scorer. <b>A:</b> aggregate success over 561 attempts per system, with captured-usage cost estimates. <b>B:</b> success in each complete 187-task repetition. Teal: Proto + DeepSeek; slate: Codex + Sol. Costs are estimates, not invoices.',CAPTION)]
        elif line=='<!-- pagebreak -->': result.append(PageBreak())
        elif line.startswith('### '): result.append(Paragraph(inline(line[4:]),H3))
        elif line.startswith('## '): result.append(Paragraph(inline(line[3:]),H2))
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
            s=' '.join(paragraph)
            style=CAPTION if s.startswith('**Table') else BODY
            if re.match(r'^\d+\. ',s):
                style=ParagraphStyle('reference',parent=BODY,fontSize=9.7,leading=12.1,alignment=0,leftIndent=12,firstLineIndent=-12,spaceAfter=5)
            result.append(Paragraph(inline(s),style))
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
