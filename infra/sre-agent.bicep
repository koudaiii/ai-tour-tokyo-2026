////////////
// Metadata
////////////
targetScope = 'subscription'

metadata description = 'Deploy Azure SRE Agent for private-isu and grant RBAC on the existing application resource group.'

////////////
// Parameters
////////////
@description('Azure region for the SRE Agent (must support Microsoft.App/agents)')
@allowed([
  'australiaeast'
  'canadacentral'
  'centralus'
  'eastasia'
  'eastus2'
  'francecentral'
  'italynorth'
  'japaneast'
  'koreacentral'
  'northcentralus'
  'southafricanorth'
  'southeastasia'
  'spaincentral'
  'swedencentral'
  'uksouth'
  'westcentralus'
  'westus2'
  'westus3'
])
param location string = 'japaneast'

@description('Date suffix for resource group name (YYYYMMDDHHmm format)')
param nowYyyymmddHhmm string

@description('Workload code used in resource names')
@minLength(2)
@maxLength(4)
param workloadCode string = 'pisu'

@description('Deployment environment used in resource names')
param deploymentEnvironment string = 'sandbox'

@description('Region code used in resource names')
@minLength(2)
@maxLength(4)
param regionCode string = 'jpe'

@description('Name of the existing application resource group (Container App, PostgreSQL, App Insights, etc.) to monitor')
param mainResourceGroupName string

@description('SRE Agent name')
param sreAgentName string = 'sre-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(nowYyyymmddHhmm, 2, 10)}'

@description('Application Insights App ID (GUID) for SRE Agent log configuration')
param appInsightsAppId string

@description('Application Insights connection string for SRE Agent log configuration')
@secure()
param appInsightsConnectionString string

@description('Resource IDs to add to SRE Agent knowledge graph (Container App, PostgreSQL Flexible Server, etc.)')
param managedResourceIds array = []

@description('Access level for the SRE Agent managed identity')
@allowed([
  'High'
  'Low'
])
param accessLevel string = 'High'

@description('SRE Agent remediation mode')
@allowed([
  'Review'
  'Automatic'
])
param actionMode string = 'Review'

@description('Tags to apply to all resources')
param tags object = {}

////////////
// Variables
////////////
var sreResourceGroupName = 'rg-${workloadCode}-sre-${deploymentEnvironment}-${regionCode}-${substring(nowYyyymmddHhmm, 2, 10)}'

////////////
// Resources / Modules
////////////
resource sreRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: sreResourceGroupName
  location: location
  tags: tags
}

module sreAgent 'sre-agent-resources.bicep' = {
  name: 'sreAgentResourcesDeployment'
  scope: sreRg
  params: {
    location: location
    tags: tags
    agentName: sreAgentName
    accessLevel: accessLevel
    actionMode: actionMode
    appInsightsAppId: appInsightsAppId
    appInsightsConnectionString: appInsightsConnectionString
    managedResourceIds: managedResourceIds
  }
}

module sreAgentRbac 'sre-agent-rbac.bicep' = {
  name: 'sreAgentRbacDeployment'
  scope: resourceGroup(mainResourceGroupName)
  params: {
    accessLevel: accessLevel
    principalId: sreAgent.outputs.managedIdentityPrincipalId
  }
}

////////////
// Outputs
////////////
@description('SRE Agent resource group name')
output sreResourceGroupName string = sreRg.name

@description('SRE Agent name')
output sreAgentName string = sreAgent.outputs.agentName

@description('SRE Agent resource ID')
output sreAgentId string = sreAgent.outputs.agentId

@description('SRE Agent portal URL')
output sreAgentPortalUrl string = sreAgent.outputs.agentPortalUrl

@description('SRE Agent user-assigned managed identity resource ID')
output sreAgentManagedIdentityId string = sreAgent.outputs.managedIdentityId

@description('SRE Agent user-assigned managed identity principal ID')
output sreAgentManagedIdentityPrincipalId string = sreAgent.outputs.managedIdentityPrincipalId
