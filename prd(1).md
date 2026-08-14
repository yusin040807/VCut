# Product Requirements Document (PRD)

# VCut — AI-Powered Multi-Camera Video Editing System

**Version:** 1.0  
**Product:** VCut  
**Project Type:** Local-first desktop application  
**Primary Platform:** Windows  
**Target Runtime:** Python 3.11+  
**UI Framework:** Tkinter  
**Video Processing:** FFmpeg / ffprobe  
**Computer Vision:** YOLO-based person detection and video-frame analysis

---

## 1. Product Overview

VCut is a local-first, human-supervised multi-camera video editing system designed to simplify the editing of event videos, particularly kindergarten graduation ceremonies.

The system accepts footage from two to four cameras, synchronizes the recordings using manually entered clap timestamps, imports programme segments, analyses camera footage with computer vision, recommends suitable camera angles, generates an explainable Edit Decision List (EDL), allows the user to review and approve every recommendation, and finally renders an edited MP4 video using FFmpeg.

VCut is designed around the principle:

> **AI recommends the edit; the human reviews and approves it; the renderer produces the final video.**

Imported video footage remains local to the user's machine and is not uploaded by VCut.

---

# 2. Problem Statement

Editing a multi-camera event video manually requires the editor to:

1. Review footage from multiple cameras.
2. Synchronize recordings.
3. Identify useful sections of each camera recording.
4. Decide when to switch camera angles.
5. Ensure selected footage is actually available at the required source time.
6. Add titles, lower-thirds, subtitles, audio and transitions.
7. Review every editing decision.
8. Render the final video.
9. Check that the final output satisfies project requirements.

This workflow can be time-consuming and repetitive.

VCut addresses this problem by combining:

- Camera metadata inspection
- Manual synchronization
- Programme segmentation
- Computer vision
- Explainable camera scoring
- Automatic camera switching
- EDL generation
- Human approval
- Validation
- FFmpeg rendering

---

# 3. Product Goals

## 3.1 Primary Goals

VCut shall:

- Support two to four camera sources.
- Store camera metadata and project information locally.
- Synchronize multiple camera recordings using clap timestamps.
- Convert programme timeline time into camera source time.
- Import programme segments from UTF-8 CSV files.
- Analyse camera frames using computer vision.
- Detect people and evaluate camera framing.
- Score camera suitability.
- Automatically recommend camera angles.
- Use a main camera as the default/fallback camera.
- Automatically switch cameras when another camera is sufficiently better.
- Prevent selections that reference unavailable source footage.
- Generate an explainable EDL.
- Allow users to edit EDL decisions.
- Require approval before final rendering.
- Validate final output requirements.
- Support subtitles and lower-third text.
- Support a main audio camera.
- Render preview and final MP4 output using FFmpeg.
- Maintain local audit logs.

## 3.2 Secondary Goals

VCut should:

- Reduce manual editing effort.
- Make AI decisions understandable.
- Avoid unnecessary camera switching.
- Preserve the user's ability to override AI recommendations.
- Keep imported footage local.
- Provide clear validation errors before rendering.

---

# 4. Non-Goals

VCut is not intended to:

- Upload user footage to a cloud editing service.
- Replace the human approval process completely.
- Automatically publish videos to social media.
- Provide a full professional nonlinear editing suite.
- Support unlimited camera sources.
- Perform unrestricted cloud-based AI video processing.
- Guarantee that every AI camera recommendation is aesthetically optimal.

---

# 5. Target Users

## 5.1 Primary User

### Event Video Editor

A user who needs to create a multi-camera event video but wants to reduce the amount of manual camera selection and synchronization work.

Typical characteristics:

- Has two to four camera recordings.
- Has limited video editing time.
- Needs an explainable automated editing workflow.
- Wants to review AI decisions before rendering.

## 5.2 Secondary User

### Student / Project Demonstrator

A student who needs to demonstrate an AI-assisted video editing system with:

- Computer vision
- Synchronization
- Automated decision making
- Explainable recommendations
- EDL generation
- Video rendering

---

# 6. Core User Workflow

