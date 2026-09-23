<#
Start a long job so that it survives the Claude session that started it.

    powershell -File harness/detach.ps1 "bash harness/rybka_match.sh > data/rybka_match.log 2>&1"

Everything a Claude Code tool starts on this machine lives inside a Windows job
object owned by claude.exe - `nohup` and `&` included, because they are Unix
ideas and a job object is not a process group. When the session restarts, the
job closes and Windows kills every process in it. A 400-game match against
Rybka died that way twenty minutes in, with no error in its log, and the queue
that was to follow it never started.

Win32_Process.Create asks the WMI service to start the process instead, so its
parent is WmiPrvSE.exe under services.exe, outside the job entirely. This
script does that, then checks the new process's ancestry and refuses to report
success if claude.exe is anywhere in it.

The command runs under Git Bash from the product folder. It must not contain
double quotes; use single quotes inside it. Stop a detached job by killing its
bash process tree - `taskkill /PID <pid> /T /F` - since nothing else will.
#>
param(
    [Parameter(Mandatory = $true)][string]$Command,
    [string]$Directory = ""
)

# PowerShell 5.1 leaves $PSScriptRoot empty in a param() default, so the
# product folder is worked out here instead
if (-not $Directory) { $Directory = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }

if ($Command.Contains('"')) { throw "the command must not contain double quotes" }

$bash = "C:\Program Files\Git\bin\bash.exe"
$unix = "/" + $Directory.Substring(0, 1).ToLower() + $Directory.Substring(2).Replace('\', '/')
$line = '"{0}" -lc "cd {1} && {2}"' -f $bash, $unix, $Command

$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $line; CurrentDirectory = $Directory }
if ($result.ReturnValue -ne 0) { throw "WMI could not start it (code $($result.ReturnValue))" }

Start-Sleep -Seconds 2
$chain = @()
$process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $result.ProcessId)
for ($i = 0; $i -lt 6 -and $process; $i++) {
    $chain += "{0}({1})" -f $process.Name, $process.ProcessId
    $process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $process.ParentProcessId) -ErrorAction SilentlyContinue
}
if (($chain -join " ") -match "claude") { throw "still under claude.exe: " + ($chain -join " <- ") }
"detached, pid {0}: {1}" -f $result.ProcessId, ($chain -join " <- ")
