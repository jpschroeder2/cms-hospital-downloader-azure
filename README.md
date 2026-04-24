# CMS Hospital Data Downloader

Downloads all CMS "Hospitals" datasets from data.cms.gov, converts columns to snake_case, stores timestamped CSVs in Azure Blob Storage, and supports incremental updates via metadata.json.

The solution is fully automated using **Terraform** (infrastructure) and **GitHub Actions** (deployment) with OIDC authentication — no manual secrets or long-lived credentials are required.

## Features

- Parallel downloads using `ThreadPoolExecutor` (configurable worker count)
- Incremental updates via `metadata.json` (skips unchanged datasets)
- Column names automatically converted to clean `snake_case`
- Dual triggers: scheduled Timer (daily) + manual HTTP trigger
- Fully automated infrastructure provisioning and code deployment
- Uses a User-Assigned Managed Identity + OIDC for secure, secretless authentication
- Remote Terraform state stored in Azure Blob Storage

## Architecture

- **Compute**: Azure Functions on Flex Consumption plan (Python 3.11)
- **Storage**: Azure Blob Storage (CSVs stored in `hospital-data/raw/`)
- **Infrastructure as Code**: Terraform
- **CI/CD**: GitHub Actions with OIDC (secretless)
- **Authentication**: User-Assigned Managed Identity with federated credential

## Prerequisites

- Azure subscription
- Azure CLI (`az`) installed and logged in
- Terraform CLI
- GitHub CLI (`gh`) — needed for the setup-oidc.sh script
- Python 3.11 (recommended) or 3.12+ (local development only)

**Note:** While the code may run with newer Python versions locally, currently Azure Functions Flex Consumption officially supports Python 3.11 and 3.12 best. We recommend using 3.11 for maximum compatibility.

## Methods to pull the repo

### Recommended

1. **Fork** this repository on GitHub (recommended)

2. Clone your fork:
```bash
git clone https://github.com/YOURUSERNAME/cms-hospital-downloader-azure.git
cd cms-hospital-downloader-azure
```

### Alternative (Clone + Change Remote)

1. Create a new empty repository on GitHub (do **not** initialize with README, .gitignore, or license).

2. Clone this repository:
```bash
git clone https://github.com/jpschroeder2/cms-hospital-downloader-azure.git
cd cms-hospital-downloader-azure
```

3. Update the remote to point to your new repository:
```bash
git remote set-url origin https://github.com/YOURUSERNAME/YOUR-NEW-REPO-NAME.git
```

4. Verify the origin URL has been updated:
```bash
git remote -v
```

## Local Development

1. **(Optional)** Create and activate a Python virtual environment:
```bash
uv venv --python 3.11          # or: python3.11 -m venv .venv
source .venv/bin/activate
```

2. Install the required Python packages:
```bash
pip install -r requirements.txt
```

3. Start the Azurite storage emulator:
```bash
npx azurite --silent --skipApiVersionCheck
```

4. Start the Azure Functions host:
```bash
func host start
```

5. Test the manual HTTP trigger:
```bash
curl http://localhost:7071/api/download-hospital-data
```

Data will appear in the local `hospital-data` container (visible in Azure Storage Explorer under "Emulator & Attached").

## Full Automated Deployment to Azure

1. Update `github_org` and `github_repo` variables in `infrastructure/main.tf` to your own GitHub username and repository.

2. Deploy the infrastructure with Terraform:
```bash
cd infrastructure
terraform init
terraform apply -auto-approve
cd ..
```

3. Enable remote backend to store Terraform tfstate in Azure 
```bash
cd infrastructure
mv backend.tf.disabled backend.tf
terraform init -reconfigure
cd ..
```

4. Run the one-time OIDC setup script:
```bash
chmod +x setup-oidc.sh
./setup-oidc.sh
```

5. Push to GitHub to trigger the full deployment:
```bash
git add .
git commit -m "Initial commit"
git push -u origin main
```

GitHub Actions will automatically run Terraform and deploy the Python code on every push.

## Customization

Edit `infrastructure/main.tf` to change:

- `environment` (e.g. `prod` → `test`)
- `location` (e.g. `eastus` → `westus`)
- `TIMER_SCHEDULE` (default: daily at 2 AM UTC)
- `MAX_WORKERS`
- `github_org` and `github_repo`

**Important:**  
If you change the `environment` variable, you should also update the matching values in `infrastructure/backend.tf`.

Specifically, update:
- `resource_group_name`
- `storage_account_name`

This ensures the Terraform state points to the correct Azure resources.

## Troubleshooting

- **Functions not appearing in portal:** Check the Log stream for storage authentication errors.
- **Deployment failing with storage errors:** Verify AzureWebJobsStorage is set correctly in app settings.
- **Local testing issues:** Make sure Azurite is running with --skipApiVersionCheck.