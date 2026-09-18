"""Regenerate editable architecture using native draw.io XML (drawio-skill workflow)."""

import xml.etree.ElementTree as ET
from pathlib import Path

destination = Path(__file__).resolve().parents[1] / "docs/assets/architecture.drawio"
mx = ET.Element("mxfile", host="app.diagrams.net")
diagram = ET.SubElement(mx, "diagram", id="all-in-inference", name="Runtime architecture")
model = ET.SubElement(
    diagram, "mxGraphModel", page="1", pageWidth="1340", pageHeight="1040", background="#ffffff"
)
root = ET.SubElement(model, "root")
ET.SubElement(root, "mxCell", id="0")
ET.SubElement(root, "mxCell", id="1", parent="0")


def node(id, label, x, y, w=260, h=90, fill="#eaf3fb", stroke="#648bab", extra="", parent="1"):
    cell = ET.SubElement(
        root,
        "mxCell",
        id=id,
        value=label,
        parent=parent,
        vertex="1",
        style=f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};"
        f"strokeColor={stroke};strokeWidth=1.5;fontColor=#193448;"
        f"fontFamily=Helvetica;fontSize=17;spacing=10;{extra}",
    )
    ET.SubElement(
        cell,
        "mxGeometry",
        x=str(x),
        y=str(y),
        width=str(w),
        height=str(h),
        attrib={"as": "geometry"},
    )


def edge(id, source, target, label="", ports="", points=(), dashed=False):
    cell = ET.SubElement(
        root,
        "mxCell",
        id=id,
        source=source,
        target=target,
        value=label,
        edge="1",
        parent="1",
        style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
        "jettySize=auto;html=1;endArrow=block;strokeColor=#59788f;"
        "strokeWidth=1.6;fontColor=#36566d;fontSize=13;"
        "labelBackgroundColor=#ffffff;" + ports + ("dashed=1;" if dashed else ""),
    )
    geo = ET.SubElement(cell, "mxGeometry", relative="1", attrib={"as": "geometry"})
    if points:
        array = ET.SubElement(geo, "Array", attrib={"as": "points"})
        for x, y in points:
            ET.SubElement(array, "mxPoint", x=str(x), y=str(y))


node(
    "title",
    "All in Inference / sync & async methods",
    40,
    20,
    1250,
    55,
    fill="none",
    stroke="none",
    extra="fontSize=28;fontStyle=1;align=left;",
)
node("mode", "<b>Inference entry</b><br>Choose sync or async", 470, 110, 300, 90)
node(
    "sync",
    "<b>Sync</b><br>Infer after chunk consumption<br>No cross-chunk fusion",
    40,
    300,
    280,
    120,
)
node(
    "async",
    "<b>Async / choose one method</b>",
    480,
    250,
    780,
    300,
    fill="#f0eafa",
    stroke="#9883b2",
    extra="container=1;pointerEvents=0;verticalAlign=top;spacingTop=18;",
)
for ident, label, x, y in [
    ("naive", "<b>Naive</b><br>Aligned replacement", 20, 70),
    ("temporal", "<b>Temporal Smoothing</b><br>Overlap crossfade", 270, 70),
    ("ensemble", "<b>Temporal Ensemble</b><br>Same-tick EMA", 520, 70),
    ("legato", "<b>Legato</b><br>Client protocol scaffold", 20, 180),
    ("custom", "<b>Registered methods</b><br>RTC / others: to implement", 270, 180),
]:
    node(ident, label, x, y, 230, 80, fill="#ffffff", stroke="#9883b2", parent="async")
node(
    "timeline",
    "<b>Bounded action timeline</b><br>Time alignment + method-selected merge",
    420,
    620,
    400,
    90,
    fill="#fff3d9",
    stroke="#c5a459",
)
node(
    "interpolation",
    "<b>Shared interpolation</b><br>Linear / monotone cubic<br>Coarse knots → continuous target",
    40,
    800,
    310,
    100,
    fill="#e6f3ee",
    stroke="#69a38a",
)
node(
    "writer",
    "<b>Shared 200 Hz control</b><br>One writer + velocity guard<br>Independent of policy latency",
    450,
    800,
    310,
    100,
    fill="#e6f3ee",
    stroke="#69a38a",
)
node(
    "adapter",
    "<b>RobotAdapter + RobotSpec</b><br>Arbitrary joint layouts<br>Direct write / measured hold",
    860,
    800,
    350,
    100,
)
node(
    "footer",
    "Temporal smoothing is an async method; interpolation is shared execution.\n"
    "Legato / custom protocols default to no extra fusion. 200 Hz is a soft-real-time target.",
    40,
    950,
    1250,
    70,
    fill="none",
    stroke="none",
    extra="align=left;fontSize=16;",
)
edge(
    "mode-sync",
    "mode",
    "sync",
    "sync",
    "exitX=0;exitY=.5;entryX=.5;entryY=0;",
    points=((180, 155),),
)
edge(
    "mode-async",
    "mode",
    "async",
    "async",
    "exitX=1;exitY=.5;entryX=.5;entryY=0;",
    points=((870, 155),),
)
edge(
    "sync-timeline",
    "sync",
    "timeline",
    "replacement",
    "exitX=.5;exitY=1;entryX=0;entryY=.5;",
    points=((180, 665),),
)
edge(
    "async-timeline",
    "async",
    "timeline",
    "method-selected fusion",
    "exitX=.5;exitY=1;entryX=1;entryY=.5;",
    points=((870, 665),),
)
edge(
    "timeline-interpolation",
    "timeline",
    "interpolation",
    "accepted knots",
    "exitX=.5;exitY=1;entryX=.5;entryY=0;",
    points=((620, 750), (195, 750)),
)
edge(
    "interpolation-writer",
    "interpolation",
    "writer",
    "target",
    "exitX=1;exitY=.5;entryX=0;entryY=.5;",
)
edge("writer-adapter", "writer", "adapter", "commands", "exitX=1;exitY=.5;entryX=0;entryY=.5;")
destination.parent.mkdir(parents=True, exist_ok=True)
ET.indent(mx)
ET.ElementTree(mx).write(destination, encoding="utf-8", xml_declaration=True)
print(destination)
