import unittest

from app.services.query_validator import QueryValidator
from app.services.retriever import Retriever
from tests.support import shared_index


class QueryValidatorTest(unittest.TestCase):
    def setUp(self):
        self.validator = QueryValidator(Retriever(shared_index()))

    def test_valid_pipeline_and_time_option_error(self):
        valid = self.validator.validate(
            'table duration=24h firewall_logs\n| search action == "deny"\n| stats count by src_ip'
        )
        self.assertTrue(valid.valid, valid.errors)
        invalid = self.validator.validate("table duration=24h from=2026-01-01 to=2026-01-02 firewall_logs")
        self.assertFalse(invalid.valid)
        self.assertTrue([error for error in invalid.errors if error.code == "exclusive_time_options"])

    def test_fulltext_time_options_are_mutually_exclusive(self):
        result = self.validator.validate('fulltext duration=24h from=20260801 to=20260802 "1.2.3.4"')
        self.assertFalse(result.valid)
        self.assertTrue([error for error in result.errors if error.code == "exclusive_time_options"])

    def test_option_validation_uses_command_context(self):
        table_ok = self.validator.validate("table duration=24h firewall_logs")
        self.assertFalse([w for w in table_ok.warnings if w.code == "unknown_option"])
        timechart_ok = self.validator.validate("table duration=24h firewall_logs | timechart span=10m count")
        self.assertFalse([w for w in timechart_ok.warnings if w.code == "unknown_option"])
        search_bad = self.validator.validate("table firewall_logs | search duration=24h")
        self.assertTrue([w for w in search_bad.warnings if w.code == "unknown_option"])

    def test_ignores_options_inside_quoted_string(self):
        result = self.validator.validate('table firewall_logs | search message == "duration=24h"')
        self.assertTrue(result.valid, result.errors)
        self.assertFalse([w for w in result.warnings if w.code == "unknown_option"])

    def test_ignores_functions_inside_quoted_string(self):
        result = self.validator.validate('table firewall_logs | search message == "fake_func(value)"')
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.functions, [])
        self.assertFalse([w for w in result.warnings if w.code == "unknown_function"])

    def test_rejects_empty_pipeline_segment(self):
        result = self.validator.validate("table firewall_logs || stats count")
        self.assertFalse(result.valid)
        self.assertTrue([error for error in result.errors if error.code == "empty_pipeline_segment"])

    def test_allows_pipe_inside_quoted_string(self):
        result = self.validator.validate('table firewall_logs | search message == "ERROR|WARN"')
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.commands, ["table", "search"])

    def test_allows_pipe_inside_subquery(self):
        result = self.validator.validate('setq [ table firewall_logs | stats count ] | table firewall_logs')
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.commands, ["setq", "table"])

    def test_rejects_pipeline_without_first_command(self):
        result = self.validator.validate("| table firewall_logs")
        self.assertFalse(result.valid)
        self.assertTrue([error for error in result.errors if error.code == "empty_pipeline_segment"])

    def test_rejects_unbalanced_quotes(self):
        result = self.validator.validate('table firewall_logs | search message == "ERROR')
        self.assertFalse(result.valid)
        self.assertTrue([error for error in result.errors if error.code == "unbalanced_quotes"])

    def test_allows_escaped_quotes(self):
        result = self.validator.validate('table firewall_logs | search message == "say \\"hello\\""')
        self.assertTrue(result.valid, result.errors)

    def test_warns_on_bad_comment_spacing(self):
        result = self.validator.validate("table firewall_logs #comment")
        self.assertTrue([warning for warning in result.warnings if warning.code == "comment_spacing"])

    def test_allows_good_comment_spacing(self):
        result = self.validator.validate("table firewall_logs # comment")
        self.assertFalse([warning for warning in result.warnings if warning.code == "comment_spacing"])

    def test_ignores_hash_inside_quoted_string_for_comment_spacing(self):
        result = self.validator.validate('table firewall_logs | search message == "error#code"')
        self.assertTrue(result.valid, result.errors)
        self.assertFalse([warning for warning in result.warnings if warning.code == "comment_spacing"])

    def test_rejects_table_without_table_name(self):
        result = self.validator.validate("table duration=24h")
        self.assertFalse(result.valid)
        self.assertTrue([error for error in result.errors if error.code == "missing_required_parameter"])

    def test_rejects_fulltext_without_expression(self):
        result = self.validator.validate("fulltext duration=24h from firewall_logs")
        self.assertFalse(result.valid)
        self.assertTrue([error for error in result.errors if error.code == "missing_required_parameter"])

    def test_rejects_stats_without_aggregation(self):
        result = self.validator.validate("table firewall_logs | stats")
        self.assertFalse(result.valid)
        self.assertTrue([error for error in result.errors if error.code == "missing_required_parameter"])

    def test_accepts_generated_parameterized_table_query(self):
        result = self.validator.validate('set from=ago("7d") | set to=str(now()) | table from=$("from") to=$("to") YOUR_TABLE')
        self.assertTrue(result.valid, result.errors)


if __name__ == "__main__":
    unittest.main()
