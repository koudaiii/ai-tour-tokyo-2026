using 'main.bicep'

param nowYyyymmddHhmm = readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000')
param storageAccountName = 'privateisu${uniqueString('rg-private-isu-${readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000')}')}'
param containerName = 'images'
param postgresServerName = 'privateisu-pg-${readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000')}'
param postgresAdminUser = 'isuconp'
param postgresAdminPassword = readEnvironmentVariable('POSTGRES_ADMIN_PASSWORD', 'ReplaceMe_123!')
param postgresDatabaseName = 'isuconp'
param postgresEntraAdminObjectId = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_OBJECT_ID', '00000000-0000-0000-0000-000000000000')
param postgresEntraAdminPrincipalName = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME', 'user@example.com')
param postgresEntraAdminPrincipalType = readEnvironmentVariable('POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE', 'User')
param postgresVersion = '18'
param postgresTier = 'Burstable'
param postgresSkuName = 'Standard_B1ms'
param postgresStorageSizeGB = 32
param containerAppsEnvironmentName = 'privateisu-acaenv-${readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000')}'
param containerAppName = 'privateisu-app-${readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000')}'
param appContainerImage = readEnvironmentVariable('APP_CONTAINER_IMAGE', 'docker.io/koudaiii/ai-tour-for-partner-2026-track4-session1:latest')
param memcachedContainerImage = 'docker.io/library/memcached:1.6'
param tags = {
  project: 'private-isu'
  environment: 'dev'
}
