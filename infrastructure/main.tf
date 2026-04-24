# infrastructure/main.tf
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
}

data "azurerm_client_config" "current" {}

variable "location" {
  default = "eastus"
}

variable "environment" {
  default = "prod"
}

variable "github_org" {
  default = "jpschroeder2"
}

variable "github_repo" {
  default = "cms-hospital-downloader-azure"
}

resource "azurerm_resource_group" "rg" {
  name     = "cms-hospital-rg-${var.environment}"
  location = var.location
}

resource "azurerm_storage_account" "storage" {
  name                     = "cmshospitalstorage${var.environment}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

# Container for Terraform state (remote backend)
resource "azurerm_storage_container" "tfstate" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.storage.id
  container_access_type = "private"
}

# Container for Function App code
resource "azurerm_storage_container" "function" {
  name                  = "function-app"
  storage_account_id    = azurerm_storage_account.storage.id
  container_access_type = "private"
}

resource "azurerm_service_plan" "plan" {
  name                = "cms-hospital-plan-${var.environment}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "FC1"
}

# User-Assigned Managed Identity (cleaner for OIDC)
resource "azurerm_user_assigned_identity" "main" {
  name                = "mi-cms-hospital-fetcher"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
}

resource "azurerm_function_app_flex_consumption" "function" {
  name                = "cms-hospital-fetcher-${var.environment}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  service_plan_id = azurerm_service_plan.plan.id

  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.storage.primary_blob_endpoint}${azurerm_storage_container.function.name}"
  storage_authentication_type = "UserAssignedIdentity"
  storage_user_assigned_identity_id = azurerm_user_assigned_identity.main.id   # ← This was the missing line

  runtime_name    = "python"
  runtime_version = "3.11"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.main.id]
  }

  app_settings = {
    "AzureWebJobsStorage" = azurerm_storage_account.storage.primary_connection_string
    "MAX_WORKERS"    = "12"
    "TIMER_SCHEDULE" = "0 0 2 * * *"
  }

  site_config {
    minimum_tls_version               = "1.2"
    http2_enabled                     = true
    ip_restriction_default_action     = "Allow"
    scm_ip_restriction_default_action = "Allow"
    scm_minimum_tls_version           = "1.2"
    vnet_route_all_enabled            = false
  }
}

# Role Assignments - required for deployment
resource "azurerm_role_assignment" "rg_contributor" {
  scope                = azurerm_resource_group.rg.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.main.principal_id
}

resource "azurerm_role_assignment" "storage_blob_owner" {
  scope                = azurerm_storage_account.storage.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azurerm_user_assigned_identity.main.principal_id
}

resource "azurerm_federated_identity_credential" "github" {
  name                = "github-actions-cred"
  resource_group_name = azurerm_resource_group.rg.name
  parent_id           = azurerm_user_assigned_identity.main.id
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/main"
  audience            = ["api://AzureADTokenExchange"]
}

# Outputs
output "function_app_name"    { value = azurerm_function_app_flex_consumption.function.name }
output "client_id"            { value = azurerm_user_assigned_identity.main.client_id }
output "tenant_id"            { value = azurerm_user_assigned_identity.main.tenant_id }
output "subscription_id"      { value = data.azurerm_client_config.current.subscription_id }
output "managed_identity_id"  { value = azurerm_user_assigned_identity.main.principal_id }