[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Pdf,
    [Parameter(Mandatory = $true)][string]$Visual,
    [Parameter(Mandatory = $true)][string]$Durations
)

$ErrorActionPreference = "Stop"
$presentation = $null
$visualPresentation = $null
$powerpoint = New-Object -ComObject PowerPoint.Application
try {
    $durationsList = Get-Content -Raw -Encoding UTF8 $Durations | ConvertFrom-Json
    $presentation = $powerpoint.Presentations.Open($Source, $false, $true, $false)
    $presentation.SaveAs($Pdf, 32)
    if (Test-Path $Visual) { Remove-Item $Visual -Force }
    for ($index = 1; $index -le $presentation.Slides.Count; $index++) {
        $slide = $presentation.Slides.Item($index)
        $slide.SlideShowTransition.AdvanceOnClick = 0
        $slide.SlideShowTransition.AdvanceOnTime = -1
        $slide.SlideShowTransition.AdvanceTime = [single]$durationsList[$index - 1]
    }
    $presentation.SaveAs($Visual, 24)
    $presentation.Close()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($presentation) | Out-Null
    $presentation = $null

    $visualPresentation = $powerpoint.Presentations.Open($Visual, $true, $false, $false)
    $videoPath = [System.IO.Path]::ChangeExtension($Visual, ".rendered.mp4")
    if (Test-Path $videoPath) { Remove-Item $videoPath -Force }
    $visualPresentation.CreateVideo($videoPath, $true, 5, 1080, 30, 85)
    $status = 1
    while ($status -eq 1) {
        Start-Sleep -Seconds 5
        $status = [int]$visualPresentation.CreateVideoStatus
    }
    if ($status -ne 3) { throw "PowerPoint CreateVideo failed with status $status" }
    $visualPresentation.Close()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($visualPresentation) | Out-Null
    $visualPresentation = $null
    Move-Item -Force $videoPath ([System.IO.Path]::ChangeExtension($Visual, ".mp4"))
}
finally {
    if ($presentation) { $presentation.Close(); [System.Runtime.Interopservices.Marshal]::ReleaseComObject($presentation) | Out-Null }
    if ($visualPresentation) { $visualPresentation.Close(); [System.Runtime.Interopservices.Marshal]::ReleaseComObject($visualPresentation) | Out-Null }
    $powerpoint.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($powerpoint) | Out-Null
}
