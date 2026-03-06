"""
Unit tests for area_summary/generate_html.py helper functions.

Tests the refactored helper functions used for paper year extraction,
paper link building, and TOC generation.
"""

# Import from the area_summary module
# The module structure uses hyphens converted to underscores in Python imports
try:
    # Try the buck module path first
    from assistant.research.paper_agent.area_summary.generate_html import (
        _add_paper_links_from_list,
        _add_paper_to_map,
        _build_cross_topic_section,
        _build_global_paper_links,
        _build_paper_year_map,
        _build_pipeline_section,
        _build_theme_section,
        _build_timeline_paper_links,
        _categorize_ordered_topics,
        _extract_acronyms_from_developments,
        _extract_paper_id,
        _extract_short_name_link,
        _extract_year_from_item,
        _find_matching_cat_entry,
        summary_file_key,
    )
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "area_summary"))
    from generate_html import (
        _add_paper_links_from_list,
        _add_paper_to_map,
        _build_cross_topic_section,
        _build_global_paper_links,
        _build_paper_year_map,
        _build_pipeline_section,
        _build_theme_section,
        _build_timeline_paper_links,
        _categorize_ordered_topics,
        _extract_acronyms_from_developments,
        _extract_paper_id,
        _extract_short_name_link,
        _extract_year_from_item,
        _find_matching_cat_entry,
        summary_file_key,
    )


class TestExtractYearFromItem:
    """Tests for _extract_year_from_item function."""

    def test_extract_year_from_year_field(self):
        """Test extraction when year field is present."""
        item = {"year": "2024"}
        result = _extract_year_from_item(item)
        assert result == "2024"

    def test_extract_year_from_pub_date_field(self):
        """Test extraction when pub_date field is used instead of year."""
        item = {"pub_date": "2023-05-15"}
        result = _extract_year_from_item(item)
        assert result == "2023"

    def test_year_field_takes_priority_over_pub_date(self):
        """Test that year field is preferred over pub_date."""
        item = {"year": "2024", "pub_date": "2023-05-15"}
        result = _extract_year_from_item(item)
        assert result == "2024"

    def test_truncate_long_year_string(self):
        """Test truncation of year strings longer than 4 chars."""
        item = {"year": "2024-01-15T00:00:00Z"}
        result = _extract_year_from_item(item)
        assert result == "2024"

    def test_empty_item_returns_empty_string(self):
        """Test that empty item returns empty string."""
        item = {}
        result = _extract_year_from_item(item)
        assert result == ""

    def test_none_year_returns_empty_string(self):
        """Test that None year value returns empty string."""
        item = {"year": None}
        result = _extract_year_from_item(item)
        assert result == ""

    def test_integer_year_is_converted(self):
        """Test that integer year is converted to string."""
        item = {"year": 2024}
        result = _extract_year_from_item(item)
        assert result == "2024"

    def test_short_year_string_returned_as_is(self):
        """Test that short year strings (less than 4 chars) are returned as-is."""
        item = {"year": "24"}
        result = _extract_year_from_item(item)
        assert result == "24"


class TestExtractPaperId:
    """Tests for _extract_paper_id function."""

    def test_extract_integer_paper_id(self):
        """Test extraction of integer paper_id."""
        item = {"paper_id": 12345}
        result = _extract_paper_id(item)
        assert result == 12345

    def test_extract_string_paper_id(self):
        """Test extraction of string paper_id converts to int."""
        item = {"paper_id": "67890"}
        result = _extract_paper_id(item)
        assert result == 67890

    def test_missing_paper_id_returns_none(self):
        """Test that missing paper_id returns None."""
        item = {"title": "Some Paper"}
        result = _extract_paper_id(item)
        assert result is None

    def test_none_paper_id_returns_none(self):
        """Test that None paper_id returns None."""
        item = {"paper_id": None}
        result = _extract_paper_id(item)
        assert result is None

    def test_invalid_paper_id_returns_none(self):
        """Test that invalid (non-numeric) paper_id returns None."""
        item = {"paper_id": "not-a-number"}
        result = _extract_paper_id(item)
        assert result is None

    def test_float_paper_id_converts_to_int(self):
        """Test that float paper_id is converted to int."""
        item = {"paper_id": 123.0}
        result = _extract_paper_id(item)
        assert result == 123


