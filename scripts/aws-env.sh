#!/usr/bin/env bash

# Set AWS environment variables from AWS CLI configuration.
# Uses AWS_PROFILE if set, otherwise the default profile.
#   AWS_PROFILE=softserve-datascienceinternship-teamproject . scripts/aws-env.sh

PROFILE_FLAG=()
[[ -n "${AWS_PROFILE:-}" ]] && PROFILE_FLAG=(--profile "$AWS_PROFILE")

export AWS_ACCESS_KEY_ID="$(aws configure get aws_access_key_id "${PROFILE_FLAG[@]}")"
export AWS_SECRET_ACCESS_KEY="$(aws configure get aws_secret_access_key "${PROFILE_FLAG[@]}")"

echo "AWS credentials loaded (profile: ${AWS_PROFILE:-default})."
