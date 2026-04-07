targetScope = 'resourceGroup'

@description('The Azure region for API Management resource deployment')
param location string

@description('Tags to apply to API Management resources')
param tags object = {}

@description('API Management service name')
param apiManagementName string

@description('Publisher email address for API Management')
param publisherEmail string

@description('Publisher name for API Management')
param publisherName string

@description('API Management SKU name')
@allowed([
  'Consumption'
  'Developer'
  'Basic'
  'Standard'
  'Premium'
])
param skuName string = 'Consumption'

@description('Backend URL of the Container App')
param containerAppUrl string

resource apiManagement 'Microsoft.ApiManagement/service@2024-06-01-preview' = {
  name: apiManagementName
  location: location
  tags: tags
  sku: {
    name: skuName
    capacity: skuName == 'Consumption' ? 0 : 1
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

resource api 'Microsoft.ApiManagement/service/apis@2024-06-01-preview' = {
  parent: apiManagement
  name: 'private-isu-api'
  properties: {
    displayName: 'Private ISU API'
    description: 'REST JSON API for the Private ISU social media application'
    path: ''
    protocols: [
      'https'
    ]
    subscriptionRequired: false
    serviceUrl: containerAppUrl
    format: 'openapi'
    value: loadTextContent('../openapi.yaml')
  }
}

resource backend 'Microsoft.ApiManagement/service/backends@2024-06-01-preview' = {
  parent: apiManagement
  name: 'container-app'
  properties: {
    title: 'Container App Backend'
    description: 'private-isu Container App'
    protocol: 'http'
    url: containerAppUrl
    tls: {
      validateCertificateChain: true
      validateCertificateName: true
    }
  }
}

resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-06-01-preview' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'xml'
    value: '<policies><inbound><base /><set-backend-service backend-id="${backend.name}" /></inbound><backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error></policies>'
  }
}

output apiManagementName string = apiManagement.name
output apiManagementGatewayUrl string = apiManagement.properties.gatewayUrl
output apiManagementPrincipalId string = apiManagement.identity.principalId
