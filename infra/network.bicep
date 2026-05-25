targetScope = 'resourceGroup'

@description('The Azure region for network resource deployment')
param location string

@description('Tags to apply to network resources')
param tags object = {}

@description('Virtual network name for private connectivity')
param virtualNetworkName string

@description('Address prefix for the virtual network')
param virtualNetworkAddressPrefix string

@description('Address prefix for the Container Apps infrastructure subnet')
param containerAppsInfrastructureSubnetPrefix string

@description('Address prefix for the PostgreSQL private endpoint subnet')
param postgresPrivateEndpointSubnetPrefix string

@description('Address prefix for the Functions VNet integration subnet (Flex Consumption)')
param functionAppVnetIntegrationSubnetPrefix string

resource virtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: virtualNetworkName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        virtualNetworkAddressPrefix
      ]
    }
    subnets: [
      {
        name: 'aca-infra'
        properties: {
          addressPrefix: containerAppsInfrastructureSubnetPrefix
          delegations: [
            {
              name: 'aca-infra-delegation'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'postgres-pe'
        properties: {
          addressPrefix: postgresPrivateEndpointSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'func-vnet-int'
        properties: {
          addressPrefix: functionAppVnetIntegrationSubnetPrefix
          delegations: [
            {
              name: 'func-vnet-int-delegation'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
    ]
  }
}

resource postgresPrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource postgresPrivateDnsZoneVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: postgresPrivateDnsZone
  name: 'link-${virtualNetworkName}'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: virtualNetwork.id
    }
  }
}

output virtualNetworkResourceId string = virtualNetwork.id
output containerAppsInfrastructureSubnetResourceId string = resourceId(
  'Microsoft.Network/virtualNetworks/subnets',
  virtualNetwork.name,
  'aca-infra'
)
output postgresPrivateEndpointSubnetResourceId string = resourceId(
  'Microsoft.Network/virtualNetworks/subnets',
  virtualNetwork.name,
  'postgres-pe'
)
output functionAppVnetIntegrationSubnetResourceId string = resourceId(
  'Microsoft.Network/virtualNetworks/subnets',
  virtualNetwork.name,
  'func-vnet-int'
)
output postgresPrivateDnsZoneResourceId string = postgresPrivateDnsZone.id
