<#
.SYNOPSIS
  Serve the local Pokemon Showdown web client over HTTP and connect it to the
  local sim server.

.DESCRIPTION
  The official client is served over HTTPS, and browsers block an HTTPS page
  from opening an insecure ws://localhost socket (mixed-content). The result is
  the recurring "Couldn't connect to server" error.

  This script serves the checked-out client (pokemon-showdown-client) over plain
  HTTP so the ws://localhost:<ServerPort> connection is allowed. It verifies the
  sim server is up, the client is built, then launches a static HTTP server and
  prints the testclient URL.

  Server is rooted at the client repo (not the play.pokemonshowdown.com subfolder)
  because testclient.html loads ../config/testclient-key.js, which lives above
  that folder.

.PARAMETER Port
  HTTP port for the client. Default 8080.

.PARAMETER ServerPort
  Port the local Showdown sim server listens on. Default 8000.

.PARAMETER ClientDir
  Path to the pokemon-showdown-client checkout. Default <repo>\pokemon-showdown-client.

.PARAMETER Open
  Open the testclient URL in the default browser after the server starts.

.EXAMPLE
  .\scripts\start-local-client.ps1

.EXAMPLE
  .\scripts\start-local-client.ps1 -Port 9000 -Open
#>
[CmdletBinding()]
param(
  [int]$Port = 8080,
  [int]$ServerPort = 8000,
  [string]$ClientDir = (Join-Path $PSScriptRoot '..\pokemon-showdown-client'),
  [switch]$Open
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ClientDir = (Resolve-Path $ClientDir -ErrorAction SilentlyContinue).Path
if (-not $ClientDir -or -not (Test-Path $ClientDir)) {
  Write-Error "Client checkout not found. Clone pokemon-showdown-client next to the project."
  exit 1
}

# Verify the client is built — testclient.html needs the compiled battle.js.
$battleJs = Join-Path $ClientDir 'play.pokemonshowdown.com\js\battle.js'
if (-not (Test-Path $battleJs)) {
  Write-Warning "Client not built (missing js/battle.js)."
  Write-Host "  Build it first:  cd `"$ClientDir`"; node build" -ForegroundColor Yellow
  exit 1
}

# Warn (don't block) if the sim server is not listening yet.
$simUp = $false
try {
  $simUp = (Test-NetConnection -ComputerName 127.0.0.1 -Port $ServerPort -WarningAction SilentlyContinue).TcpTestSucceeded
} catch { $simUp = $false }

if (-not $simUp) {
  Write-Warning "No sim server on port $ServerPort."
  Write-Host "  Start it:  cd `"$ClientDir\..\pokemon-showdown`"; node pokemon-showdown start --no-security" -ForegroundColor Yellow
  Write-Host "  Continuing anyway — start the sim, then reload the browser." -ForegroundColor DarkGray
}

$url = "http://localhost:$Port/play.pokemonshowdown.com/testclient.html?~~localhost:$ServerPort"

Write-Host ""
Write-Host "Local Showdown client" -ForegroundColor Cyan
Write-Host "  Serving : $ClientDir  (HTTP :$Port)"
Write-Host "  Sim     : ws://localhost:$ServerPort  [$(if ($simUp) {'UP'} else {'DOWN'})]"
Write-Host "  Open    : $url" -ForegroundColor Green
Write-Host "  Stop    : Ctrl+C"
Write-Host ""

if ($Open) { Start-Process $url }

# Foreground, blocking — Ctrl+C stops it. Bound to loopback only.
Push-Location $ClientDir
try {
  python -m http.server $Port --bind 127.0.0.1
} finally {
  Pop-Location
}
