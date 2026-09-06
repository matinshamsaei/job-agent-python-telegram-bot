from app.core.enums import AtsType, CollectionStatus, CollectionStrategy
from app.db.seed import declared_sources_for, load_target_companies, normalize_source
from app.db.seed_data import JOB_SOURCES
from app.jobs.pipeline import PipelineSummary


def test_legacy_flat_columns_still_produce_a_primary_source() -> None:
    sources = declared_sources_for({"ats_type": "greenhouse", "board_token": "careem"})
    assert len(sources) == 1
    assert sources[0]["label"] == "primary"
    assert sources[0]["ats_type"] == AtsType.GREENHOUSE.value
    assert sources[0]["board_token"] == "careem"
    assert sources[0]["collection_strategy"] == CollectionStrategy.API.value
    assert sources[0]["status"] == CollectionStatus.FEED_AVAILABLE.value


def test_a_company_can_declare_several_sources() -> None:
    sources = declared_sources_for(
        {
            "ats_type": "career_page",
            "sources": [
                {"ats_type": "greenhouse", "board_token": "acme"},
                {
                    "ats_type": "workday",
                    "feed_url": "https://acme.wd3.myworkdayjobs.com/en-US/Acme",
                    "label": "corporate",
                },
            ],
        }
    )
    assert [source["label"] for source in sources] == ["primary", "corporate"]
    assert sources[1]["collection_strategy"] == CollectionStrategy.API.value


def test_source_without_a_token_is_not_marked_feed_available() -> None:
    source = normalize_source({"ats_type": "greenhouse"}, 0)
    assert source["status"] == CollectionStatus.DISCOVERED.value


def test_career_page_source_is_discovered_not_feed_available() -> None:
    source = normalize_source({"ats_type": "career_page"}, 0)
    assert source["status"] == CollectionStatus.DISCOVERED.value
    assert source["collection_strategy"] == CollectionStrategy.BROWSER.value


def test_unlabelled_extra_sources_get_distinct_labels() -> None:
    sources = declared_sources_for(
        {"sources": [{"ats_type": "greenhouse"}, {"ats_type": "lever"}]}
    )
    labels = [source["label"] for source in sources]
    assert len(labels) == len(set(labels))


def test_catalog_lists_every_ats_type_with_a_strategy() -> None:
    names = {source["name"] for source in JOB_SOURCES}
    assert names == {ats.value for ats in AtsType}
    for source in JOB_SOURCES:
        assert source["collection_strategy"] in set(CollectionStrategy)


def test_catalog_marks_the_implemented_adapters() -> None:
    implemented = {
        source["name"] for source in JOB_SOURCES if source["adapter_implemented"]
    }
    from app.collectors.registry import supported_ats_types

    assert implemented == supported_ats_types()


def test_seed_json_entries_all_resolve_to_a_source() -> None:
    for row in load_target_companies():
        sources = declared_sources_for(row)
        assert sources, row["slug"]
        for source in sources:
            assert source["ats_type"] in {ats.value for ats in AtsType}
            assert source["collection_strategy"] in set(CollectionStrategy)


def test_summary_counts_statuses_and_ranks_missing_adapters() -> None:
    summary = PipelineSummary()
    summary.record_status(CollectionStatus.COLLECTED, AtsType.GREENHOUSE.value)
    summary.record_status(CollectionStatus.ADAPTER_MISSING, AtsType.CAREER_PAGE.value)
    summary.record_status(CollectionStatus.ADAPTER_MISSING, AtsType.CAREER_PAGE.value)
    summary.record_status(CollectionStatus.ADAPTER_MISSING, AtsType.ICIMS.value)

    assert summary.status_counts[CollectionStatus.COLLECTED.value] == 1
    assert summary.status_counts[CollectionStatus.ADAPTER_MISSING.value] == 3
    assert summary.missing_adapters == {AtsType.CAREER_PAGE.value: 2, AtsType.ICIMS.value: 1}
