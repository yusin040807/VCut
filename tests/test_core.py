from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vcut.camera_rules import recommend_camera
from vcut.edl_service import EDLService
from vcut.exceptions import ProgrammeFormatError, SubtitleFormatError, SynchronizationError
from vcut.ffmpeg_adapter import FFmpegAdapter
from vcut.models import CameraSource, EDLSegment, Overlay, ProgrammeSegment, Project, SubtitleEntry
from vcut.programme_reader import read_programme
from vcut.project_service import ProjectService
from vcut.subtitle_service import export_srt, overlap_warnings, parse_srt
from vcut.synchronization import SynchronizationService
from vcut.timecode import format_timecode, parse_timecode
from vcut.validation import ValidationService


def camera(camera_id: str, role: str, file: str = "camera.mp4", duration: float = 200, audio: bool = True) -> CameraSource:
    return CameraSource(camera_id, camera_id, role, file, duration, 1280, 720, 30, "h264", audio, 100)


def edl(segment_id: str, start: float, end: float, camera_id: str, *, approved: bool = True, transition: str = "cut") -> EDLSegment:
    return EDLSegment(segment_id, start, end, camera_id, start, end, "performance", "Event", "Explainable reason", transition, Overlay(), approved)


class TimecodeTests(unittest.TestCase):
    def test_parses_seconds_and_clock_time(self):
        self.assertEqual(parse_timecode("62.5"), 62.5)
        self.assertEqual(parse_timecode("01:02:03.250"), 3723.25)

    def test_rejects_invalid_timecode(self):
        with self.assertRaises(ValueError): parse_timecode("00:99:00")

    def test_format_round_trip(self):
        self.assertEqual(parse_timecode(format_timecode(125.678)), 125.678)


class SynchronizationTests(unittest.TestCase):
    def test_calculates_signed_offsets(self):
        result = SynchronizationService().calculate_offsets({"CAM1": 3.2, "CAM2": 3.65}, "CAM1")
        self.assertEqual(result.offsets, {"CAM1": 0.0, "CAM2": 0.45})

    def test_maps_timeline_to_source_using_offset(self):
        service = SynchronizationService(); config = service.calculate_offsets({"A": 2, "B": 3.5}, "A")
        self.assertEqual(service.timeline_to_source_time(10, "B", config), 11.5)

    def test_requires_two_clap_times(self):
        with self.assertRaises(SynchronizationError): SynchronizationService().calculate_offsets({"A": 1}, "A")


