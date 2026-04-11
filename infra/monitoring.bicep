targetScope = 'resourceGroup'

@description('The Azure region for monitoring resource deployment')
param location string

@description('Tags to apply to monitoring resources')
param tags object = {}

@description('Log Analytics workspace name')
param logAnalyticsWorkspaceName string

@description('Application Insights name')
param appInsightsName string

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
  }
}

@description('Log Analytics workspace resource ID')
output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id

@description('Log Analytics workspace customer ID (GUID)')
output logAnalyticsWorkspaceCustomerId string = logAnalyticsWorkspace.properties.customerId

@description('Application Insights connection string')
output appInsightsConnectionString string = appInsights.properties.ConnectionString

@description('Application Insights instrumentation key')
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey
