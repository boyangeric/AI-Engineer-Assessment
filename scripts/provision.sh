#!/usr/bin/env bash
# Provision the minimal Azure resources for the policy Q&A system.
# Idempotent: safe to re-run. Requires: az CLI, an active `az login` session.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-policy-qa}"
LOCATION="${LOCATION:-eastus2}"
AOAI_NAME="${AOAI_NAME:-aoai-policy-qa-$RANDOM}"
SEARCH_NAME="${SEARCH_NAME:-search-policy-qa-$RANDOM}"
SEARCH_SKU="${SEARCH_SKU:-basic}"
SEMANTIC_SEARCH_PLAN="${SEMANTIC_SEARCH_PLAN:-free}" # first 1,000 semantic queries/month
SEARCH_LOCATION="${SEARCH_LOCATION:-australiaeast}"
CHAT_MODEL="${CHAT_MODEL:-gpt-5-mini}"
CHAT_MODEL_VERSION="${CHAT_MODEL_VERSION:-2025-08-07}"

echo ">> Resource group: $RESOURCE_GROUP ($LOCATION)"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# Reuse existing resources on re-run if names were exported.
existing_aoai=$(az cognitiveservices account list -g "$RESOURCE_GROUP" \
  --query "[?kind=='OpenAI'] | [0].name" -o tsv)
if [[ -n "$existing_aoai" ]]; then AOAI_NAME="$existing_aoai"; fi
# Free services can't be upgraded to Basic. Reuse only a service whose SKU
# matches the requested tier; otherwise create a new service.
existing_search=$(az search service list -g "$RESOURCE_GROUP" \
  --query "[?sku.name=='$SEARCH_SKU'] | [0].name" -o tsv)
if [[ -n "$existing_search" ]]; then SEARCH_NAME="$existing_search"; fi

echo ">> Azure OpenAI: $AOAI_NAME"
az cognitiveservices account create \
  --name "$AOAI_NAME" --resource-group "$RESOURCE_GROUP" --location "$LOCATION" \
  --kind OpenAI --sku S0 --custom-domain "$AOAI_NAME" --output none

echo ">> Deploying $CHAT_MODEL"
az cognitiveservices account deployment create \
  --name "$AOAI_NAME" --resource-group "$RESOURCE_GROUP" \
  --deployment-name "$CHAT_MODEL" --model-name "$CHAT_MODEL" \
  --model-version "$CHAT_MODEL_VERSION" --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 50 --output none || echo "   (deployment exists)"

echo ">> Deploying text-embedding-3-small"
az cognitiveservices account deployment create \
  --name "$AOAI_NAME" --resource-group "$RESOURCE_GROUP" \
  --deployment-name text-embedding-3-small --model-name text-embedding-3-small \
  --model-version "1" --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 50 --output none || echo "   (deployment exists)"

echo ">> Azure AI Search: $SEARCH_NAME (sku: $SEARCH_SKU, $SEARCH_LOCATION)"
az search service create \
  --name "$SEARCH_NAME" --resource-group "$RESOURCE_GROUP" \
  --sku "$SEARCH_SKU" --location "$SEARCH_LOCATION" \
  --semantic-search "$SEMANTIC_SEARCH_PLAN" --output none || echo "   (service exists)"

AOAI_ENDPOINT=$(az cognitiveservices account show -n "$AOAI_NAME" -g "$RESOURCE_GROUP" \
  --query "properties.endpoint" -o tsv)
AOAI_KEY=$(az cognitiveservices account keys list -n "$AOAI_NAME" -g "$RESOURCE_GROUP" \
  --query "key1" -o tsv)
SEARCH_KEY=$(az search admin-key show --service-name "$SEARCH_NAME" -g "$RESOURCE_GROUP" \
  --query "primaryKey" -o tsv)

cat <<EOF

>> Done. Add these values to your local .env only (do not commit it):

AZURE_OPENAI_ENDPOINT=$AOAI_ENDPOINT
AZURE_OPENAI_API_KEY=$AOAI_KEY
AZURE_OPENAI_CHAT_DEPLOYMENT=$CHAT_MODEL
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
AZURE_SEARCH_ENDPOINT=https://$SEARCH_NAME.search.windows.net
AZURE_SEARCH_API_KEY=$SEARCH_KEY
USE_SEMANTIC_RANKER=true
EOF
