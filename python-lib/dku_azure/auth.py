from azure.identity import DefaultAzureCredential, ManagedIdentityCredential, ClientSecretCredential
from azure.mgmt.msi import ManagedServiceIdentityClient
from msrest.authentication import BasicTokenAuthentication
from azure.core.pipeline.policies import BearerTokenCredentialPolicy
from azure.core.pipeline import PipelineRequest, PipelineContext
from azure.core.pipeline.transport import HttpRequest

from dku_utils.access import _is_none_or_blank

def get_credentials_from_connection_info(connection_info, connection_info_secret):
    client_id = connection_info.get('clientId', None)
    tenant_id = connection_info.get('tenantId', None)
    password = connection_info.get('password', None)
    if _is_none_or_blank(client_id) or _is_none_or_blank(password) or _is_none_or_blank(tenant_id):
        raise Exception('Client, password and tenant must all be defined')

    credentials = ClientSecretCredential(tenant_id, client_id, password)
    return credentials


def get_credentials_from_connection_infoV2(connection_infos):
    infos = connection_infos
    user_managed_identity = infos.get('userManagedIdentity', None)
    identity_type = infos.get('identityType','default')
    managed_identity_id = None
    if identity_type == 'default':
        credentials = DefaultAzureCredential()
    elif identity_type == 'user-assigned':
        managed_identity_id = infos.get('userManagedIdentityId')
        if managed_identity_id.startswith("/"):
            credentials = ManagedIdentityCredential(identity_config={'msi_res_id': managed_identity_id})
        else:
            credentials = ManagedIdentityCredential(client_id=managed_identity_id)
    elif identity_type == 'service-principal':
        client_id = infos.get('clientId', None)
        password = infos.get('password', None)
        tenant_id = infos.get('tenantId', None)
        credentials = ClientSecretCredential(tenant_id, client_id, password)
    else:
        raise Exception("Identity type {} is unknown and cannot be used".format(identity_type))

    return credentials, managed_identity_id



# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# Adapt credentials from azure-identity to be compatible with SDK that needs msrestazure or azure.common.credentials
# Need msrest >= 0.6.0
# See also https://pypi.org/project/azure-identity/
# See https://github.com/jongio/azidext/blob/master/python/azure_identity_credential_adapter.py
class AzureIdentityCredentialAdapter(BasicTokenAuthentication):
    def __init__(self, credential=None, resource_id="https://management.azure.com/.default", **kwargs):
        """Adapt any azure-identity credential to work with SDK that needs azure.common.credentials or msrestazure.
        Default resource is ARM (syntax of endpoint v2)
        :param credential: Any azure-identity credential (DefaultAzureCredential by default)
        :param str resource_id: The scope to use to get the token (default ARM)
        """
        super(AzureIdentityCredentialAdapter, self).__init__(None)
        if credential is None:
            credential = DefaultAzureCredential()
        self._policy = BearerTokenCredentialPolicy(credential, resource_id, **kwargs)

    def _make_request(self):
        return PipelineRequest(
            HttpRequest(
                "AzureIdentityCredentialAdapter",
                "https://fakeurl"
            ),
            PipelineContext(None)
        )

    def set_token(self):
        """Ask the azure-core BearerTokenCredentialPolicy policy to get a token.
        Using the policy gives us for free the caching system of azure-core.
        We could make this code simpler by using private method, but by definition
        I can't assure they will be there forever, so mocking a fake call to the policy
        to extract the token, using 100% public API."""
        request = self._make_request()
        self._policy.on_request(request)
        # Read Authorization, and get the second part after Bearer
        token = request.http_request.headers["Authorization"].split(" ", 1)[1]
        self.token = {"access_token": token}

    def signed_session(self, session=None):
        self.set_token()
        return super(AzureIdentityCredentialAdapter, self).signed_session(session)
