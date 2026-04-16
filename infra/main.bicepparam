using 'main.bicep'

param nowYyyymmddHhmm = readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000')
param workloadCode = 'pisu'
param deploymentEnvironment = 'sandbox'
param regionCode = 'jpe'
param storageAccountName = 'st${workloadCode}sbx${regionCode}${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 6)}${substring(uniqueString(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000')), 0, 2)}'
param containerName = 'images'
param postgresServerName = 'pgfs-${workloadCode}-${deploymentEnvironment}-${regionCode}-${readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000')}'
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
param containerAppsEnvironmentName = 'acae-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 10)}'
param containerAppName = 'aca-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 10)}'
param appContainerImage = readEnvironmentVariable('APP_CONTAINER_IMAGE', 'docker.io/koudaiii/ai-tour-tokyo-2026:latest')
param memcachedContainerImage = 'docker.io/library/memcached:1.6'
param apiManagementName = 'apim-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 10)}'
param apimPublisherEmail = readEnvironmentVariable('APIM_PUBLISHER_EMAIL', 'admin@example.com')
param apimPublisherName = 'private-isu'
param apimSkuName = 'Consumption'
param functionAppName = 'func-${workloadCode}-mcp-${deploymentEnvironment}-${regionCode}-${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 10)}'
param functionAppServicePlanName = 'asp-${workloadCode}-mcp-${deploymentEnvironment}-${regionCode}-${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 10)}'
param functionsStorageAccountName = 'stfn${workloadCode}${regionCode}${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 6)}${substring(uniqueString(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 'func'), 0, 2)}'
param seedFunctionAppName = 'func-${workloadCode}-seed-${deploymentEnvironment}-${regionCode}-${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 10)}'
param seedFunctionAppServicePlanName = 'asp-${workloadCode}-seed-${deploymentEnvironment}-${regionCode}-${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 10)}'
param seedFunctionsStorageAccountName = 'stfs${workloadCode}${regionCode}${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 6)}${substring(uniqueString(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 'seedfunc'), 0, 2)}'
param logAnalyticsWorkspaceName = 'log-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 10)}'
param appInsightsName = 'appi-${workloadCode}-${deploymentEnvironment}-${regionCode}-${substring(readEnvironmentVariable('NOW_YYYYMMDDHHMM', '000000000000'), 2, 10)}'
param tags = {
  project: 'private-isu'
  environment: 'dev'
}