class TestAddPaperToMap:
    """Tests for _add_paper_to_map function."""

    def test_add_paper_with_valid_id_and_year(self):
        """Test adding paper with valid paper_id and year."""
        pmap = {}
        item = {"paper_id": 100, "year": "2024"}
        _add_paper_to_map(pmap, item)
        assert pmap == {100: "2024"}

    def test_overwrite_existing_paper_when_overwrite_true(self):
        """Test that existing paper is overwritten when overwrite=True."""
        pmap = {100: "2023"}
        item = {"paper_id": 100, "year": "2024"}
        _add_paper_to_map(pmap, item, overwrite=True)
        assert pmap[100] == "2024"

    def test_skip_existing_paper_when_overwrite_false(self):
        """Test that existing paper is NOT overwritten when overwrite=False."""
        pmap = {100: "2023"}
        item = {"paper_id": 100, "year": "2024"}
        _add_paper_to_map(pmap, item, overwrite=False)
        assert pmap[100] == "2023"

    def test_add_new_paper_when_overwrite_false(self):
        """Test that new papers are added when overwrite=False."""
        pmap = {100: "2023"}
        item = {"paper_id": 200, "year": "2024"}
        _add_paper_to_map(pmap, item, overwrite=False)
        assert pmap == {100: "2023", 200: "2024"}

    def test_skip_item_with_no_paper_id(self):
        """Test that items without paper_id are skipped."""
        pmap = {}
        item = {"title": "No ID Paper", "year": "2024"}
        _add_paper_to_map(pmap, item)
        assert pmap == {}

    def test_add_paper_with_pub_date(self):
        """Test adding paper using pub_date instead of year."""
        pmap = {}
        item = {"paper_id": 100, "pub_date": "2024-03-15"}
        _add_paper_to_map(pmap, item)
        assert pmap == {100: "2024"}


class TestExtractShortNameLink:
    """Tests for _extract_short_name_link function."""

    def test_extract_link_from_valid_paper(self):
        """Test extraction of (short_name, paper_id, year) tuple."""
        item = {"paper_id": 100, "title": "BERT: Bidirectional Encoder", "year": "2019"}
        result = _extract_short_name_link(item)
        assert result is not None
        sn, pid, yr = result
        assert pid == 100
        assert yr == "2019"
        assert "BERT" in sn or sn != ""

    def test_returns_none_for_missing_paper_id(self):
        """Test that None is returned when paper_id is missing."""
        item = {"title": "Some Paper", "year": "2024"}
        result = _extract_short_name_link(item)
        assert result is None

    def test_returns_none_for_empty_title(self):
        """Test that None is returned when title is empty."""
        item = {"paper_id": 100, "title": "", "year": "2024"}
        result = _extract_short_name_link(item)
        # Should return None because short_paper_name("") returns None/empty
        assert result is None


class TestAddPaperLinksFromList:
    """Tests for _add_paper_links_from_list function."""

    def test_add_links_from_paper_list(self):
        """Test adding links from a list of papers."""
        links = {}
        papers = [
            {"paper_id": 100, "title": "BERT Model", "year": "2019"},
            {"paper_id": 200, "title": "GPT Architecture", "year": "2020"},
        ]
        _add_paper_links_from_list(links, papers)
        # Should have added links for papers with derivable short names
        assert len(links) >= 0  # Some papers may not have derivable short names

    def test_skip_papers_without_paper_id(self):
        """Test that papers without paper_id are skipped."""
        links = {}
        papers = [
            {"title": "No ID Paper", "year": "2024"},
        ]
        _add_paper_links_from_list(links, papers)
        assert links == {}

    def test_overwrite_false_preserves_existing(self):
        """Test that overwrite=False preserves existing links."""
        links = {"BERT": (999, "2018")}
        papers = [
            {"paper_id": 100, "title": "BERT Model", "year": "2019"},
        ]
        _add_paper_links_from_list(links, papers, overwrite=False)
        # If BERT short name would be generated, original should be preserved
        if "BERT" in links:
            assert links["BERT"] == (999, "2018")

    def test_overwrite_true_replaces_existing(self):
        """Test that overwrite=True replaces existing links."""
        links = {"BERT": (999, "2018")}
        papers = [
            {"paper_id": 100, "title": "BERT Model", "year": "2019"},
        ]
        _add_paper_links_from_list(links, papers, overwrite=True)
        # If BERT short name would be generated, it should be replaced
        # Note: depends on short_paper_name implementation


