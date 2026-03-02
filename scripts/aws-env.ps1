# Set AWS environment variables from AWS CLI configuration
$env:AWS_ACCESS_KEY_ID = $(aws configure get aws_access_key_id)
$env:AWS_SECRET_ACCESS_KEY = $(aws configure get aws_secret_access_key)

Write-Host "AWS credentials loaded into environment variables."
