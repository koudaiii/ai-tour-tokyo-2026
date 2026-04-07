////////////
// Metadata
////////////
targetScope = 'subscription'

metadata description = 'Deploy Azure Storage Account + Azure Database for PostgreSQL Flexible Server + Azure Container Apps for private-isu'

////////////
// Parameters
////////////
@description('The Azure region for resource deployment')
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

@description('Name of the Storage Account (must be globally unique, 3-24 lowercase alphanumeric)')
@minLength(3)
@maxLength(24)
param storageAccountName string = 'st${workloadCode}sbx${regionCode}${substring(nowYyyymmddHhmm, 2, 6)}${substring(uniqueString(subscription().subscriptionId, nowYyyymmddHhmm), 0, 2)}'

@description('Name of the blob container for storing images')
param containerName string = 'images'

@description('Name of the PostgreSQL Flexible Server (3-63 lowercase alphanumeric or hyphen)')
@minLength(3)
@maxLength(63)
param postgresServerName string = 'pgfs-${workloadCode}-${deploymentEnvironment}-${regionCode}-${nowYyyymmddHhmm}'

@description('PostgreSQL administrator login')
param postgresAdminUser string = 'isuconp'

@description('PostgreSQL administrator password')
@secure()
param postgresAdminPassword string

@description('Application database name in PostgreSQL')
param postgresDatabaseName string = 'isuconp'

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

@description('Container Apps managed environment name')
param containerAppsEnvironmentName string = 'acae-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(nowYyyymmddHhmm, 2, 10)}'

@description('Container App name')
param containerAppName string = 'aca-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(nowYyyymmddHhmm, 2, 10)}'

@description('Virtual network name for private connectivity')
param virtualNetworkName string = 'vnet-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(nowYyyymmddHhmm, 2, 10)}'

@description('Address prefix for the virtual network')
param virtualNetworkAddressPrefix string = '10.10.0.0/16'

@description('Address prefix for the Container Apps infrastructure subnet')
param containerAppsInfrastructureSubnetPrefix string = '10.10.0.0/23'

@description('Address prefix for the PostgreSQL private endpoint subnet')
param postgresPrivateEndpointSubnetPrefix string = '10.10.2.0/24'

@description('Application container image (Docker Hub or ACR)')
param appContainerImage string = 'docker.io/koudaiii/ai-tour-for-partner-2026-track4-session1:latest'

@description('Memcached sidecar container image')
param memcachedContainerImage string = 'docker.io/library/memcached:1.6'

@description('API Management service name')
param apiManagementName string = 'apim-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(nowYyyymmddHhmm, 2, 10)}'

@description('Publisher email address for API Management')
param apimPublisherEmail string

@description('Publisher name for API Management')
param apimPublisherName string = 'private-isu'

@description('API Management SKU name')
@allowed([
  'Consumption'
  'Developer'
  'Basic'
  'Standard'
  'Premium'
])
param apimSkuName string = 'Consumption'

@description('Tags to apply to all resources')
param tags object = {}

////////////
// Variables
////////////
var resourceGroupName = 'rg-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(nowYyyymmddHhmm, 2, 10)}'

////////////
// Resources / Modules
////////////
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module network 'network.bicep' = {
  name: 'networkDeployment'
  scope: rg
  params: {
    location: location
    tags: tags
    virtualNetworkName: virtualNetworkName
    virtualNetworkAddressPrefix: virtualNetworkAddressPrefix
    containerAppsInfrastructureSubnetPrefix: containerAppsInfrastructureSubnetPrefix
    postgresPrivateEndpointSubnetPrefix: postgresPrivateEndpointSubnetPrefix
  }
}

module storageAccount 'br/public:avm/res/storage/storage-account:0.32.0' = {
  name: 'storageAccountDeployment'
  scope: rg
  params: {
    name: storageAccountName
    location: location
    tags: tags
    kind: 'StorageV2'
    skuName: 'Standard_LRS'
    accessTier: 'Hot'
    allowBlobPublicAccess: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    blobServices: {
      containers: [
        {
          name: containerName
          publicAccess: 'Blob'
        }
      ]
    }
  }
}

