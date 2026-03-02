#!/usr/bin/env bash

# Set AWS environment variables from AWS CLI configuration
export AWS_ACCESS_KEY_ID="$(aws configure get aws_access_key_id)"
export AWS_SECRET_ACCESS_KEY="$(aws configure get aws_secret_access_key)"

echo "AWS credentials loaded into environment variables."
