"""Post-run JSON/CSV export. No file writes or web requests during control."""

import csv
import json
from pathlib import Path


def export_run(runtime, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "summary.json").write_text(
        json.dumps(runtime.summary(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    names = [j.name for j in runtime.robot.spec.joints]
    with (directory / "commands.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["time_s", "lateness_s", "underrun"]
            + [f"command/{n}" for n in names]
            + [f"observed/{n}" for n in names]
        )
        for t, lateness, starved, q, observed in runtime.trace():
            writer.writerow([t, lateness, int(starved), *q, *observed])