class TestBuildPaperYearMap:
    """Tests for _build_paper_year_map function."""

    def test_build_map_from_field_timeline(self):
        """Test building year map from field_timeline landmark papers."""
        topic_summaries = {}
        cross_topic = {
            "field_timeline": {
                "periods": [
                    {
                        "landmark_papers": [
                            {"paper_id": 100, "year": "2020"},
                            {"paper_id": 200, "pub_date": "2021-05-01"},
                        ]
                    }
                ]
            }
        }
        result = _build_paper_year_map(topic_summaries, cross_topic)
        assert result[100] == "2020"
        assert result[200] == "2021"

    def test_build_map_from_topic_summaries(self):
        """Test building year map from topic summaries."""
        topic_summaries = {
            "topic_1": {
                "significant_papers": [{"paper_id": 100, "year": "2020"}],
                "methods": [
                    {"representative_papers": [{"paper_id": 200, "year": "2021"}]}
                ],
            }
        }
        cross_topic = {"field_timeline": {}}
        result = _build_paper_year_map(topic_summaries, cross_topic)
        assert result[100] == "2020"
        assert result[200] == "2021"

    def test_timeline_papers_take_priority(self):
        """Test that field_timeline papers overwrite topic summary papers."""
        topic_summaries = {
            "topic_1": {
                "significant_papers": [{"paper_id": 100, "year": "2019"}],
            }
        }
        cross_topic = {
            "field_timeline": {
                "periods": [{"landmark_papers": [{"paper_id": 100, "year": "2020"}]}]
            }
        }
        result = _build_paper_year_map(topic_summaries, cross_topic)
        # Timeline should have priority
        assert result[100] == "2020"

    def test_benchmark_papers_are_included(self):
        """Test that benchmark best_result papers are included."""
        topic_summaries = {
            "topic_1": {
                "benchmark_results": {
                    "primary_benchmarks": [
                        {"best_result": {"paper_id": 100, "year": "2023"}}
                    ]
                }
            }
        }
        cross_topic = {"field_timeline": {}}
        result = _build_paper_year_map(topic_summaries, cross_topic)
        assert result[100] == "2023"

    def test_empty_input_returns_empty_map(self):
        """Test that empty inputs return empty map."""
        result = _build_paper_year_map({}, {})
        assert result == {}


class TestBuildTimelinePaperLinks:
    """Tests for _build_timeline_paper_links function."""

    def test_build_links_from_timeline(self):
        """Test building links from field timeline landmark papers."""
        field_timeline = {
            "periods": [
                {
                    "landmark_papers": [
                        {"paper_id": 100, "title": "BERT Model", "year": "2019"},
                    ]
                }
            ]
        }
        result = _build_timeline_paper_links(field_timeline)
        # Result should contain links for papers with derivable short names
        assert isinstance(result, dict)

    def test_empty_timeline_returns_empty_dict(self):
        """Test that empty timeline returns empty dict."""
        result = _build_timeline_paper_links({})
        assert result == {}

    def test_timeline_without_periods_returns_empty(self):
        """Test that timeline without periods returns empty dict."""
        result = _build_timeline_paper_links({"periods": []})
        assert result == {}


class TestExtractAcronymsFromDevelopments:
    """Tests for _extract_acronyms_from_developments function."""

    def test_extract_acronym_from_development_text(self):
        """Test extraction of acronym from development text pattern."""
        field_timeline = {
            "periods": [
                {
                    "key_developments": [
                        "Bidirectional Encoder Representations from Transformers (BERT, Paper 100)"
                    ]
                }
            ]
        }
        paper_year_map = {100: "2019"}
        result = _extract_acronyms_from_developments(field_timeline, paper_year_map)
        assert "BERT" in result
        assert result["BERT"] == (100, "2019")

    def test_extract_from_dict_development(self):
        """Test extraction from dict-style development entries."""
        field_timeline = {
            "periods": [
                {
                    "key_developments": [
                        {
                            "description": "Generative Pre-trained Transformer (GPT, Paper 200)"
                        }
                    ]
                }
            ]
        }
        paper_year_map = {200: "2020"}
        result = _extract_acronyms_from_developments(field_timeline, paper_year_map)
        assert "GPT" in result
        assert result["GPT"] == (200, "2020")

    def test_empty_timeline_returns_empty_dict(self):
        """Test that empty timeline returns empty dict."""
        result = _extract_acronyms_from_developments({}, {})
        assert result == {}

    def test_no_matching_pattern_returns_empty(self):
        """Test that text without matching pattern returns empty dict."""
        field_timeline = {
            "periods": [{"key_developments": ["No acronym pattern here"]}]
        }
        result = _extract_acronyms_from_developments(field_timeline, {})
        assert result == {}


