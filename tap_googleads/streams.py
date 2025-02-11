"""Stream type classes for tap-googleads."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, Optional, TypeVar

from singer_sdk import typing as th  # JSON Schema typing helpers

from tap_googleads.client import GoogleAdsStream

if TYPE_CHECKING:
    from singer_sdk.helpers.types import Context, Record

SCHEMAS_DIR = Path(__file__).parent / Path("./schemas")
_TToken = TypeVar("_TToken")


class AccessibleCustomers(GoogleAdsStream):
    """Accessible Customers"""

    path = "/customers:listAccessibleCustomers"
    name = "stream_accessible_customers"
    primary_keys = ["resource_names"]
    replication_key = None
    schema = th.PropertiesList(
        th.Property("resourceNames", th.ArrayType(th.StringType))
    ).to_dict()

    def generate_child_contexts(
        self,
        record: Record,
        context: Context | None,
    ) -> Iterable[Context | None]:
        """Generate child contexts.

        Args:
            record: Individual record in the stream.
            context: Stream partition or context dictionary.

        Yields:
            A child context for each child stream.
        """
        for customer in record.get("resourceNames", []):
            yield self.get_child_context(record=customer, context=context)

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Return a context dictionary for child streams."""
        customer_id = record.split("/")[1]
        return {"customer_id": customer_id}


