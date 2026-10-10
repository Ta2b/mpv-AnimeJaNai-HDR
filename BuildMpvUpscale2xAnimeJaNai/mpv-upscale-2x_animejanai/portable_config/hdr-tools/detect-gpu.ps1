$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$adapters = @(Get-CimInstance -ClassName Win32_VideoController |
    Select-Object Name, PNPDeviceID, Status)
ConvertTo-Json -InputObject $adapters -Depth 3 -Compress