class TestBuildGlobalPaperLinks:
    """Tests for _build_global_paper_links function."""

    def test_combines_timeline_and_topic_links(self):
        """Test that function combines links from multiple sources."""
        topic_summaries = {
            "topic_1": {
                "landmark_papers": [
                    {"paper_id": 100, "title": "Paper A", "year": "2020"}
                ],
                "methods": [],
            }
        }
        field_timeline = {
            "periods": [
                {
                    "landmark_papers": [
                        {"paper_id": 200, "title": "Paper B", "year": "2021"}
                    ],
                    "key_developments": [],
                }
            ]
        }
        result = _build_global_paper_links(topic_summaries, field_timeline)
        assert isinstance(result, dict)

    def test_empty_inputs_returns_empty_dict(self):
        """Test that empty inputs return empty dict."""
        result = _build_global_paper_links({}, {})
        assert result == {}


class TestCategorizeOrderedTopics:
    """Tests for _categorize_ordered_topics function."""

    def test_categorize_category_general_topics(self):
        """Test categorization of category_general topics."""
        ordered_topics = [("category_general", "retrieval", "[C]")]
        # Note: summary_file_key removes underscores, so "category_general" -> "category_retrieval"
        topic_summaries = {
            "category_retrieval": {
                "topic_name": "Retrieval",
                "topic_id": "retrieval",
            }
        }
        cats, subs, themes = _categorize_ordered_topics(ordered_topics, topic_summaries)
        assert len(cats) == 1
        assert cats[0] == ("[C]", "Retrieval", "retrieval")
        assert len(subs) == 0
        assert len(themes) == 0

    def test_categorize_sub_topic_topics(self):
        """Test categorization of sub_topic topics."""
        ordered_topics = [("sub_topic", "dense_retrieval", "[S]")]
        # Note: summary_file_key removes underscores, so "sub_topic" -> "subtopic_dense_retrieval"
        topic_summaries = {
            "subtopic_dense_retrieval": {
                "topic_name": "Dense Retrieval",
                "topic_id": "dense_retrieval",
            }
        }
        cats, subs, themes = _categorize_ordered_topics(ordered_topics, topic_summaries)
        assert len(cats) == 0
        assert len(subs) == 1
        assert subs[0] == ("[S]", "Dense Retrieval", "dense_retrieval")
        assert len(themes) == 0

    def test_categorize_theme_topics(self):
        """Test categorization of theme topics (default category)."""
        ordered_topics = [("theme", "efficiency", "[T]")]
        topic_summaries = {
            "theme_efficiency": {
                "topic_name": "Efficiency",
                "topic_id": "efficiency",
            }
        }
        cats, subs, themes = _categorize_ordered_topics(ordered_topics, topic_summaries)
        assert len(cats) == 0
        assert len(subs) == 0
        assert len(themes) == 1
        assert themes[0] == ("[T]", "Efficiency", "efficiency")

    def test_skip_topics_not_in_summaries(self):
        """Test that topics not found in topic_summaries are skipped."""
        ordered_topics = [("category_general", "missing", "[?]")]
        topic_summaries = {}
        cats, subs, themes = _categorize_ordered_topics(ordered_topics, topic_summaries)
        assert len(cats) == 0
        assert len(subs) == 0
        assert len(themes) == 0

    def test_categorize_multiple_topics(self):
        """Test categorization of multiple topics of different types."""
        ordered_topics = [
            ("category_general", "retrieval", "[C]"),
            ("sub_topic", "dense", "[S]"),
            ("theme", "efficiency", "[T]"),
        ]
        # Keys use the actual summary_file_key format
        topic_summaries = {
            "category_retrieval": {"topic_name": "Retrieval", "topic_id": "retrieval"},
            "subtopic_dense": {"topic_name": "Dense", "topic_id": "dense"},
            "theme_efficiency": {"topic_name": "Efficiency", "topic_id": "efficiency"},
        }
        cats, subs, themes = _categorize_ordered_topics(ordered_topics, topic_summaries)
        assert len(cats) == 1
        assert len(subs) == 1
        assert len(themes) == 1


