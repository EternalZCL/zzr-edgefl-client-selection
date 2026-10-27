"""Export the verified Markdown report to a typeset Chinese PDF with embedded fonts."""
import html
import json
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle, KeepTogether

out = Path(sys.argv[1]).resolve()
font_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("C:/Windows/Fonts/simhei.ttf")
pdfmetrics.registerFont(TTFont("Chinese", str(font_path)))
pdfmetrics.registerFontFamily("Chinese", normal="Chinese", bold="Chinese", italic="Chinese", boldItalic="Chinese")
ink = colors.HexColor("#173342")
teal = colors.HexColor("#007f89")
grey = colors.HexColor("#526676")
body = ParagraphStyle("Body", fontName="Chinese", fontSize=10, leading=17, textColor=ink,
                      spaceAfter=9, wordWrap="CJK", splitLongWords=True, allowWidows=0, allowOrphans=0)
heading = ParagraphStyle("Heading", parent=body, fontSize=14, leading=21, textColor=teal,
                         spaceBefore=15, spaceAfter=9, keepWithNext=True)
small = ParagraphStyle("Small", parent=body, fontSize=8, leading=12, textColor=grey)
caption = ParagraphStyle("Caption", parent=small, fontSize=9, leading=14, spaceAfter=12)
cell = ParagraphStyle("Cell", parent=body, fontSize=7.4, leading=11, spaceAfter=0)
width, height = A4
margin = 18 * mm
available = width - 2 * margin
results = json.loads((out / "results.json").read_text(encoding="utf-8"))


def clean(text):
    return html.escape(text.replace("`", "").replace("\u2013", "-").replace("\u2014", "-").replace("\u2011", "-"))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d7e1e5"))
    canvas.line(margin, 15 * mm, width-margin, 15 * mm)
    canvas.setFont("Chinese", 8)
    canvas.setFillColor(grey)
    canvas.drawString(margin, 10 * mm, "EdgeFL | ghj | 可复现实验报告 | 2026-10-27")
    canvas.drawRightString(width-margin, 10 * mm, str(doc.page))
    if doc.page > 1:
        canvas.setFont("Chinese", 7)
        canvas.drawString(margin, height-10*mm, "固定模拟时间预算下的联邦客户端选择")
    canvas.restoreState()


story = []
cover_title = ParagraphStyle("Cover", parent=body, fontSize=27, leading=39, spaceAfter=24)
cover_sub = ParagraphStyle("CoverSub", parent=body, fontSize=14, leading=23, textColor=teal, spaceAfter=20)
story += [Spacer(1, 20*mm), Paragraph("面向异构云边感知的<br/>联邦客户端选择", cover_title),
          Paragraph("ghj 可复现实验与课程研究报告", cover_sub), Spacer(1, 10*mm)]
summary = results["primary_preregistered_comparison"]
lines = ["正式矩阵：175 / 175 次已完成", "数据：UCI HAPT，30 位用户，六类动作",
         f"预算：B = {results['config']['evaluation']['budget_sim_seconds']:.6f} 模拟秒",
         "正式种子：101 / 102 / 103 / 104 / 105",
         f"主比较配对差：{summary['mean']:+.6f} Macro-F1",
         "作者工作区：ghj；实验顺序执行；未自动晋级 Champion"]
cover_table = Table([[Paragraph(clean(line), body)] for line in lines], colWidths=[available], hAlign="LEFT")
cover_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#eef5f5")),
                                ("LEFTPADDING", (0,0), (-1,-1), 14), ("RIGHTPADDING", (0,0), (-1,-1), 14),
                                ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
story += [cover_table, Spacer(1, 17*mm),
          Paragraph("包含全部成功、负结果与协议修订记录。评价只使用当前阶段允许的数据；所有最终方法在测试前冻结。五种子结果仅支持有限证据，不作显著性承诺。", body),
          Spacer(1, 8*mm), Paragraph("交付日期：2026-10-27", small), PageBreak()]

lines = (out / "研究报告.md").read_text(encoding="utf-8").splitlines()
index = 0
while index < len(lines):
    line = lines[index].strip()
    if not line or line.startswith("# "):
        index += 1
        continue
    if line.startswith("## "):
        name = line[3:]
        if name == "图表":
            story.append(PageBreak())
        story.append(Paragraph(clean(name), heading))
        index += 1
        continue
    if line.startswith("| "):
        rows=[]
        while index < len(lines) and lines[index].strip().startswith("|"):
            row=[v.strip() for v in lines[index].strip().strip("|").split("|")]
            if not all(re.fullmatch(r"[-: ]+", value) for value in row):
                rows.append([Paragraph(clean(value), cell) for value in row])
            index += 1
        if len(rows[0]) == 6:
            weights=[.18,.24,.14,.10,.19,.15]
        elif len(rows[0]) == 2:
            weights=[.45,.55]
        else:
            weights=[1/len(rows[0])]*len(rows[0])
        tab=Table(rows, colWidths=[available*w for w in weights], repeatRows=1, hAlign="LEFT")
        tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dfebed")),
                                ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#f5f8f8")]),
                                ("VALIGN",(0,0),(-1,-1),"TOP"), ("LEFTPADDING",(0,0),(-1,-1),6),
                                ("RIGHTPADDING",(0,0),(-1,-1),6), ("TOPPADDING",(0,0),(-1,-1),7),
                                ("BOTTOMPADDING",(0,0),(-1,-1),7),
                                ("LINEBELOW",(0,0),(-1,0),.6,teal)]))
        story += [tab, Spacer(1, 10)]
        continue
    match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
    if match:
        name, target = match.groups()
        path = out / target
        from PIL import Image as PillowImage
        with PillowImage.open(path) as source:
            image_width, image_height = source.size
        image = Image(str(path), width=available, height=available*image_height/image_width)
        story.append(KeepTogether([image, Paragraph(clean(name), caption), Spacer(1, 8)]))
        index += 1
        continue
    paragraph=[]
    while index < len(lines) and lines[index].strip() and not lines[index].startswith(("## ","| ","![")):
        paragraph.append(lines[index].strip())
        index += 1
    story.append(Paragraph(clean(" ".join(paragraph)), body))

destination=out / "研究报告.pdf"
doc=SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=margin, rightMargin=margin,
                      topMargin=18*mm, bottomMargin=22*mm, title="ghj EdgeFL 可复现实验研究报告", author="ghj")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(destination)