The main workflow is:

```text
Create / Open Project
        ↓
Import Cameras
        ↓
Synchronize Cameras
        ↓
Import Programme Segments
        ↓
Generate AI Recommendations
        ↓
Review EDL
        ↓
Edit / Approve Recommendations
        ↓
Audio & Text
        ↓
Validate
        ↓
Render Preview / Final Video
        ↓
Output MP4
```

The desktop application exposes the workflow through these steps:

```text
Project
Cameras
Synchronize
Segments
EDL Review
Audio & Text
Export
```

---

# 7. Functional Requirements

## FR-01 Project Creation

The system shall allow users to create a project.

A project shall support:

- Project name
- Event name
- Event date
- Sharing type
- Consent confirmation
- Privacy confirmation
- Copyright confirmation
- Opening title
- Closing credits
- Lower-third text
- Lower-third start time
- Lower-third end time
- Main audio camera
- Render settings

Default render settings are:

- Width: 1280
- Height: 720
- FPS: 30
- Volume: 1.0
- Muted: false
- Fade-in: 1 second
- Fade-out: 1 second

---

# 8. Camera Management

## FR-02 Import Camera Sources

The system shall support two to four camera sources.

Each camera source shall contain:

- Camera ID
- Camera name
- Camera role
- File path
- Duration
- Width
- Height
- FPS
- Codec
- Audio availability
- File size

The system shall verify that imported camera files exist.

## FR-03 Camera Limit

The system shall reject projects with:

- Fewer than two cameras
- More than four cameras

The recommended default main camera is:

```text
CAM001
```

The main camera acts as the default/fallback angle when alternative cameras are not sufficiently better or are unavailable.

---

# 9. Media Probing

## FR-04 Media Metadata

The system shall use media probing to obtain video information such as:

- Duration
- Resolution
- Frame rate
- Codec
- Audio stream availability
- File size

The media information shall be stored as camera metadata.

---

# 10. Synchronization

## FR-05 Reference Camera

The user shall select a reference camera.

The reference camera must have a valid clap timestamp.

## FR-06 Clap Timestamp Input

The user shall enter one clap timestamp per camera.

Example:

```text
CAM001=00:00:03.200
CAM002=00:00:03.700
CAM003=00:00:02.900
```

At least two camera timestamps are required.

Negative timestamps shall not be accepted.

## FR-07 Offset Calculation

The synchronization service shall calculate:

```text
offset(camera) = camera_clap_time - reference_clap_time
```

The reference camera shall have an offset of:

```text
0.0
```

## FR-08 Timeline-to-Source Mapping

The system shall map programme timeline time to source video time using the camera synchronization offset.

Conceptually:

```text
source_time = timeline_time + camera_offset
```

If the mapping results in a negative source time, the system shall reject the invalid source position.

---

# 11. Programme Segments

## FR-09 CSV Import

The system shall import UTF-8 programme CSV files.

Required fields:

```text
id
start
end
event_type
description
```

Example:

```csv
id,start,end,event_type,description
SEG001,00:00:00.000,00:00:10.000,performance,Performance Part 1
SEG002,00:00:10.000,00:00:20.000,performance,Performance Part 2
```

## FR-10 Manual Segment Editing

The user shall be able to:

- Add a segment
- Edit a segment
- Delete a segment

A segment must have:

```text
end > start
```

## FR-11 Segment Coverage

Programme segments should cover the intended editing timeline without unintended gaps or overlaps.

---

# 12. Computer Vision

## FR-12 Vision-Based Camera Analysis

The system shall analyse camera frames using computer vision.

The implementation uses a YOLO-based model for person detection.

The default model is:

```text
yolo11n.pt
```

The system shall analyse factors including:

- Subject size
- Subject position / centre
- Person count
- Image sharpness
- Motion
- Camera role suitability

## FR-13 Camera Score

The system shall calculate a total camera score based on multiple visual factors.

The current scoring model includes weighted factors for:

| Factor | Weight |
|---|---:|
| Subject size | 0.20 |
| Subject centre | 0.15 |
| Person count | 0.15 |
| Sharpness | 0.20 |
| Motion | 0.10 |
| Camera role | 0.20 |

