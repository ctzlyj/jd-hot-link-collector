﻿param(
  [string]$Stage = "D:\caotong.888\Desktop\京东链接搬运\.collector_state",
  [int]$Minutes = 5
)
$end = (Get-Date).AddMinutes($Minutes)
$lastPhase = $null
while((Get-Date) -lt $end){
  Start-Sleep -Seconds 30
  $s = Get-Content (Join-Path $Stage "runner_state.json") -Raw -Encoding UTF8 -ErrorAction SilentlyContinue | ConvertFrom-Json
  $d = Get-Content (Join-Path $Stage "batch_driver_state.json") -Raw -Encoding UTF8 -ErrorAction SilentlyContinue | ConvertFrom-Json
  $phase = if($d){ "$($d.phase)/$($d.workPhase)" } else { "?" }
  $line = ("[{0}] driver={1} runner={2} req={3} ok={4} partial={5} prod={6}/{7} nav={8} rounds={9}" -f (Get-Date -Format HH:mm:ss),$phase,$s.state,$s.requests,$s.successful,$s.partial,$s.products,$s.sourceProducts,$s.navigations,$d.rounds)
  if($phase -ne $lastPhase){ Write-Output $line; $lastPhase = $phase }
  elseif($s.state -ne 'RUNNING'){ Write-Output $line }
  if($d.phase -in @('DONE','BLOCKED_PLATFORM','BLOCKED_UNKNOWN','BLOCKED_MATERIAL','BLOCKED_STALL','BLOCKED_DRIVER','BLOCKED_LOCK','AWAITING_PRICE_DECISION')){ break }
}
$k = Get-Content (Join-Path $Stage "keeper_state.json") -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Output ("keeper: {0} reason={1}" -f $k.state,$k.reason)
if(Test-Path (Join-Path $Stage "independent_validation.json")){
  $v = Get-Content (Join-Path $Stage "independent_validation.json") -Raw -Encoding UTF8 | ConvertFrom-Json
  Write-Output ("validation: scope={0} complete={1} counts={2}" -f $v.scope,$v.complete,(($v.counts.PSObject.Properties | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ' '))
}
