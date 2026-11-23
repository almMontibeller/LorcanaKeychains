#!/usr/bin/env python3
"""Validate the repaired projects with the locally installed Bambu Studio CLI."""
from pathlib import Path
import json
import re
import subprocess
import tempfile
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
SETS = ROOT / "sets"
DEST = ROOT / "collection" / "v1.2"
LOGS = ROOT / "validation"


def bambu_command():
    app = Path("/var/lib/flatpak/app/com.bambulab.BambuStudio/current/active")
    metadata = (app / "metadata").read_text()
    runtime = re.search(r"^runtime=(.+)$", metadata, re.M).group(1)
    for base in (Path("/var/lib/flatpak/runtime"), Path.home() / ".local/share/flatpak/runtime"):
        files = base / runtime / "active/files"
        loader = files / "lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
        if loader.exists():
            return [str(loader), "--library-path", ":".join(map(str, [app / "files/lib", files / "lib/x86_64-linux-gnu", files / "lib"])), str(app / "files/bin/bambu-studio")]
    raise RuntimeError("Bambu's installed runtime was not found")


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    only = sys.argv[1:]
    report_path = DEST / "Validation_v1.2.json"
    reports = json.loads(report_path.read_text()) if only and report_path.exists() else []
    command = bambu_command()
    for path in sorted(SETS.glob("Set_*/v1.2/Set_*.3mf")):
        if only and path.name[4:6] not in only:
            continue
        reports = [report for report in reports if report["filename"][4:6] != path.name[4:6]]
        logs = LOGS / path.parent.parent.name / "v1.2"
        logs.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="lorcana-bambu-") as directory:
            work = Path(directory)
            run = subprocess.run(command + ["--datadir", str(work / "settings"), "--debug", "2", "--info", "--slice", "1", "--outputdir", directory, str(path)], cwd=work, capture_output=True, text=True, timeout=180)
            output = run.stdout + run.stderr
            (logs / (path.stem + ".log")).write_text(output)
            assert "manifold = yes" in output, path.name
            result = json.loads((work / "result.json").read_text())
            (logs / (path.stem + "-result.json")).write_text(json.dumps(result, indent=2))
            if run.returncode != 0 or result["return_code"] != 0:
                report = {"filename": path.name, "import_exit_code": run.returncode, "slice_result": result}
                reports.append(report)
                print(path.name, "SLICE FAILED:", result.get("error_string"), flush=True)
                (DEST / "Validation_v1.2.json").write_text(json.dumps(reports, indent=2))
                continue
            plate = result["sliced_plates"][0]
            with zipfile.ZipFile(path) as archive:
                config = json.loads(archive.read("Metadata/project_settings.config"))
            channels = [filament["id"] for filament in plate["filaments"]]
            assert channels == list(range(1, len(config["filament_colour"]) + 1)), (path.name, channels)
            assert all(filament["main_used_g"] > 0 for filament in plate["filaments"]), path.name
            assert plate["warning_message"] == "", (path.name, plate["warning_message"])
            info = dict(re.findall(r"^(size_[xyz]|number_of_facets|volume) = (.+)$", output, re.M))
            reports.append({
                "filename": path.name,
                "bambu_version": "02.08.02.61",
                "import_exit_code": run.returncode,
                "manifold": True,
                "model_info": info,
                "slice_result": result,
                "filament_channels_used": channels,
                "gui_open_verified": False,
                "environment_notes": "CLI used with the installed Flatpak runtime. The desktop display is unavailable in this session. The relocated CLI reports missing /app resources; embedded project settings were used and slicing succeeded.",
            })
            print(path.name, "imported and sliced;", len(channels), "colour channels", flush=True)
            (DEST / "Validation_v1.2.json").write_text(json.dumps(reports, indent=2))
    reports.sort(key=lambda report: report["filename"])
    assert len(reports) == 14
    assert all(report["slice_result"]["return_code"] == 0 for report in reports)
    (DEST / "Validation_v1.2.json").write_text(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
