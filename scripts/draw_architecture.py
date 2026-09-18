"""Regenerate editable architecture using native draw.io XML (drawio-skill workflow)."""

import xml.etree.ElementTree as ET
from pathlib import Path

destination = Path(__file__).resolve().parents[1] / "docs/assets/architecture.drawio"
mx = ET.Element("mxfile", host="app.diagrams.net")
diagram = ET.SubElement(mx, "diagram", id="all-in-inference", name="Runtime architecture")
model = ET.SubElement(
    diagram, "mxGraphModel", page="1", pageWidth="1340", pageHeight="840", background="#ffffff"
)
root = ET.SubElement(model, "root")
ET.SubElement(root, "mxCell", id="0")
ET.SubElement(root, "mxCell", id="1", parent="0")


def node(id, label, x, y, w=260, h=90, fill="#eaf3fb", stroke="#648bab", extra=""):
    cell = ET.SubElement(
        root,
        "mxCell",
        id=id,
        value=label,
        parent="1",
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
    "All in Inference  /  action chunks → continuous execution",
    40,
    20,
    1250,
    55,
    fill="none",
    stroke="none",
    extra="fontSize=28;fontStyle=1;align=left;",
)
node(
    "subtitle",
    "Model-agnostic · configurable joint layouts · one command writer · post-run reporting",
    40,
    76,
    1240,
    34,
    fill="none",
    stroke="none",
    extra="align=left;fontSize=16;",
)
node(
    "observation",
    "<b>Observation worker</b><br>Fresh state + sensor snapshot<br>Independent read rate",
    40,
    150,
)
node(
    "policy",
    "<b>Policy adapter + JointCodec</b><br>VLA / VLM / coarse planner<br>Decode into robot-space H × D",
    370,
    150,
    310,
)
node(
    "schedule",
    "<b>Schedule extension point</b><br>Async: request-time alignment<br>Sync: rebase after inference",
    750,
    150,
    310,
    fill="#f0eafa",
    stroke="#9883b2",
)
node(
    "timeline",
    "<b>Bounded action timeline</b><br>Drop elapsed / stale results<br>Replace · temporal · ensemble",
    750,
    340,
    310,
    fill="#fff3d9",
    stroke="#c5a459",
)
node(
    "interpolation",
    "<b>Continuous target</b><br>Linear / monotone cubic<br>Per-axis blending masks",
    370,
    340,
    310,
    fill="#e6f3ee",
    stroke="#69a38a",
)
node(
    "writer",
    "<b>200 Hz command owner</b><br>Deadline clock + velocity guard<br>Skip missed slots; never burst",
    40,
    340,
    260,
    fill="#e6f3ee",
    stroke="#69a38a",
)
node(
    "adapter",
    "<b>RobotAdapter</b><br>read · direct write · measured hold<br>No implicit enable / home",
    40,
    550,
    310,
)
node(
    "spec",
    "<b>RobotSpec</b><br>Names · units · limits · groups<br>Single / dual / mixed joints",
    420,
    550,
    310,
)
node(
    "telemetry",
    "<b>Bounded in-memory trace</b><br>Latency · jitter · drops · faults<br>JSON / CSV after execution",
    800,
    550,
    310,
    fill="#f4f5f7",
    stroke="#9aa9b3",
)
node(
    "footer",
    "200 Hz is a measured soft-real-time target, not a hard real-time guarantee.\n"
    "Hardware SDK / safety controller owns bus transport, torque and physical protection.",
    40,
    724,
    1220,
    68,
    fill="none",
    stroke="none",
    extra="align=left;fontSize=15;",
)
edge("obs-policy", "observation", "policy", "snapshot", "exitX=1;exitY=.5;entryX=0;entryY=.5;")
edge(
    "policy-schedule",
    "policy",
    "schedule",
    "request / result",
    "exitX=1;exitY=.5;entryX=0;entryY=.5;",
)
edge(
    "schedule-timeline",
    "schedule",
    "timeline",
    "timestamped chunk",
    "exitX=.5;exitY=1;entryX=.5;entryY=0;",
)
edge(
    "timeline-interp",
    "timeline",
    "interpolation",
    "aligned knots",
    "exitX=0;exitY=.5;entryX=1;entryY=.5;",
)
edge("interp-writer", "interpolation", "writer", "target", "exitX=0;exitY=.5;entryX=1;entryY=.5;")
edge("writer-adapter", "writer", "adapter", "one writer", "exitX=.5;exitY=1;entryX=.42;entryY=0;")
edge(
    "adapter-obs",
    "adapter",
    "observation",
    "",
    "exitX=0;exitY=.5;entryX=0;entryY=.5;",
    points=((15, 595), (15, 195)),
)
edge(
    "spec-adapter",
    "spec",
    "adapter",
    "joint layout",
    "exitX=0;exitY=.5;entryX=1;entryY=.5;",
    dashed=True,
)
edge(
    "writer-trace",
    "writer",
    "telemetry",
    "append only",
    "exitX=.82;exitY=1;entryX=.5;entryY=0;",
    points=((253, 478), (955, 478)),
    dashed=True,
)
destination.parent.mkdir(parents=True, exist_ok=True)
ET.indent(mx)
ET.ElementTree(mx).write(destination, encoding="utf-8", xml_declaration=True)
print(destination)