module postgres 'postgresql.bicep' = {
  name: 'postgresDeployment'
  scope: rg
  params: {
    location: location
    tags: tags
    postgresServerName: postgresServerName
    postgresAdminUser: postgresAdminUser
    postgresAdminPassword: postgresAdminPassword
    postgresDatabaseName: postgresDatabaseName
    postgresEntraAdminObjectId: postgresEntraAdminObjectId
    postgresEntraAdminPrincipalName: postgresEntraAdminPrincipalName
    postgresEntraAdminPrincipalType: postgresEntraAdminPrincipalType
    postgresEntraAdminTenantId: subscription().tenantId
    postgresVersion: postgresVersion
    postgresTier: postgresTier
    postgresSkuName: postgresSkuName
    postgresStorageSizeGB: postgresStorageSizeGB
    postgresPrivateEndpointSubnetResourceId: network.outputs.postgresPrivateEndpointSubnetResourceId
    postgresPrivateDnsZoneResourceId: network.outputs.postgresPrivateDnsZoneResourceId
  }
}

module containerApps 'containerapps.bicep' = {
  name: 'containerAppsDeployment'
  scope: rg
  params: {
    location: location
    tags: tags
    containerAppsEnvironmentName: containerAppsEnvironmentName
    containerAppName: containerAppName
    containerAppsInfrastructureSubnetResourceId: network.outputs.containerAppsInfrastructureSubnetResourceId
    appContainerImage: appContainerImage
    memcachedContainerImage: memcachedContainerImage
    azureStorageAccountUrl: storageAccount.outputs.primaryBlobEndpoint
    azureStorageAccountResourceId: storageAccount.outputs.resourceId
    azureStorageContainerName: containerName
    postgresDatabaseUrl: 'postgresql://${postgresAdminUser}:${postgresAdminPassword}@${postgres.outputs.postgresHost}:5432/${postgresDatabaseName}?sslmode=require'
  }
}

module apiManagement 'apimanagement.bicep' = {
  name: 'apiManagementDeployment'
  scope: rg
  params: {
    location: location
    tags: tags
    apiManagementName: apiManagementName
    publisherEmail: apimPublisherEmail
    publisherName: apimPublisherName
    skuName: apimSkuName
    containerAppUrl: containerApps.outputs.containerAppUrl
  }
}

////////////
// Outputs
////////////
@description('The resource group name')
output resourceGroupName string = rg.name

@description('The primary blob endpoint URL')
output blobEndpoint string = storageAccount.outputs.primaryBlobEndpoint

@description('The full container URL for image access')
output containerUrl string = '${storageAccount.outputs.primaryBlobEndpoint}${containerName}'

@description('The Storage Account name')
output storageAccountName string = storageAccount.outputs.name

@description('The Storage Account resource ID')
output storageAccountId string = storageAccount.outputs.resourceId

@description('PostgreSQL flexible server name')
output postgresServerName string = postgres.outputs.postgresServerName

@description('PostgreSQL flexible server host FQDN')
output postgresHost string = postgres.outputs.postgresHost

@description('PostgreSQL port')
output postgresPort int = postgres.outputs.postgresPort

@description('PostgreSQL admin login')
output postgresAdminLogin string = postgres.outputs.postgresAdminLogin

@description('PostgreSQL database name')
output postgresDatabaseName string = postgres.outputs.postgresDatabaseName

@description('Container App name')
output containerAppName string = containerApps.outputs.containerAppName

@description('Container App URL')
output containerAppUrl string = containerApps.outputs.containerAppUrl

@description('Container Apps managed environment name')
output containerAppsEnvironmentName string = containerApps.outputs.managedEnvironmentName

@description('API Management service name')
output apiManagementName string = apiManagement.outputs.apiManagementName

@description('API Management gateway URL')
output apiManagementGatewayUrl string = apiManagement.outputs.apiManagementGatewayUrl
