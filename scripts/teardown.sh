#!/usr/bin/env bash
# Delete every Azure resource created by provision.sh (the whole resource group).
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-policy-qa}"

echo "Deleting resource group '$RESOURCE_GROUP' and ALL resources inside it."
read -r -p "Continue? [y/N] " confirm
if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
  az group delete --name "$RESOURCE_GROUP" --yes --no-wait
  echo "Deletion started (runs in the background)."
else
  echo "Aborted."
fi
