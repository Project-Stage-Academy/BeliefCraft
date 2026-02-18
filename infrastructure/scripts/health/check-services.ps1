$services = @(
  @{ Name = "environment-api"; Url = "http://localhost:8000/health" },
  @{ Name = "rag-service"; Url = "http://localhost:8001/health" },
  @{ Name = "agent-service"; Url = "http://localhost:8003/health" },
  @{ Name = "ui"; Url = "http://localhost:3000/health" }
)

$failed = $false

foreach ($service in $services) {
  try {
    $response = Invoke-WebRequest -Uri $service.Url -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
      Write-Host "[OK] $($service.Name)"
    }
    else {
      Write-Host "[FAIL] $($service.Name): status $($response.StatusCode)"
      $failed = $true
    }
  }
  catch {
    Write-Host "[FAIL] $($service.Name): $($_.Exception.Message)"
    $failed = $true
  }
}

if ($failed) { exit 1 }
