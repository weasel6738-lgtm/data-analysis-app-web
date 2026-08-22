# Azure deployment

## Container Apps with Bicep

The production image serves the built React app and FastAPI on port 8000 as a
non-root user.

```powershell
az group create --name rg-fabriq-demo --location koreacentral
az acr create --resource-group rg-fabriq-demo --name <uniqueAcr> --sku Basic
az acr login --name <uniqueAcr>
docker build -t <uniqueAcr>.azurecr.io/fabriq:1.0.0 .
docker push <uniqueAcr>.azurecr.io/fabriq:1.0.0
az deployment group create `
  --resource-group rg-fabriq-demo `
  --template-file infra/main.bicep `
  --parameters acrName=<uniqueAcr> imageName=fabriq:1.0.0
```

The template creates a user-assigned managed identity, grants it `AcrPull`, and
uses that identity for the private registry. No registry password is stored.

## Production configuration

Use Container Apps secrets or Key Vault references; never place credentials in
Bicep parameter files or source control.

```powershell
az containerapp secret set --name <app> --resource-group rg-fabriq-demo `
  --secrets aoai-key="<value>"
az containerapp update --name <app> --resource-group rg-fabriq-demo `
  --set-env-vars ORCHESTRATOR_PROVIDER=microsoft-agent `
    AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com `
    AZURE_OPENAI_DEPLOYMENT=<deployment> `
    AZURE_OPENAI_API_KEY=secretref:aoai-key
```

To include the optional AI packages in a custom production image, add
`backend/requirements-ai.txt` to the Docker install step or use:

```powershell
docker build --build-arg INSTALL_AI=true -t fabriq:ai .
```

Restrict CORS when the frontend is hosted separately. Configure custom domains,
TLS, Entra ID authentication, Log Analytics alerts, minimum replicas and
organization-approved network egress before handling operational data.

## Smoke checks

```powershell
curl https://<app-fqdn>/api/health
curl https://<app-fqdn>/api/config
```

The health endpoint must return `status=ok`; the config endpoint must not expose
keys or tokens. Verify the synthetic banner before sharing a demo.
