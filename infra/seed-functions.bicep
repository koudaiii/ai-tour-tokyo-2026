targetScope = 'resourceGroup'

@description('The Azure region for resource deployment')
param location string

@description('Tags to apply to resources')
param tags object = {}

@description('Name of the seed Function App')
param functionAppName string

@description('Name of the App Service Plan for the seed Function App')
param appServicePlanName string

@description('Name of the Storage Account for seed Azure Functions runtime')
@minLength(3)
@maxLength(24)
param functionsStorageAccountName string

@description('Base URL of the Container App API (e.g. https://aca-xxx.azurecontainerapps.io)')
param apiBaseUrl string

@description('Azure Blob Storage account URL')
param azureStorageAccountUrl string

@description('Azure Blob Storage account resource ID')
param azureStorageAccountResourceId string

@description('Azure Blob Storage container name')
param azureStorageContainerName string = 'images'

@description('Default number of posts to create for one seed run')
param seedPostCount int = 100

@description('Application Insights connection string for monitoring')
param appInsightsConnectionString string = ''

@description('Timer trigger schedule in NCRONTAB format (e.g. "0 0 0 * * *" = daily midnight UTC)')
param seedTimerSchedule string = '0 0 0 * * *'

@description('Disable the seed timer trigger (true to disable)')
param seedTimerDisabled bool = true

var functionAppBaseSettings = [
  {
    name: 'AzureWebJobsStorage'
    value: 'DefaultEndpointsProtocol=https;AccountName=${functionsStorageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${functionsStorageAccount.listKeys().keys[0].value}'
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
  {
    name: 'AZURE_STORAGE_ACCOUNT_URL'
    value: azureStorageAccountUrl
  }
  {
    name: 'AZURE_STORAGE_CONTAINER_NAME'
    value: azureStorageContainerName
  }
  {
    name: 'SEED_POST_COUNT'
    value: string(seedPostCount)
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: appInsightsConnectionString
  }
  {
    name: 'SEED_TIMER_SCHEDULE'
    value: seedTimerSchedule
  }
  {
    name: 'AzureWebJobs.seed_timer.Disabled'
    value: string(seedTimerDisabled)
  }
]
var functionAppContentSettings = [
  {
    name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING'
    value: 'DefaultEndpointsProtocol=https;AccountName=${functionsStorageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${functionsStorageAccount.listKeys().keys[0].value}'
  }
  {
    name: 'WEBSITE_CONTENTSHARE'
    value: toLower(functionAppName)
  }
]

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
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  kind: 'functionapp,linux'
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      appSettings: concat(functionAppBaseSettings, functionAppContentSettings)
    }
  }
}

resource storageAccountResource 'Microsoft.Storage/storageAccounts@2025-01-01' existing = {
  scope: resourceGroup()
  name: last(split(azureStorageAccountResourceId, '/'))
}

resource seedFunctionStorageBlobDataContributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(azureStorageAccountResourceId, functionAppName, 'Storage Blob Data Contributor')
  scope: storageAccountResource
  properties: {
    principalId: functionApp.identity.principalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
    principalType: 'ServicePrincipal'
  }
}

@description('Seed Function App name')
output functionAppName string = functionApp.name

@description('Seed Function App URL')
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
