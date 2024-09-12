"""REST client handling, including GoogleAdsStream base class."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import re

import requests
from dateutil import parser
from memoization import cached
from singer_sdk.authenticators import OAuthAuthenticator
from singer_sdk.streams import RESTStream
from singer_sdk.pagination import BaseAPIPaginator

from tap_googleads.auth import GoogleAdsAuthenticator, ProxyGoogleAdsAuthenticator


class GoogleAdsStream(RESTStream):
    """GoogleAds stream class."""

    url_base = "https://googleads.googleapis.com/v16"

    records_jsonpath = "$[*]"  # Or override `parse_response`.
    next_page_token_jsonpath = "$.nextPageToken"  # Or override `get_next_page_token`.
    _LOG_REQUEST_METRIC_URLS: bool = True

    _end_date = "'" + datetime.now().strftime("%Y-%m-%d") + "'"
    _start_date = datetime.now() - timedelta(days=91)
    _start_date = "'" + _start_date.strftime("%Y-%m-%d") + "'"

    @property
    @cached
    def authenticator(self) -> OAuthAuthenticator:
        """Return a new authenticator object."""
        base_auth_url = "https://www.googleapis.com/oauth2/v4/token"
        # Silly way to do parameters but it works

        client_id = self.config.get("oauth_credentials", {}).get("client_id", None)
        client_secret = self.config.get("oauth_credentials", {}).get(
            "client_secret", None
        )
        refresh_token = self.config.get("oauth_credentials", {}).get(
            "refresh_token", None
        )

        auth_url = base_auth_url + f"?refresh_token={refresh_token}"
        auth_url = auth_url + f"&client_id={client_id}"
        auth_url = auth_url + f"&client_secret={client_secret}"
        auth_url = auth_url + "&grant_type=refresh_token"

        if client_id and client_secret and refresh_token:
            return GoogleAdsAuthenticator(stream=self, auth_endpoint=auth_url)

        oauth_credentials = self.config.get("oauth_credentials", {})

        auth_body = {}
        auth_headers = {}

        auth_body["refresh_token"] = oauth_credentials.get("refresh_token")
        auth_body["grant_type"] = "refresh_token"

        auth_headers["authorization"] = oauth_credentials.get("refresh_proxy_url_auth")
        auth_headers["Content-Type"] = "application/json"
        auth_headers["Accept"] = "application/json"

        return ProxyGoogleAdsAuthenticator(
            stream=self,
            auth_endpoint=oauth_credentials.get("refresh_proxy_url"),
            auth_body=auth_body,
            auth_headers=auth_headers,
        )

    @property
    def http_headers(self) -> dict:
        """Return the http headers needed."""
        headers = {}
        if "user_agent" in self.config:
            headers["User-Agent"] = self.config.get("user_agent")
        headers["developer-token"] = self.config["developer_token"]
        headers["login-customer-id"] = self.config.get("login_customer_id")
        return headers

    def get_new_paginator(self) -> BaseAPIPaginator:
        return GoogleAdsPaginator(None)

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params: dict = {}
        if next_page_token:
            params["pageToken"] = next_page_token
        if self.replication_key:
            params["sort"] = "asc"
            params["order_by"] = self.replication_key
        return params

    @property
    def start_date(self):
        date = self.config.get("start_date")
        if date:
            date = parser.parse(self.config.get("start_date"))
            date = "'" + date.strftime("%Y-%m-%d") + "'"
        return date or self._start_date

    @property
    def end_date(self):
        date = self.config.get("end_date")
        if date:
            date = parser.parse(self.config.get("end_date"))
            date = "'" + date.strftime("%Y-%m-%d") + "'"
        return date or self._end_date

    def _camel_case_to_snake_case(self, camel_case_word: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", camel_case_word).lower()


class GoogleAdsPaginator(BaseAPIPaginator):
    def get_next(self, response: requests.Response) -> str | None:
        """Get the next pagination token or index from the API response.

        Args:
            response: API response object.

        Returns:
            The next page token or index. Return `None` from this method to indicate
                the end of pagination.
        """
        data = response.json()
        return data.get("nextPageToken")
