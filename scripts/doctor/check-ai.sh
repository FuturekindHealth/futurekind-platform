#!/bin/sh

echo "Checking LiteLLM..."

curl http://localhost:4000/health/liveliness

echo

echo "Checking Models..."

curl http://localhost:4000/v1/models \
-H "Authorization: Bearer $LITELLM_MASTER_KEY"