class CustomerHierarchyStream(GoogleAdsStream):
    """
    Customer Hierarchy, inspiration from Google here
    https://developers.google.com/google-ads/api/docs/account-management/get-account-hierarchy.

    This stream is stictly to be the Parent Stream, to let all Child Streams
    know when to query the down stream apps.

    """

    rest_method = "POST"

    @property
    def path(self):
        # Paramas
        path = "/customers/{customer_id}"
        path = path + "/googleAds:search"
        path = path + f"?query={self.gaql}"
        return path

    @property
    def gaql(self):
        return """
	SELECT
          customer_client.client_customer,
          customer_client.level,
          customer_client.status,
          customer_client.manager,
          customer_client.descriptive_name,
          customer_client.currency_code,
          customer_client.time_zone,
          customer_client.id
        FROM customer_client
        WHERE customer_client.level <= 1
	"""

    records_jsonpath = "$.results[*]"
    name = "stream_customer_hierarchy"
    primary_keys = ["customerClient__id"]
    replication_key = None
    parent_stream_type = AccessibleCustomers
    schema = th.PropertiesList(
        th.Property(
            "customerClient",
            th.ObjectType(
                th.Property("resourceName", th.StringType),
                th.Property("clientCustomer", th.StringType),
                th.Property("level", th.StringType),
                th.Property("status", th.StringType),
                th.Property("timeZone", th.StringType),
                th.Property("manager", th.BooleanType),
                th.Property("descriptiveName", th.StringType),
                th.Property("currencyCode", th.StringType),
                th.Property("id", th.StringType),
            ),
        )
    ).to_dict()

    # Goal of this stream is to send to children stream a dict of
    # login-customer-id:customer-id to query for all queries downstream
    def get_records(self, context: Optional[dict]) -> Iterable[Dict[str, Any]]:
        """Return a generator of row-type dictionary objects.

        Each row emitted should be a dictionary of property names to their values.

        Args:
            context: Stream partition or context dictionary.

        Yields:
            One item per (possibly processed) record in the API.
        """
        for row in self.request_records(context):
            row = self.post_process(row, context)
            # Don't search Manager accounts as we can't query them for everything
            if (
                row["customerClient"]["manager"]
                or row["customerClient"]["status"] != "ENABLED"
                or row["customerClient"]["id"]
                not in self.config.get("customer_ids", [row["customerClient"]["id"]])
            ):
                continue
            yield row

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Return a context dictionary for child streams."""
        return {"customer_id": record["customerClient"]["id"]}


class GeotargetsStream(GoogleAdsStream):
    """Geotargets, worldwide, constant across all customers"""

    rest_method = "POST"

    @property
    def path(self):
        # Paramas
        path = f"/customers/{self.config.get('login_customer_id')}"
        path = path + "/googleAds:search"
        path = path + f"?query={self.gaql}"
        return path

    gaql = """
    SELECT geo_target_constant.canonical_name, geo_target_constant.country_code, geo_target_constant.id, geo_target_constant.name, geo_target_constant.status, geo_target_constant.target_type FROM geo_target_constant
    """
    records_jsonpath = "$.results[*]"
    name = "stream_geo_target_constant"
    primary_keys = ["geo_target_constant__id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "geo_target_constant.json"
    parent_stream_type = None  # Override ReportsStream default as this is a constant


class ReportsStream(GoogleAdsStream):
    rest_method = "POST"
    parent_stream_type = CustomerHierarchyStream
    path = "/customers/{customer_id}/googleAds:search"

    @property
    def gaql(self):
        raise NotImplementedError

    def prepare_request_payload(
        self,
        context: Context | None,
        next_page_token: _TToken | None,
    ) -> dict | None:
        """Prepare the data payload for the REST API request.

        By default, no payload will be sent (return None).

        Developers may override this method if the API requires a custom payload along
        with the request. (This is generally not required for APIs which use the
        HTTP 'GET' method.)

        Args:
            context: Stream partition or context dictionary.
            next_page_token: Token, page number or any request argument to request the
                next page of data.
        """
        return {
            "query": self.gaql,
            "pageToken": next_page_token,
        }


class ClickViewReportStream(ReportsStream):
    @property
    def gaql(self):
        return """
        SELECT
            click_view.gclid
            , customer.id
            , click_view.ad_group_ad
            , ad_group.id
            , ad_group.name
            , campaign.id
            , campaign.name
            , segments.ad_network_type
            , segments.device
            , segments.date
            , segments.slot
            , metrics.clicks
            , segments.click_type
            , click_view.keyword
            , click_view.keyword_info.match_type
        FROM click_view
        WHERE segments.date = {date}
        """

    records_jsonpath = "$.results[*]"
    name = "stream_click_view_report"
    primary_keys = [
        "clickView__gclid",
        "clickView__keyword",
        "clickView__keywordInfo__matchType",
        "customer__id",
        "adGroup__id",
        "campaign__id",
        "segments__device",
        "segments__adNetworkType",
        "segments__slot",
        "date",
    ]
    replication_key = "date"
    schema_filepath = SCHEMAS_DIR / "click_view_report.json"
    state_partitioning_keys = []

    def post_process(self, row, context):
        row["date"] = row["segments"].pop("date")

        if row.get("clickView", {}).get("keyword") is None:
            row["clickView"]["keyword"] = "null"
            row["clickView"]["keywordInfo"] = {"matchType": "null"}

        return row

    def get_records(self, context: Optional[dict]) -> Iterable[Dict[str, Any]]:
        date_list = []

        replication_values = []

        value = self.stream_state.get("replication_key_value", False)
        if value:
            replication_values.append(value)

        # Get the maximum replication_key_value
        if len(replication_values) > 0:
            last_replication_date = max(replication_values)
        else:
            last_replication_date = None

        yesterdays_date = datetime.now() - timedelta(days=1)

        # if last_replication_date is today or greater, set the date to yesterday (last full days data)
        if last_replication_date:
            if last_replication_date >= datetime.now().strftime("%Y-%m-%d"):
                last_replication_date = yesterdays_date.strftime("%Y-%m-%d")

            # This is if the last_replication_date defaults back to the start date (timestamp)
            if "T" in last_replication_date:
                last_replication_date, _ = last_replication_date.split("T")

        current_date = datetime.strptime(self.start_date.replace("'", ""), "%Y-%m-%d")

        if last_replication_date:
            current_date = datetime.strptime(
                last_replication_date.replace("'", ""), "%Y-%m-%d"
            )

        # Generate a list of dates up to yesterday
        if current_date < datetime.now() - timedelta(days=1):
            while current_date < datetime.now() - timedelta(days=1):
                date_list.append("'" + current_date.strftime("%Y-%m-%d") + "'")
                current_date += timedelta(days=1)
        else:
            date_list.append("'" + yesterdays_date.strftime("%Y-%m-%d") + "'")

        for date in date_list:
            context["date"] = date
            # Call the parent get_records with the modified context (date value)
            for record in super().get_records(context):
                yield record

    def sync(self, context):
        """Sync this stream.

        This method is internal to the SDK and should not need to be overridden.

        Args:
            context: Stream partition or context dictionary.

        Raises:
            Exception: Any exception raised by the sync process.
        """
        msg = f"Beginning {self.replication_method.lower()} sync of '{self.name}'"
        if context:
            msg += f" with context: {context}"
        self.logger.info("%s...", msg)

        # Send a SCHEMA message to the downstream target:
        if self.selected:
            self._write_schema_message()

        try:
            batch_config = self.get_batch_config(self.config)
            if batch_config:
                self._sync_batches(batch_config, context=context)
            else:
                # Sync the records themselves:
                for _ in self._sync_records(context=context):
                    pass
        except Exception as ex:
            if hasattr(ex, "response") and ex.response is not None:
                status_code = ex.response.status_code
                if status_code not in [400, 403]:
                    # Raise the exception if it's not 400 or 403
                    self.logger.exception(
                        "An unhandled error occurred while syncing '%s'",
                        self.name,
                    )
                    raise ex
            else:
                # Log the 400 or 403 error and continue
                self.logger.exception(
                    "An unhandled error occurred while syncing '%s'",
                    self.name,
                )


class CampaignsStream(ReportsStream):
    """Define custom stream."""

    @property
    def gaql(self) -> str:
        """Create gaql statement for request.

        Returns
        -------
        str
            gaql statement.

        """
        properties = [
            f"{self._camel_case_to_snake_case(key)}.{self._camel_case_to_snake_case(prop)}"
            for key, value in self.schema["properties"].items()
            if key not in ["id", "customer_id"]
            for prop in value["properties"]
        ]
        return f"SELECT {', '.join(properties)} FROM campaign"  # noqa: S608

    def post_process(
        self,
        row: Record,
        context: Context | None = None,  # noqa: ARG002
    ) -> dict | None:
        """As needed, append or transform raw data to match expected structure.

        Optional. This method gives developers an opportunity to "clean up" the results
        prior to returning records to the downstream tap - for instance: cleaning,
        renaming, or appending properties to the raw record result returned from the
        API.

        Developers may also return `None` from this method to filter out
        invalid or not-applicable records from the stream.

        Args:
            row: Individual record in the stream.
            context: Stream partition or context dictionary.

        Returns:
            The resulting record dict, or `None` if the record should be excluded.

        """
        row["id"] = row["campaign"]["id"]
        return row

    records_jsonpath = "$.results[*]"
    name = "stream_campaign"
    primary_keys = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign.json"


class AdGroupsStream(ReportsStream):
    """Define custom stream."""

    @property
    def gaql(self):
        return """
       SELECT ad_group.url_custom_parameters, 
       ad_group.type, 
       ad_group.tracking_url_template, 
       ad_group.targeting_setting.target_restrictions,
       ad_group.target_roas,
       ad_group.target_cpm_micros,
       ad_group.status,
       ad_group.target_cpa_micros,
       ad_group.resource_name,
       ad_group.percent_cpc_bid_micros,
       ad_group.name,
       ad_group.labels,
       ad_group.id,
       ad_group.final_url_suffix,
       ad_group.excluded_parent_asset_field_types,
       ad_group.effective_target_roas_source,
       ad_group.effective_target_roas,
       ad_group.effective_target_cpa_source,
       ad_group.effective_target_cpa_micros,
       ad_group.display_custom_bid_dimension,
       ad_group.cpv_bid_micros,
       ad_group.cpm_bid_micros,
       ad_group.cpc_bid_micros,
       ad_group.campaign,
       ad_group.base_ad_group,
       ad_group.ad_rotation_mode
       FROM ad_group 
       """

    records_jsonpath = "$.results[*]"
    name = "stream_adgroups"
    primary_keys = ["ad_group__id", "ad_group__campaign", "ad_group__status"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "ad_group.json"


class AdGroupsPerformance(ReportsStream):
    """AdGroups Performance"""

    @property
    def gaql(self):
        return f"""
        SELECT campaign.id, ad_group.id, metrics.impressions, metrics.clicks,
               metrics.cost_micros
               FROM ad_group
               WHERE segments.date >= {self.start_date} and segments.date <= {self.end_date}
        """

    records_jsonpath = "$.results[*]"
    name = "stream_adgroupsperformance"
    primary_keys = ["campaign__id", "ad_group__id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "adgroups_performance.json"


class CampaignPerformance(ReportsStream):
    """Campaign Performance"""

    @property
    def gaql(self):
        return f"""
    SELECT campaign.name, campaign.status, segments.device, segments.date, metrics.impressions, metrics.clicks, metrics.ctr, metrics.average_cpc, metrics.cost_micros FROM campaign WHERE segments.date >= {self.start_date} and segments.date <= {self.end_date}
    """

    records_jsonpath = "$.results[*]"
    name = "stream_campaign_performance"
    primary_keys = [
        "campaign__name",
        "campaign__status",
        "segments__date",
        "segments__device",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign_performance.json"


class CampaignPerformanceByAgeRangeAndDevice(ReportsStream):
    """Campaign Performance By Age Range and Device"""

    @property
    def gaql(self):
        return f"""
    SELECT ad_group_criterion.age_range.type, campaign.name, campaign.status, ad_group.name, segments.date, segments.device, ad_group_criterion.system_serving_status, ad_group_criterion.bid_modifier, metrics.clicks, metrics.impressions, metrics.ctr, metrics.average_cpc, metrics.cost_micros, campaign.advertising_channel_type FROM age_range_view WHERE segments.date >= {self.start_date} and segments.date <= {self.end_date}
    """

    records_jsonpath = "$.results[*]"
    name = "stream_campaign_performance_by_age_range_and_device"
    primary_keys = [
        "ad_group_criterion__age_range__type",
        "campaign__name",
        "segments__date",
        "campaign__status",
        "segments__device",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign_performance_by_age_range_and_device.json"


class CampaignPerformanceByGenderAndDevice(ReportsStream):
    """Campaign Performance By Age Range and Device"""

    @property
    def gaql(self):
        return f"""
    SELECT ad_group_criterion.gender.type, campaign.name, campaign.status, ad_group.name, segments.date, segments.device, ad_group_criterion.system_serving_status, ad_group_criterion.bid_modifier, metrics.clicks, metrics.impressions, metrics.ctr, metrics.average_cpc, metrics.cost_micros, campaign.advertising_channel_type FROM gender_view WHERE segments.date >= {self.start_date} and segments.date <= {self.end_date}
    """

    records_jsonpath = "$.results[*]"
    name = "stream_campaign_performance_by_gender_and_device"
    primary_keys = [
        "ad_group_criterion__gender__type",
        "campaign__name",
        "segments__date",
        "campaign__status",
        "segments__device",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign_performance_by_gender_and_device.json"


class CampaignPerformanceByLocation(ReportsStream):
    """Campaign Performance By Age Range and Device"""

    @property
    def gaql(self):
        return f"""
    SELECT campaign_criterion.location.geo_target_constant, campaign.name, campaign_criterion.bid_modifier, segments.date, metrics.clicks, metrics.impressions, metrics.ctr, metrics.average_cpc, metrics.cost_micros FROM location_view WHERE segments.date >= {self.start_date} and segments.date <= {self.end_date} AND campaign_criterion.status != 'REMOVED'
    """

    records_jsonpath = "$.results[*]"
    name = "stream_campaign_performance_by_location"
    primary_keys = [
        "campaign_criterion__location__geo_target_constant",
        "campaign__name",
        "segments__date",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "campaign_performance_by_location.json"


class GeoPerformance(ReportsStream):
    """Geo performance"""

    @property
    def gaql(self):
        return f"""
    SELECT 
        campaign.name, 
        campaign.status, 
        segments.date, 
        metrics.clicks, 
        metrics.cost_micros,
        metrics.impressions, 
        metrics.conversions,
        geographic_view.location_type,
        geographic_view.country_criterion_id
    FROM geographic_view 
    WHERE segments.date >= {self.start_date} and segments.date <= {self.end_date} 
    """

    records_jsonpath = "$.results[*]"
    name = "stream_geo_performance"
    primary_keys = [
        "geographic_view__country_criterion_id",
        "customer_id",
        "campaign__name",
        "segments__date",
    ]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / "geo_performance.json"
