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

////////////
// Storage Account for Azure Functions runtime
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

////////////
// App Service Plan (Consumption Y1)
////////////
resource appServicePlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: appServicePlanName
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  properties: {
    reserved: true // Linux
  }
}

////////////
// Function App
////////////
resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${functionsStorageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${functionsStorageAccount.listKeys().keys[0].value}'
        }
        {
          name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING'
          value: 'DefaultEndpointsProtocol=https;AccountName=${functionsStorageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${functionsStorageAccount.listKeys().keys[0].value}'
        }
        {
          name: 'WEBSITE_CONTENTSHARE'
          value: toLower(functionAppName)
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'API_BASE_URL'
          value: apiBaseUrl
        }
      ]
    }
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
