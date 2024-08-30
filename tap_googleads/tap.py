"""GoogleAds tap class."""

from typing import List

from singer_sdk import Stream, Tap
from singer_sdk import typing as th  # JSON schema typing helpers

from tap_googleads.streams import (
    AccessibleCustomers,
    AdGroupsPerformance,
    AdGroupsStream,
    CampaignPerformance,
    CampaignPerformanceByAgeRangeAndDevice,
    CampaignPerformanceByGenderAndDevice,
    CampaignPerformanceByLocation,
    CampaignsStream,
    CustomerHierarchyStream,
    GeoPerformance,
    GeotargetsStream,
    ClickViewReportStream,
)

STREAM_TYPES = [
    CampaignsStream,
    AdGroupsStream,
    AdGroupsPerformance,
    AccessibleCustomers,
    CustomerHierarchyStream,
    CampaignPerformance,
    CampaignPerformanceByAgeRangeAndDevice,
    CampaignPerformanceByGenderAndDevice,
    CampaignPerformanceByLocation,
    GeotargetsStream,
    GeoPerformance,
]


class TapGoogleAds(Tap):
    """GoogleAds tap class."""

    name = "tap-googleads"

    # TODO: Add Descriptions
    config_jsonschema = th.PropertiesList(
        th.Property(
            "oauth_credentials.client_id",
            th.StringType,
        ),
        th.Property(
            "oauth_credentials.client_secret",
            th.StringType,
        ),
        th.Property(
            "developer_token",
            th.StringType,
        ),
        th.Property(
            "oauth_credentials.refresh_token",
            th.StringType,
        ),
        th.Property(
            "customer_id",
            th.StringType,
        ),
        th.Property(
            "login_customer_id",
            th.StringType,
            description="Value to use in the login-customer-id header, if different from the customer_id to sync. Useful if you are syncing using a manager account.",
        ),
        th.Property(
            "comma_separated_string_of_customer_ids",
            th.StringType,
            description="Overrides the taps default get all data for all available customers logic, and will get you the data for only the the provided customer_ids",
        ),
        th.Property(
            "enable_click_view_report_stream",
            th.BooleanType,
            description="Enables the tap's ClickViewReportStream. This requires setting up / permission on your google ads account(s)",
        ),
    ).to_dict()

    def discover_streams(self) -> List[Stream]:
        """Return a list of discovered streams."""
        if self.config.get("enable_click_view_report_stream"):
            if self.config.get("enable_click_view_report_stream") == True:
                STREAM_TYPES.append(ClickViewReportStream)
        return [stream_class(tap=self) for stream_class in STREAM_TYPES]
