targetScope = 'resourceGroup'

@description('The Azure region for PostgreSQL resource deployment')
param location string

@description('Tags to apply to PostgreSQL resources')
param tags object = {}

@description('Name of the PostgreSQL Flexible Server')
param postgresServerName string

@description('PostgreSQL administrator login')
param postgresAdminUser string

@description('PostgreSQL administrator password')
@secure()
param postgresAdminPassword string

@description('Application database name')
param postgresDatabaseName string

@description('Microsoft Entra admin principal object ID for PostgreSQL server')
param postgresEntraAdminObjectId string

@description('Microsoft Entra admin principal name (UPN/display name/app name)')
param postgresEntraAdminPrincipalName string

@description('Microsoft Entra admin principal type')
@allowed([
  'User'
  'Group'
  'ServicePrincipal'
])
param postgresEntraAdminPrincipalType string = 'User'

@description('Tenant ID for Microsoft Entra admin')
param postgresEntraAdminTenantId string

@description('PostgreSQL server version')
@allowed([
  '18'
])
param postgresVersion string = '18'

@description('PostgreSQL compute tier')
@allowed([
  'Burstable'
  'GeneralPurpose'
  'MemoryOptimized'
])
param postgresTier string = 'Burstable'

@description('PostgreSQL SKU name')
param postgresSkuName string = 'Standard_B1ms'

@description('PostgreSQL storage size in GiB')
param postgresStorageSizeGB int = 32

@description('Subnet resource ID used for PostgreSQL private endpoint')
param postgresPrivateEndpointSubnetResourceId string

@description('Private DNS zone resource ID for PostgreSQL private endpoint')
param postgresPrivateDnsZoneResourceId string

module postgresServer 'br/public:avm/res/db-for-postgre-sql/flexible-server:0.15.2' = {
  name: 'postgresFlexibleServerDeployment'
  params: {
    name: postgresServerName
    location: location
    tags: tags
    availabilityZone: -1
    skuName: postgresSkuName
    tier: postgresTier
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Enabled'
      tenantId: postgresEntraAdminTenantId
    }
    version: postgresVersion
    storageSizeGB: postgresStorageSizeGB
    backupRetentionDays: 7
    geoRedundantBackup: 'Disabled'
    highAvailability: 'Disabled'
    publicNetworkAccess: 'Enabled'
    privateEndpoints: [
      {
        subnetResourceId: postgresPrivateEndpointSubnetResourceId
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            {
              privateDnsZoneResourceId: postgresPrivateDnsZoneResourceId
            }
          ]
        }
      }
    ]
    databases: [
      {
        name: postgresDatabaseName
        charset: 'UTF8'
        collation: 'en_US.utf8'
      }
    ]
  }
}

resource postgresServerResource 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' existing = {
  name: postgresServerName
}

resource postgresEntraAdmin 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2024-08-01' = if (!empty(postgresEntraAdminObjectId) && !empty(postgresEntraAdminPrincipalName)) {
  parent: postgresServerResource
  name: postgresEntraAdminObjectId
  properties: {
    principalName: postgresEntraAdminPrincipalName
    principalType: postgresEntraAdminPrincipalType
    tenantId: postgresEntraAdminTenantId
  }
  dependsOn: [
    postgresServer
  ]
}

output postgresServerName string = postgresServerName
output postgresHost string = '${postgresServerName}.postgres.database.azure.com'
output postgresPort int = 5432
output postgresAdminLogin string = postgresAdminUser
output postgresDatabaseName string = postgresDatabaseName