The score shall be used by the automatic camera selection system.

---

# 13. Automatic Camera Recommendation

## FR-14 Camera Recommendation

For each analysed timeline position, the system shall identify suitable camera candidates.

The recommendation shall include:

- Selected camera ID
- Reason for selection

The reason should be explainable rather than simply returning a camera ID.

Example:

```text
CAM002 selected by automatic vision analysis.
Average vision score: 68.4/100.
```

---

# 14. Automatic Camera Switching

## FR-15 Main Camera

The system shall support:

```text
CAM001
```

as the main/default camera.

If no alternative camera is clearly better, the system should remain on CAM001.

## FR-16 Camera Switching

The SwitchEngine shall consider:

- Camera score
- Current camera
- Score difference
- Minimum shot duration
- Confirmation duration
- Score smoothing
- Camera availability

## FR-17 Avoid Excessive Switching

The system shall avoid unnecessary rapid camera switching.

A candidate should satisfy the configured switching conditions before becoming the active camera.

## FR-18 Camera Availability

The system shall not create an EDL segment that references source footage outside the selected camera's available recording range.

If a selected alternative camera becomes unavailable, the system should return to an available camera, preferably the main camera.

---

# 15. Edit Decision List (EDL)

## FR-19 EDL Generation

The system shall generate an EDL from:

- Programme segments
- Camera sources
- Synchronization offsets
- Vision analysis
- SwitchEngine decisions

Each EDL segment shall contain:

- Segment ID
- Timeline start
- Timeline end
- Selected camera
- Source start
- Source end
- Event type
- Description
- Reason
- Transition
- Overlay
- Approval status
- Manual modification status

## FR-20 Source Range Validation

Every EDL segment shall verify that:

```text
source_start >= 0
```

and:

```text
source_end <= camera_duration
```

within the allowed tolerance.

Invalid source ranges shall block rendering.

## FR-21 Segment Merging

Adjacent segments using the same camera may be merged when appropriate.

The system shall preserve actual camera switches.

---

# 16. Human Review

## FR-22 EDL Review

The user shall be able to review every generated EDL recommendation.

The review interface shall show:

- Timeline
- Camera
- Event type
- Transition
- Approval status
- Reason

## FR-23 Edit Recommendation

The user shall be able to edit the selected EDL segment.

Material changes shall return the segment to:

```text
Pending
```

## FR-24 Approval

The user shall be able to:

- Approve selected
- Approve all

Final rendering shall require all EDL segments to be approved.

---

# 17. Audio

## FR-25 Main Audio Camera

The user shall select a main audio camera.

The selected camera must:

- Exist in the imported camera list
- Contain an audio stream

## FR-26 Audio Settings

The user shall be able to configure:

- Volume
- Mute
- Fade-in
- Fade-out

The final renderer shall use the selected camera as the continuous audio source.

---

# 18. Text and Subtitles

## FR-27 Opening Title

The system shall support an opening title.

The opening title shall be displayed near the beginning of the final video.

## FR-28 Lower Third

The system shall support:

- Lower-third text
- Start time
- End time

## FR-29 Closing Credits

The system shall support closing credits near the end of the video.

## FR-30 Subtitle Import

The system shall support subtitle entries.

Each subtitle contains:

- Start time
- End time
- Text
- Source

The system shall detect invalid subtitle timing and empty subtitle text.

---

# 19. Validation

## FR-31 Preview Validation

Before preview rendering, the system shall check:

- Consent confirmation
- Camera count
- Camera file existence
- EDL existence
- Unique segment IDs
- Segment ranges
- Camera validity
- Source ranges
- Main audio camera
- Audio availability

## FR-32 Final Validation

Before final rendering, the system shall additionally verify:

### Output Duration

The final output must be:

```text
60–180 seconds
```

### Camera Usage

At least:

```text
2 camera angles
```

must be used.

### Camera Switches

At least:

```text
3 camera switches
```

must occur.

### Required Text

