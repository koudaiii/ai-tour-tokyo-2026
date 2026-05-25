targetScope = 'resourceGroup'

metadata description = 'Deploy Azure SRE Agent (Microsoft.App/agents) and its user-assigned managed identity. Based on https://github.com/koudaiii/azure-sre-agent-sandbox'

@description('The Azure region for the SRE Agent (must support Microsoft.App/agents)')
param location string

@description('Tags to apply to SRE Agent resources')
param tags object = {}

@description('SRE Agent name')
param agentName string

@description('Access level (High = Reader + Contributor + Log Analytics Reader, Low = Reader + Log Analytics Reader)')
@allowed([
  'High'
  'Low'
])
param accessLevel string = 'High'

@description('Action mode (Review = require approval before remediation; Automatic = auto-execute)')
@allowed([
  'Review'
  'Automatic'
])
param actionMode string = 'Review'

@description('Application Insights App ID (GUID) for log configuration')
param appInsightsAppId string

@description('Application Insights connection string for log configuration')
@secure()
param appInsightsConnectionString string

@description('Resource IDs to add to the SRE Agent knowledge graph (e.g., Container App, PostgreSQL)')
param managedResourceIds array = []

var uniqueSuffix = uniqueString(resourceGroup().id, agentName)
var identityName = 'id-${agentName}-${take(uniqueSuffix, 6)}'

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: identityName
  location: location
  tags: tags
}

#disable-next-line BCP081
resource sreAgent 'Microsoft.App/agents@2025-05-01-preview' = {
  name: agentName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    knowledgeGraphConfiguration: {
      identity: managedIdentity.id
      managedResources: managedResourceIds
    }
    actionConfiguration: {
      accessLevel: accessLevel
      identity: managedIdentity.id
      mode: actionMode
    }
    logConfiguration: {
      applicationInsightsConfiguration: {
        appId: appInsightsAppId
        connectionString: appInsightsConnectionString
      }
    }
  }
}

@description('SRE Agent name')
output agentName string = sreAgent.name

@description('SRE Agent resource ID')
output agentId string = sreAgent.id

@description('SRE Agent portal URL')
output agentPortalUrl string = 'https://portal.azure.com/#view/Microsoft_Azure_PaasServerless/AgentFrameBlade.ReactView/id/${replace(sreAgent.id, '/', '%2F')}'

@description('User-assigned managed identity resource ID')
output managedIdentityId string = managedIdentity.id

@description('User-assigned managed identity principal ID (used for RBAC assignments)')
output managedIdentityPrincipalId string = managedIdentity.properties.principalId
