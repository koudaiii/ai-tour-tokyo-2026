targetScope = 'resourceGroup'

metadata description = 'Grant the SRE Agent managed identity RBAC roles on the main application resource group (cross-RG assignment).'

@description('SRE Agent access level (must match the value used in sre-agent-resources.bicep)')
@allowed([
  'High'
  'Low'
])
param accessLevel string = 'High'

@description('Principal ID of the SRE Agent user-assigned managed identity')
param principalId string

var roleDefinitions = {
  Low: [
    '92aaf0da-9dab-42b6-94a3-d43ce8d16293' // Log Analytics Reader
    'acdd72a7-3385-48ef-bd42-f606fba81ae7' // Reader
  ]
  High: [
    '92aaf0da-9dab-42b6-94a3-d43ce8d16293' // Log Analytics Reader
    'acdd72a7-3385-48ef-bd42-f606fba81ae7' // Reader
    'b24988ac-6180-42a0-ab88-20f7382dd24c' // Contributor
  ]
}

resource roleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for roleId in roleDefinitions[accessLevel]: {
    name: guid(resourceGroup().id, principalId, roleId)
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]
