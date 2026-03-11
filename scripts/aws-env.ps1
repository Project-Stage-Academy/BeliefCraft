# Set AWS environment variables from AWS CLI configuration.
# Uses AWS_PROFILE if set, otherwise the default profile.
#   $env:AWS_PROFILE = "softserve-datascienceinternship-teamproject"; . .\scripts\aws-env.ps1

$profileFlag = @()
if ($env:AWS_PROFILE) { $profileFlag = @("--profile", $env:AWS_PROFILE) }

$env:AWS_ACCESS_KEY_ID     = & aws configure get aws_access_key_id @profileFlag
$env:AWS_SECRET_ACCESS_KEY = & aws configure get aws_secret_access_key @profileFlag

$profile = if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { "default" }
Write-Host "AWS credentials loaded (profile: $profile)."