The project must contain:

- Opening title
- Closing credits
- Lower-third label or subtitles

### Transitions

At least one fade transition must exist.

### Approval

Every EDL segment must be approved.

### Privacy

The final privacy confirmation must be completed.

### Copyright

The final copyright confirmation must be completed.

---

# 20. Rendering

## FR-33 Preview Rendering

The system shall support a preview render.

Preview output shall use reduced rendering settings for faster processing.

The preview file shall be:

```text
output/preview.mp4
```

## FR-34 Final Rendering

The system shall render the approved EDL into:

```text
output/final_video.mp4
```

The final renderer shall:

1. Extract each EDL segment from its selected camera.
2. Apply required video processing.
3. Apply transitions.
4. Concatenate visual segments.
5. Add continuous audio.
6. Apply audio volume and fades.
7. Add subtitles if present.
8. Add opening title.
9. Add lower-third.
10. Add closing credits.
11. Encode the final MP4.
12. Save the final video locally.

## FR-35 FFmpeg Safety

FFmpeg commands shall be constructed using argument arrays rather than shell command strings.

Shell execution shall not be used for video commands.

## FR-36 Rendering Progress

The GUI shall provide rendering progress/status messages.

---

# 21. Export

## FR-37 EDL Export

The system shall allow the user to export EDL information as JSON.

The exported information shall preserve the editing decisions required to reproduce the project state.

## FR-38 Video Export

The system shall provide:

```text
preview.mp4
final_video.mp4
```

depending on the selected rendering mode.

---

# 22. Project Storage

## FR-39 Local Project Storage

Project information shall be stored locally.

The project shall preserve:

- Project settings
- Camera metadata
- Synchronization data
- Programme segments
- EDL segments
- Subtitle data

## FR-40 Audit Log

Important project operations shall be recorded in a local audit log.

Examples include:

- Preview rendering
- Final rendering
- Rendering failures

---

# 23. User Interface Requirements

The desktop GUI shall provide the following workflow:

```text
1. Project
2. Cameras
3. Synchronize
4. Segments
5. EDL Review
6. Audio & Text
7. Export
```

## Project Page

The user can:

- Create a project
- Open a project
- Configure project metadata

## Cameras Page

The user can:

- Import cameras
- View camera metadata
- Remove cameras

## Synchronization Page

The user can:

- Select reference camera
- Enter clap timestamps
- Calculate offsets
- Save synchronization

## Segments Page

The user can:

- Import programme CSV
- Add segment
- Edit segment
- Delete segment

## EDL Review Page

The user can:

- Generate recommendations
- Edit selected recommendation
- Approve selected
- Approve all
- Export EDL JSON

## Audio & Text Page

The user can:

- Select main audio camera
- Set volume
- Mute audio
- Configure text
- Import subtitles
- Add subtitles
- Delete subtitles

## Export Page

The user can:

- Validate project
- Render preview
- Render final video
- View render status

---

# 24. Non-Functional Requirements

## NFR-01 Local-First Processing

Video footage shall remain local to the user's computer.

## NFR-02 Explainability

AI camera recommendations shall provide a reason and relevant camera scoring information.

## NFR-03 Reliability

Invalid camera source ranges and invalid EDL states shall block rendering rather than silently producing an incorrect video.

## NFR-04 Usability

The application should guide the user through a clear sequential workflow.

## NFR-05 Maintainability

The system shall separate responsibilities into services such as:

- Vision analysis
- Synchronization
- Camera switching
- EDL generation
- Validation
- Rendering
- Project management

## NFR-06 Testability

Core functionality shall be covered by automated tests.

## NFR-07 Performance

Long-running video analysis and rendering should not freeze the GUI.

The GUI should execute long-running rendering operations in a background worker.

## NFR-08 Compatibility

The project targets Python 3.11 or later and requires FFmpeg/ffprobe for media processing.

---

# 25. System Architecture

The system follows a service-oriented local desktop architecture.