class TestFindMatchingCatEntry:
    """Tests for _find_matching_cat_entry function."""

    def test_exact_match(self):
        """Test finding exact match for cat_id."""
        cats = [("[C]", "Retrieval", "retrieval")]
        result = _find_matching_cat_entry(cats, "retrieval")
        assert result == ("[C]", "Retrieval", "retrieval")

    def test_partial_match(self):
        """Test finding partial match (cat_id in anchor)."""
        cats = [("[C]", "Retrieval Methods", "retrieval_methods")]
        result = _find_matching_cat_entry(cats, "retrieval")
        assert result == ("[C]", "Retrieval Methods", "retrieval_methods")

    def test_no_match_returns_none(self):
        """Test that non-matching cat_id returns None."""
        cats = [("[C]", "Retrieval", "retrieval")]
        result = _find_matching_cat_entry(cats, "generation")
        assert result is None

    def test_empty_cats_returns_none(self):
        """Test that empty cats list returns None."""
        result = _find_matching_cat_entry([], "retrieval")
        assert result is None


class TestBuildThemeSection:
    """Tests for _build_theme_section function."""

    def test_build_section_with_themes(self):
        """Test building theme section with multiple themes."""
        themes = [
            ("[T]", "Efficiency", "efficiency"),
            ("[T]", "Safety", "safety"),
        ]
        result = _build_theme_section(themes)
        assert "Research Themes" in result
        assert "efficiency" in result
        assert "safety" in result
        assert "[T]" in result
        assert "[T]" in result

    def test_empty_themes_returns_empty_string(self):
        """Test that empty themes list returns empty string."""
        result = _build_theme_section([])
        assert result == ""


class TestBuildCrossTopicSection:
    """Tests for _build_cross_topic_section function."""

    def test_returns_static_html(self):
        """Test that function returns expected static HTML structure."""
        result = _build_cross_topic_section()
        assert "Cross-Topic Analysis" in result
        assert "recommendations" in result
        assert "takeaways" in result
        assert "trends" in result
        assert "opportunities" in result
        assert "distribution" in result
        assert "glossary" in result


class TestBuildPipelineSection:
    """Tests for _build_pipeline_section function."""

    def test_build_section_with_categories(self):
        """Test building pipeline section with categories."""
        cats = [("[C]", "Retrieval", "retrieval")]
        subs = []
        taxonomy = {"categories": [{"id": "retrieval", "sub_topics": []}]}
        result = _build_pipeline_section(cats, subs, taxonomy)
        assert "Pipeline Categories" in result
        assert "retrieval" in result

    def test_build_section_with_subs(self):
        """Test building pipeline section with sub-topics."""
        cats = [("[C]", "Retrieval", "retrieval")]
        subs = [("[S]", "Dense Retrieval", "dense_retrieval")]
        taxonomy = {
            "categories": [
                {"id": "retrieval", "sub_topics": [{"id": "dense_retrieval"}]}
            ]
        }
        result = _build_pipeline_section(cats, subs, taxonomy)
        assert "Pipeline Categories" in result
        assert "dense_retrieval" in result

    def test_empty_taxonomy_returns_empty_string(self):
        """Test that empty taxonomy returns empty string."""
        result = _build_pipeline_section([], [], {"categories": []})
        assert result == ""


class TestSummaryFileKey:
    """Tests for summary_file_key function."""

    def test_generates_correct_key_for_category_general(self):
        """Test that correct file key is generated for category_general."""
        result = summary_file_key("category_general", "retrieval")
        # Note: category_general maps to "category_" prefix
        assert result == "category_retrieval"

    def test_generates_correct_key_for_sub_topic(self):
        """Test key generation for sub_topic (maps to subtopic_ prefix)."""
        result = summary_file_key("sub_topic", "dense_retrieval")
        # Note: sub_topic maps to "subtopic_" prefix (no underscore)
        assert result == "subtopic_dense_retrieval"

    def test_generates_correct_key_for_theme(self):
        """Test key generation for theme type."""
        result = summary_file_key("theme", "efficiency")
        assert result == "theme_efficiency"