class ParsingTests(unittest.TestCase):
    def test_reads_valid_programme_sorted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "programme.csv"
            path.write_text("segment_id,start_time,end_time,event_type,description\nSEG2,10,20,speech,Talk\nSEG1,0,10,opening,Open\n", encoding="utf-8")
            result = read_programme(path)
            self.assertEqual([item.id for item in result], ["SEG1", "SEG2"])

    def test_programme_reports_duplicate_identifier(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "programme.csv"
            path.write_text("segment_id,start_time,end_time,event_type,description\nSEG1,0,2,opening,A\nSEG1,2,3,speech,B\n", encoding="utf-8")
            with self.assertRaises(ProgrammeFormatError): read_programme(path)

    def test_parses_and_exports_srt(self):
        source = "1\n00:00:01,000 --> 00:00:03,250\nWelcome\n"
        parsed = parse_srt(source)
        self.assertEqual(parsed[0].text, "Welcome")
        self.assertIn("00:00:03,250", export_srt(parsed))

    def test_rejects_empty_subtitle(self):
        with self.assertRaises(SubtitleFormatError): parse_srt("1\n00:00:01,000 --> 00:00:03,000\n")

    def test_warns_about_subtitle_overlap(self):
        items = [SubtitleEntry(0, 3, "A"), SubtitleEntry(2, 4, "B")]
        self.assertEqual(len(overlap_warnings(items)), 1)


class RecommendationAndEDLTests(unittest.TestCase):
    def test_opening_prefers_wide_camera(self):
        result = recommend_camera(ProgrammeSegment("S", 0, 5, "opening"), [camera("A", "front"), camera("B", "wide")])
        self.assertEqual(result.camera_id, "B")
        self.assertIn("preferred", result.reason)

    def test_long_repeated_view_changes_for_variety(self):
        result = recommend_camera(ProgrammeSegment("S", 0, 10, "performance"), [camera("A", "wide"), camera("B", "side")], "A")
        self.assertEqual(result.camera_id, "B")
        self.assertIn("variety", result.reason)

    def test_material_edl_change_resets_approval(self):
        changed = EDLService().update_segment(edl("S", 0, 10, "A"), {"selected_camera": "B"})
        self.assertFalse(changed.approved)
        self.assertTrue(changed.manually_modified)

    def test_approving_only_is_not_manual_modification(self):
        item = edl("S", 0, 10, "A", approved=False)
        changed = EDLService().update_segment(item, {"approved": True})
        self.assertTrue(changed.approved)
        self.assertFalse(changed.manually_modified)

    def test_programme_generates_source_aligned_edl(self):
        sync = SynchronizationService().calculate_offsets({"A": 2.0, "B": 2.5}, "A")
        project = Project("Demo")
        segments = EDLService().generate(project, [camera("A", "front"), camera("B", "wide")], [ProgrammeSegment("S", 10, 20, "opening")], sync)
        self.assertEqual(segments[0].selected_camera, "B")
        self.assertEqual(segments[0].source_start, 10.5)
        self.assertEqual(segments[0].transition, "fade")


class PersistenceTests(unittest.TestCase):
    def test_project_round_trip_and_folder_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"; service = ProjectService(); original = Project("Demo", consent_confirmed=True)
            service.create_project(root, original)
            self.assertEqual(service.load_project(root).project_name, "Demo")
            self.assertTrue((root / "evidence" / "screenshots").is_dir())

    def test_project_path_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(Exception): ProjectService.safe_project_path(Path(temp) / "project", "../outside.txt")

    def test_atomic_json_is_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"; service = ProjectService(); service.create_project(root, Project("Demo"))
            self.assertEqual(json.loads((root / "project.json").read_text(encoding="utf-8"))["project_name"], "Demo")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.files=[]
        for name in ("a.mp4", "b.mp4"):
            path=Path(self.temp.name)/name; path.write_bytes(b"media"); self.files.append(str(path))
        self.cameras=[camera("A","wide",self.files[0]),camera("B","front",self.files[1])]

    def test_preview_allows_pending_approvals(self):
        project=Project("Demo",consent_confirmed=True,main_audio_camera="A")
        issues=ValidationService().validate_preview(project,self.cameras,[edl("S",0,10,"A",approved=False)])
        self.assertNotIn("SEGMENT_NOT_APPROVED",{issue.code for issue in issues})

    def test_final_enforces_approval_and_duration(self):
        project=Project("Demo",consent_confirmed=True,main_audio_camera="A")
        issues=ValidationService().validate_final(project,self.cameras,[edl("S",0,10,"A",approved=False)])
        codes={issue.code for issue in issues}
        self.assertIn("SEGMENT_NOT_APPROVED",codes); self.assertIn("OUTPUT_DURATION_INVALID",codes)

    def test_final_accepts_compliant_edit(self):
        project=Project("Demo",consent_confirmed=True,main_audio_camera="A",privacy_confirmed=True,copyright_confirmed=True)
        segments=[edl("S1",0,20,"A",transition="fade"),edl("S2",20,40,"B"),edl("S3",40,60,"A"),edl("S4",60,80,"B")]
        issues=ValidationService().validate_final(project,self.cameras,segments)
        self.assertEqual([issue for issue in issues if issue.severity=="error"],[])

    def test_missing_camera_file_is_blocking(self):
        project=Project("Demo",consent_confirmed=True)
        issues=ValidationService().validate_preview(project,[camera("A","wide","missing.mp4"),self.cameras[1]],[edl("S",0,10,"A")])
        self.assertIn("CAMERA_FILE_MISSING",{issue.code for issue in issues})

    def test_main_audio_is_required(self):
        project=Project("Demo",consent_confirmed=True)
        issues=ValidationService().validate_preview(project,self.cameras,[edl("S",0,10,"A")])
        self.assertIn("MAIN_AUDIO_INVALID",{issue.code for issue in issues})

    def test_subtitle_outside_output_is_rejected(self):
        project=Project("Demo",consent_confirmed=True,main_audio_camera="A",privacy_confirmed=True,copyright_confirmed=True)
        segments=[edl("S1",0,20,"A",transition="fade"),edl("S2",20,40,"B"),edl("S3",40,60,"A"),edl("S4",60,80,"B")]
        issues=ValidationService().validate_final(project,self.cameras,segments,[SubtitleEntry(79,90,"Too late")])
        self.assertIn("SUBTITLE_RANGE_INVALID",{issue.code for issue in issues})


class FFmpegCommandTests(unittest.TestCase):
    def test_segment_command_is_argument_array(self):
        adapter=FFmpegAdapter("ffmpeg")
        command=adapter.segment_command(Path("input.mp4"),Path("output.mp4"),1.25,5,854,480,30,True)
        self.assertIsInstance(command,list);self.assertIn("-ss",command);self.assertIn("DRAFT PREVIEW"," ".join(command))

    @patch("vcut.ffmpeg_adapter.subprocess.run")
    def test_adapter_explicitly_disables_shell(self,mock_run):
        mock_run.return_value=type("Result",(),{"returncode":0,"stdout":"","stderr":""})()
        FFmpegAdapter("ffmpeg").run(["ffmpeg","-version"])
        self.assertFalse(mock_run.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