```text
                    ┌─────────────────────┐
                    │      Tkinter GUI    │
                    └──────────┬──────────┘
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
             ▼                 ▼                 ▼
       Project Service   Programme Reader   Synchronization
             │                 │                 │
             └─────────────────┼─────────────────┘
                               │
                               ▼
                       Vision Analyzer
                               │
                               ▼
                        Camera Rules
                               │
                               ▼
                        Switch Engine
                               │
                               ▼
                         EDL Service
                               │
                               ▼
                       Validation Service
                               │
                               ▼
                           Renderer
                               │
                               ▼
                      FFmpeg / ffprobe
                               │
                               ▼
                         Final MP4
```

---

# 26. Main Data Flow

## 26.1 Camera Flow

```text
Camera Files
    ↓
Media Probe
    ↓
Camera Metadata
    ↓
Camera Sources
```

## 26.2 Synchronization Flow

```text
Clap Times
    ↓
Reference Camera
    ↓
SynchronizationService
    ↓
Camera Offsets
    ↓
Timeline → Source Mapping
```

## 26.3 AI Editing Flow

```text
Timeline Position
    ↓
Read Camera Frames
    ↓
YOLO Person Detection
    ↓
Visual Metrics
    ↓
Camera Score
    ↓
SwitchEngine
    ↓
Camera Shot Decision
```

## 26.4 EDL Flow

```text
Programme Segment
       +
Camera Analysis
       +
Synchronization
       ↓
SwitchEngine
       ↓
EDLService
       ↓
EDL Segments
       ↓
Human Review
       ↓
Approval
```

## 26.5 Rendering Flow

```text
Approved EDL
     ↓
Validation
     ↓
FFmpeg Segment Extraction
     ↓
Visual Concatenation
     ↓
Audio
     ↓
Titles / Lower Third / Subtitles
     ↓
Closing Credits
     ↓
H.264 MP4
```

---

# 27. Camera Selection Strategy

VCut uses a main-camera fallback strategy.

The default main camera is:

```text
CAM001
```

The intended behaviour is:

```text
Is CAM001 available?
        │
        ├── Yes
        │    ↓
        │  Is another camera clearly better?
        │       │
        │       ├── No → Stay on CAM001
        │       │
        │       └── Yes → Switch to better camera
        │
        └── No
             ↓
        Select best available camera
```

When an alternative camera is no longer available:

```text
Alternative Camera
       ↓
Unavailable
       ↓
Return to CAM001 if available
       ↓
Otherwise choose another valid camera
```

---

# 28. Example Editing Scenario

For a 125.109-second performance:

```text
00:00.000 → 01:19.500   CAM001
01:19.500 → 01:20.000   CAM002
01:20.000 → 01:24.000   CAM001
01:24.000 → 01:30.000   CAM002
01:30.000 → 02:05.109   CAM001
```

The final result uses:

```text
Cameras used: 2
Camera switches: 4
Duration: 125.109 seconds
```

The EDL is then reviewed and approved before final rendering.

---

# 29. Error Handling Requirements

The system shall display clear errors for conditions including:

```text
No camera is available
Camera file missing
Invalid synchronization
Invalid source range
Invalid segment range
Duplicate segment ID
Insufficient camera count
Too many cameras
Insufficient output duration
Insufficient camera angles
Insufficient camera switches
Missing main audio
Missing title
Missing closing credits
Missing label or subtitles
Unapproved EDL segment
Privacy confirmation missing
Copyright confirmation missing
FFmpeg unavailable
```

Errors should identify the relevant segment or project requirement whenever possible.

---

# 30. Security and Privacy Requirements

## SR-01 Local Footage

Imported footage shall remain local.

## SR-02 No Unnecessary Upload

The system shall not upload user video files as part of normal operation.

## SR-03 Explicit Confirmation

The project shall require confirmation that footage is authorized or simulated.

## SR-04 Privacy Check

The final rendering process shall require privacy confirmation.

## SR-05 Copyright Check

The final rendering process shall require copyright confirmation.

---

# 31. Testing Requirements

The system shall include automated tests covering:

- Core data handling
- Camera recommendations
- Synchronization
- EDL generation
- Camera switching
- Automatic editing behaviour
- Validation rules

