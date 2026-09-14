#requires -Version 7.0
# Windows PowerShell 7 initializer. Launch with pwsh, not Windows PowerShell 5.1.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$env:PYTHONUTF8 = '1'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program 退出码 $LASTEXITCODE" }
}
function Test-Python {
    param([string]$Program)
    if (-not $Program) { return $false }
    try {
        & $Program -c 'import sys,struct;sys.exit(not (sys.version_info >= (3,12) and struct.calcsize(chr(80))==8))' *> $null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

try {
    if (-not $IsWindows) { throw '此脚本仅支持 Windows PowerShell 7。' }
    $PackageDirectory = $PSScriptRoot
    $Binary = Join-Path $PackageDirectory 'hugemark-windows-amd64.exe'
    $VenvDirectory = Join-Path $PackageDirectory '.venv'
    $VenvPython = Join-Path $VenvDirectory 'Scripts/python.exe'
    $Requirements = Join-Path $PackageDirectory '.hugemark-requirements.txt'
    if (-not (Test-Path -LiteralPath $Binary -PathType Leaf)) { throw "同目录缺少 hugemark-windows-amd64.exe：$Binary" }
    $Version = & $Binary --version
    if ($LASTEXITCODE -ne 0 -or "$Version" -notlike 'hugemark *') { throw '二进制不可用；请确认使用 Windows amd64 发行包。' }
    Write-Host "二进制：$Binary`n版本：$Version"
    foreach ($Resource in @('requirements-gui.txt', 'initialize_environment.py', 'gui.py', 'desktop.py', 'assets/desktop.qss', 'assets/fonts/NotoSansCJKsc-Regular.otf')) {
        if (-not (Test-Path -LiteralPath (Join-Path $PackageDirectory $Resource) -PathType Leaf)) { throw "发行包不完整，缺少 $Resource" }
    }
    $UvCommand = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $UvPath = if ($UvCommand) { $UvCommand.Source } else { $null }
    $BasePython = $null
    if (Test-Path -LiteralPath $VenvDirectory) {
        if (-not (Test-Path -LiteralPath (Join-Path $VenvDirectory 'pyvenv.cfg')) -or -not (Test-Python $VenvPython)) {
            throw '.venv 已存在但不可用（需要 64 位 Python 3.12+）；请备份或移走后重试。'
        }
        $BasePython = $VenvPython
    } else {
        foreach ($Name in @('python', 'python3')) {
            $Command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($Command -and (Test-Python $Command.Source)) { $BasePython = $Command.Source; break }
        }
        if (-not $BasePython) {
            $Launcher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($Launcher) {
                foreach ($Selector in @('-3', '-3.14', '-3.13', '-3.12')) {
                    $Candidate = & $Launcher.Source $Selector -c 'import sys; print(sys.executable)' 2>$null
                    if ($LASTEXITCODE -eq 0 -and (Test-Python "$Candidate")) { $BasePython = "$Candidate"; break }
                }
            }
        }
        if (-not $BasePython -and $UvPath) {
            $Candidate = & $UvPath python find --no-python-downloads '>=3.12' 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-Python "$Candidate")) { $BasePython = "$Candidate" }
        }
        if (-not $BasePython) { throw '找不到可用的 64 位 Python 3.12+。请先安装 Python；脚本不会自动下载解释器。' }
        if ($UvPath) {
            Invoke-Checked $UvPath @('venv', '--no-python-downloads', '--python', $BasePython, $VenvDirectory)
        } else {
            Invoke-Checked $BasePython @('-m', 'venv', $VenvDirectory)
        }
    }
    if (-not (Test-Python $VenvPython)) { throw '虚拟环境 Python 无法运行。' }
    Invoke-Checked $VenvPython @('-c', 'import pathlib,sys;assert sys.prefix != sys.base_prefix and pathlib.Path(sys.prefix).resolve() == pathlib.Path(sys.argv[1]).resolve()', $VenvDirectory)
    $RequiredPackages = & $Binary requirements
    if ($LASTEXITCODE -ne 0 -or -not $RequiredPackages) { throw '二进制未输出依赖清单。' }
    $RequiredPackages | Set-Content -LiteralPath $Requirements -Encoding utf8NoBOM
    Write-Host "`n安装全部依赖（每次执行均重新安装）…"
    $GuiRequirements = Join-Path $PackageDirectory 'requirements-gui.txt'
    if ($UvPath) {
        Invoke-Checked $UvPath @('pip', 'install', '--python', $VenvPython, '--reinstall', '-r', $Requirements, '-r', $GuiRequirements)
        Invoke-Checked $UvPath @('pip', 'check', '--python', $VenvPython)
    } else {
        Invoke-Checked $VenvPython @('-m', 'ensurepip', '--upgrade')
        Invoke-Checked $VenvPython @('-m', 'pip', 'install', '--force-reinstall', '-r', $Requirements, '-r', $GuiRequirements)
        Invoke-Checked $VenvPython @('-m', 'pip', 'check')
    }
    Invoke-Checked $VenvPython @((Join-Path $PackageDirectory 'initialize_environment.py'), $Binary)
    $Installer = $UvPath ?? 'python -m pip'
    Write-Host "`n初始化成功`n二进制：$Binary`nPython：$VenvPython`n虚拟环境：$VenvDirectory`n安装工具：$Installer`n依赖：已重新安装并通过检查"
    Write-Host "启动 GUI：`n  & '$($VenvPython.Replace("'", "''"))' '$((Join-Path $PackageDirectory 'gui.py').Replace("'", "''"))'"
    if (-not [Console]::IsInputRedirected) {
        Write-Host "`n按任意键退出…"
        $null = [Console]::ReadKey($true)
    } else { Write-Host "`n非交互输入，跳过按键等待。" }
    exit 0
} catch {
    [Console]::Error.WriteLine("初始化失败：$($_.Exception.Message)")
    exit 1
}
