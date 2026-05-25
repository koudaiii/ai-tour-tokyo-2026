targetScope = 'resourceGroup'

@description('The Azure region for resource deployment')
param location string

@description('Tags to apply to resources')
param tags object = {}

@description('Name of the Function App')
param functionAppName string

@description('Name of the App Service Plan for the Function App')
param appServicePlanName string

@description('Name of the Storage Account for Azure Functions runtime')
@minLength(3)
@maxLength(24)
param functionsStorageAccountName string

@description('Base URL of the Container App API (e.g. https://aca-xxx.azurecontainerapps.io)')
param apiBaseUrl string

@description('PostgreSQL connection string used by the MCP DB inspection tool')
@secure()
param postgresDatabaseUrl string

@description('Resource ID of the VNet integration subnet (delegated to Microsoft.App/environments)')
param virtualNetworkSubnetId string

@description('Application Insights connection string for monitoring')
param appInsightsConnectionString string = ''

@description('Name of the blob container used by Flex Consumption for deployment packages')
param deploymentPackageContainerName string = 'app-package'

var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

////////////
// Storage Account for Azure Functions runtime + Flex Consumption deployment package
////////////
resource functionsStorageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: functionsStorageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-01-01' = {
  parent: functionsStorageAccount
  name: 'default'
  properties: {}
}

resource deploymentPackageContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: deploymentPackageContainerName
  properties: {
    publicAccess: 'None'
  }
}

////////////
// App Service Plan (Flex Consumption FC1)
////////////
resource appServicePlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: appServicePlanName
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

////////////
// Function App (Flex Consumption, VNet integrated)
////////////
resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    virtualNetworkSubnetId: virtualNetworkSubnetId
    vnetRouteAllEnabled: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${functionsStorageAccount.properties.primaryEndpoints.blob}${deploymentPackageContainerName}'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 100
        instanceMemoryMB: 2048
      }
    }
    siteConfig: {
      appSettings: [
        {
          name: 'AzureWebJobsStorage__accountName'
          value: functionsStorageAccount.name
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'API_BASE_URL'
          value: apiBaseUrl
        }
        {
          name: 'ISUCONP_DATABASE_URL'
          value: postgresDatabaseUrl
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsightsConnectionString
        }
      ]
    }
  }
  dependsOn: [
    deploymentPackageContainer
  ]
}

////////////
// RBAC: grant the Function App MI access to its own deployment storage
////////////
resource storageBlobDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorageAccount.id, functionApp.id, storageBlobDataContributorRoleId)
  scope: functionsStorageAccount
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
  }
}

////////////
// Outputs
////////////
@description('Function App name')
output functionAppName string = functionApp.name

@description('Function App default hostname')
output functionAppHostname string = functionApp.properties.defaultHostName

@description('Function App URL')
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'

@description('MCP SSE endpoint URL')
output mcpEndpointUrl string = 'https://${functionApp.properties.defaultHostName}/runtime/webhooks/mcp/sse'
