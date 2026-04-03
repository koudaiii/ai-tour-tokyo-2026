////////////
// Metadata
////////////
metadata description = 'Deploy Azure Storage Account and Blob Container for private-isu image storage'

////////////
// Parameters
////////////
@description('The Azure region for resource deployment')
param location string = resourceGroup().location

@description('Name of the Storage Account (must be globally unique, 3-24 lowercase alphanumeric)')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Name of the blob container for storing images')
param containerName string = 'images'

@description('Tags to apply to all resources')
param tags object = {}

////////////
// Resources / Modules
////////////
module storageAccount 'br/public:avm/res/storage/storage-account:0.32.0' = {
  name: 'storageAccountDeployment'
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

////////////
// Outputs
////////////
@description('The primary blob endpoint URL')
output blobEndpoint string = storageAccount.outputs.primaryBlobEndpoint

@description('The full container URL for image access')
output containerUrl string = '${storageAccount.outputs.primaryBlobEndpoint}${containerName}'

@description('The Storage Account name')
output storageAccountName string = storageAccount.outputs.name

@description('The Storage Account resource ID')
output storageAccountId string = storageAccount.outputs.resourceId
