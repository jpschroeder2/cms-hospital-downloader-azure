#!/bin/bash
set -e

echo "=== Reading Terraform outputs from infrastructure/ ==="

cd infrastructure

CLIENT_ID=$(terraform output -raw client_id)
TENANT_ID=$(terraform output -raw tenant_id)
SUBSCRIPTION_ID=$(terraform output -raw subscription_id)

cd ..

echo "✅ Terraform outputs read successfully:"
echo "   Client ID       : $CLIENT_ID"
echo "   Tenant ID       : $TENANT_ID"
echo "   Subscription ID : $SUBSCRIPTION_ID"

# Set GitHub repository secrets
echo "Setting GitHub Actions secrets..."
gh secret set AZURE_CLIENT_ID       -b "$CLIENT_ID"
gh secret set AZURE_TENANT_ID       -b "$TENANT_ID"
gh secret set AZURE_SUBSCRIPTION_ID -b "$SUBSCRIPTION_ID"

echo ""
echo "🎉 Setup completed successfully!"
echo "   → All three GitHub secrets have been created"
echo ""
echo "Next step:"
echo "   git add . && git commit -m \"OIDC setup complete\" && git push"
echo "This will trigger the full code deployment via GitHub Actions."