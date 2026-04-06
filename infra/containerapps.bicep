targetScope = 'resourceGroup'

@description('The Azure region for Container Apps resource deployment')
param location string

@description('Tags to apply to Container Apps resources')
param tags object = {}

@description('Container Apps managed environment name')
param containerAppsEnvironmentName string

@description('Container App name')
param containerAppName string

@description('Application container image')
param appContainerImage string

@description('Memcached sidecar container image')
param memcachedContainerImage string = 'docker.io/library/memcached:1.6'

@description('Azure Blob Storage account URL')
param azureStorageAccountUrl string

@description('Azure Blob Storage account resource ID')
param azureStorageAccountResourceId string

@description('Azure Blob Storage container name')
param azureStorageContainerName string = 'images'

@description('PostgreSQL server host FQDN')
param postgresHost string

@description('PostgreSQL database name')
param postgresDatabaseName string

@description('PostgreSQL Entra principal name used by app managed identity')
param postgresIdentityPrincipalName string

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppsEnvironmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'none'
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'app'
          image: appContainerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'ISUCONP_DB_AUTH_MODE'
              value: 'managed_identity'
            }
            {
              name: 'ISUCONP_DB_HOST'
              value: postgresHost
            }
            {
              name: 'ISUCONP_DB_PORT'
              value: '5432'
            }
            {
              name: 'ISUCONP_DB_NAME'
              value: postgresDatabaseName
            }
            {
              name: 'ISUCONP_DB_USER'
              value: postgresIdentityPrincipalName
            }
            {
              name: 'ISUCONP_MEMCACHED_ADDRESS'
              value: '127.0.0.1:11211'
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT_URL'
              value: azureStorageAccountUrl
            }
            {
              name: 'AZURE_STORAGE_CONTAINER_NAME'
              value: azureStorageContainerName
            }
          ]
        }
        {
          name: 'memcached'
          image: memcachedContainerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

resource storageAccountResource 'Microsoft.Storage/storageAccounts@2025-01-01' existing = {
  scope: resourceGroup()
  name: last(split(azureStorageAccountResourceId, '/'))
}

resource storageBlobDataContributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(azureStorageAccountResourceId, containerAppName, 'Storage Blob Data Contributor')
  scope: storageAccountResource
  properties: {
    principalId: containerApp.identity.principalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
    principalType: 'ServicePrincipal'
  }
}

output containerAppName string = containerApp.name
output containerAppPrincipalId string = containerApp.identity.principalId
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output managedEnvironmentName string = managedEnvironment.name
output managedEnvironmentId string = managedEnvironment.id
output postgresIdentityPrincipalName string = postgresIdentityPrincipalName

