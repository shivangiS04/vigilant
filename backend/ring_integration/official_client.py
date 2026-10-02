import os
from typing import Any, Dict, List, Optional

import httpx


RING_OAUTH_BASE_URL = "https://oauth.ring.com"
RING_API_BASE_URL = "https://api.amazonvision.com"


class RingPartnerAPIError(RuntimeError):
    pass


class RingPartnerClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http_client: Optional[httpx.Client] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = http_client or httpx.Client(timeout=10.0)

    @classmethod
    def from_env(cls, http_client: Optional[httpx.Client] = None) -> "RingPartnerClient":
        client_id = os.getenv("RING_CLIENT_ID")
        client_secret = os.getenv("RING_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError("RING_CLIENT_ID and RING_CLIENT_SECRET must be configured")
        return cls(client_id, client_secret, http_client)

    def exchange_authorization_code(self, code: str) -> Dict[str, Any]:
        return self._exchange_token(
            {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
            }
        )

    def refresh_tokens(self, refresh_token: str) -> Dict[str, Any]:
        return self._exchange_token(
            {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
            }
        )

    def get_user_profile(self, access_token: str) -> Dict[str, Any]:
        return self._get_json("/v1/users/me", access_token)

    def list_devices(self, access_token: str) -> List[Dict[str, Any]]:
        result = self._get_json("/v1/devices", access_token)
        data = result.get("data")
        if not isinstance(data, list):
            raise RingPartnerAPIError("Ring returned an invalid device list")
        return data

    def complete_account_link(
        self, access_token: str, account_identifier: str, nonce: str
    ) -> None:
        headers = self._auth_headers(access_token)
        response = self._http.post(
            f"{RING_API_BASE_URL}/v1/accounts/me/app-integrations",
            headers=headers,
            json={"account_identifier": account_identifier, "nonce": nonce},
        )
        self._raise_for_ring(response, "Ring account-link verification failed")

        response = self._http.patch(
            f"{RING_API_BASE_URL}/v1/accounts/me/app-integrations",
            headers=headers,
            json={"status": "completed"},
        )
        self._raise_for_ring(response, "Ring account-link completion failed")

    def _exchange_token(self, fields: Dict[str, str]) -> Dict[str, Any]:
        response = self._http.post(
            f"{RING_OAUTH_BASE_URL}/oauth/token",
            data=fields,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        result = self._json_response(response, "Ring token exchange failed")
        required = ("access_token", "refresh_token", "expires_in")
        if any(key not in result for key in required):
            raise RingPartnerAPIError("Ring token response is missing required fields")
        return result

    def _get_json(self, path: str, access_token: str) -> Dict[str, Any]:
        response = self._http.get(
            f"{RING_API_BASE_URL}{path}", headers=self._auth_headers(access_token)
        )
        result = self._json_response(response, "Ring API request failed")
        if not isinstance(result, dict):
            raise RingPartnerAPIError("Ring returned an invalid JSON response")
        return result

    @staticmethod
    def _auth_headers(access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _json_response(response: httpx.Response, message: str) -> Dict[str, Any]:
        try:
            RingPartnerClient._raise_for_ring(response, message)
            result = response.json()
        except ValueError as exc:
            raise RingPartnerAPIError("Ring returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise RingPartnerAPIError("Ring returned an invalid JSON response")
        return result

    @staticmethod
    def _raise_for_ring(response: httpx.Response, message: str) -> None:
        if response.is_error:
            raise RingPartnerAPIError(f"{message} (HTTP {response.status_code})")