The test suite should pass before a release is considered complete.

Example expected result:

```text
27 passed
```

when the current project test suite is executed.

---

# 32. Acceptance Criteria

The product shall be considered functionally complete when all of the following are satisfied:

### AC-01 Project

- [ ] User can create and open a project.
- [ ] Project information can be saved and loaded.

### AC-02 Cameras

- [ ] Two to four cameras can be imported.
- [ ] Camera metadata is displayed.
- [ ] Missing camera files are detected.

### AC-03 Synchronization

- [ ] A reference camera can be selected.
- [ ] Clap timestamps can be entered.
- [ ] Offsets are calculated correctly.
- [ ] Timeline-to-source mapping works.

### AC-04 Programme

- [ ] CSV segments can be imported.
- [ ] Segments can be added, edited and deleted.
- [ ] Timecode is displayed as `HH:MM:SS.mmm`.

### AC-05 AI Analysis

- [ ] Camera frames can be analysed.
- [ ] People can be detected.
- [ ] Camera scores are generated.
- [ ] Camera recommendations contain explanations.

### AC-06 Automatic Editing

- [ ] CAM001 can act as the main camera.
- [ ] Better alternative cameras can be selected.
- [ ] Unnecessary rapid switching is avoided.
- [ ] Unavailable source footage is rejected or avoided.

### AC-07 EDL

- [ ] EDL segments are generated.
- [ ] Source ranges are valid.
- [ ] Camera switches are represented.
- [ ] EDL recommendations can be reviewed.
- [ ] EDL recommendations can be edited.
- [ ] EDL recommendations can be approved.

### AC-08 Validation

A final video must satisfy:

```text
Duration: 60–180 seconds
Cameras used: >= 2
Camera switches: >= 3
Opening title: present
Closing credits: present
Lower-third or subtitles: present
At least one fade: present
All EDL segments approved
Privacy confirmation: complete
Copyright confirmation: complete
```

### AC-09 Rendering

- [ ] Preview rendering works.
- [ ] Final rendering works.
- [ ] `output/final_video.mp4` is generated.
- [ ] Render errors are displayed clearly.
- [ ] Rendering logs are stored locally.

---

# 33. Success Metrics

The project is successful when:

1. A user can import multiple camera recordings without manually editing source timecodes.
2. The recordings can be synchronized using clap timestamps.
3. The system can automatically analyse camera footage.
4. The system can produce explainable camera recommendations.
5. The system can generate an EDL with multiple camera angles.
6. The system can maintain CAM001 as a main/fallback camera when appropriate.
7. The user can approve the automated edit.
8. The system can render the approved edit into a valid MP4.
9. The final video satisfies the required validation rules.
10. The workflow can be completed locally without uploading the original footage.

---

# 34. Project Constraints

The current project is designed around:

- Python 3.11+
- Windows desktop usage
- Tkinter GUI
- FFmpeg
- ffprobe
- YOLO-based computer vision
- Two to four camera sources
- Local file processing
- Human approval before final rendering

The current project does not require a cloud backend for normal operation.

---

# 35. Deliverables

The VCut project shall provide:

```text
1. Desktop GUI
2. Command-line interface
3. Project management
4. Camera import and metadata
5. Synchronization service
6. Programme CSV import
7. Vision-based camera analysis
8. Camera recommendation
9. Automatic camera switching
10. EDL generation
11. EDL review and approval
12. Validation
13. Subtitle support
14. Audio configuration
15. FFmpeg rendering
16. Preview video
17. Final MP4 video
18. EDL JSON export
19. Audit logs
20. Automated tests
```

---

# 36. Final Product Vision

VCut aims to make multi-camera event video editing faster without removing human control.

The intended experience is:

```text
Import footage
      ↓
Synchronize once
      ↓
Describe the programme
      ↓
Let AI analyse the cameras
      ↓
Review the suggested edit
      ↓
Approve
      ↓
Render
      ↓
Final event video
```

The core product principle is:

> **Automate repetitive camera-selection work while keeping the final editorial decision under human control.**
