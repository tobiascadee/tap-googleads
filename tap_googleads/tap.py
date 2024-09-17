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
            "oauth_credentials",
            th.ObjectType(
                th.Property(
                    "client_id",
                    th.StringType,
                    required=True,
                ),
                th.Property(
                    "client_secret",
                    th.StringType,
                    required=True,
                    secret=True,
                ),
                th.Property(
                    "refresh_token",
                    th.StringType,
                    required=True,
                    secret=True,
                ),
                additional_properties=False,
            ),
            required=True,
        ),
        th.Property(
            "developer_token",
            th.StringType,
            required=True,
            secret=True,
        ),
        th.Property(
            "login_customer_id",
            th.StringType,
            description="Value to use in the login-customer-id header if using a manager customer account. See https://developers.google.com/search-ads/reporting/concepts/login-customer-id for more info.",
        ),
        th.Property(
            "customer_id",
            th.StringType,
            description="Value to use in the login-customer-id header when not using a manager customer account.",
        ),
        th.Property(
            "customer_ids",
            th.ArrayType(th.StringType),
            description="Overrides the taps default get all data for all available customers logic, and will get you the data for only the the provided customer_ids, granted you have access to them.",
        ),
        th.Property(
            "start_date",
            th.DateTimeType,
            description="Start date for all of the streams that use date based filtering.",
        ),
        th.Property(
            "end_date",
            th.DateTimeType,
            description="End date for all of the streams that use date based filtering.",
        ),
        th.Property(
            "enable_click_view_report_stream",
            th.BooleanType,
            description="Enables the tap's ClickViewReportStream. This requires setting up / permission on your google ads account(s)",
            default=False,
        ),
    ).to_dict()

    def discover_streams(self) -> List[Stream]:
        """Return a list of discovered streams."""
        if self.config["enable_click_view_report_stream"]:
            STREAM_TYPES.append(ClickViewReportStream)
        return [stream_class(tap=self) for stream_class in STREAM_TYPES]
