[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('check-system', 'gui', 'test', 'create-project', 'show-project')]
    [string]$Command = 'gui',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments
)

$projectRoot = $PSScriptRoot
$bundledPython = 'C:\Users\Asus\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue

if ($pythonCommand) {
    $pythonExecutable = $pythonCommand.Source
} elseif (Test-Path -LiteralPath $bundledPython) {
    $pythonExecutable = $bundledPython
} else {
    throw 'Python 3.11 or newer was not found. Install Python with Tcl/Tk support and try again.'
}

$existingPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
$sourcePath = Join-Path $projectRoot 'src'
$env:PYTHONPATH = if ($existingPythonPath) {
    "$sourcePath$([IO.Path]::PathSeparator)$existingPythonPath"
} else {
    $sourcePath
}

switch ($Command) {
    'gui' {
        & $pythonExecutable -m vcut.gui @CommandArguments
    }
    'test' {
        & $pythonExecutable -m unittest discover -s (Join-Path $projectRoot 'tests') -v @CommandArguments
    }
    default {
        & $pythonExecutable -m vcut.cli $Command @CommandArguments
    }
}

exit $LASTEXITCODE
