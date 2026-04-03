using 'main.bicep'

param storageAccountName = 'privateisu${uniqueString(readEnvironmentVariable('AZURE_RESOURCE_GROUP', 'default'))}'
param containerName = 'images'
param tags = {
  project: 'private-isu'
  environment: 'dev'
}
