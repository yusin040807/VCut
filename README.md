# VCut

VCut is a local-first, human-supervised assistant for planning and rendering a
two-to-four-camera kindergarten graduation video. It provides project storage,
manual clap synchronization, programme/SRT import, explainable camera choices,
an editable and approval-gated EDL, a Tkinter workflow, and safe FFmpeg command
construction.

## Run VCut

The launcher resolves the project location automatically, so it works even when
the current PowerShell directory is somewhere else:

```powershell
& 'C:\Users\Asus\Documents\SPI\vcut.ps1' check-system
& 'C:\Users\Asus\Documents\SPI\vcut.ps1' test
& 'C:\Users\Asus\Documents\SPI\vcut.ps1' gui
```

Alternatively, when running the Python module directly, first change to the
repository and add its `src` folder to `PYTHONPATH`:

```powershell
Set-Location 'C:\Users\Asus\Documents\SPI'
$python = 'C:\Users\Asus\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = "$PWD\src"
& $python -m vcut.cli check-system
& $python -m unittest discover -s tests -v
```

Run `check-system` first. Launch the desktop workflow with
`& $python -m vcut.gui` only when it reports Tkinter, FFmpeg, and ffprobe as OK.
To make the direct module command available from every directory, install this
workspace once in editable mode:

```powershell
& $python -m pip install --no-build-isolation --editable 'C:\Users\Asus\Documents\SPI'
```

Imported footage remains local and is never uploaded by VCut.
