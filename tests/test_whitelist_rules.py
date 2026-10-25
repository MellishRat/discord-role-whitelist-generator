import unittest
import pandas as pd
from whitelist_rules import OutputRule, build_lists, normalize_output_filename


class WhitelistRulesTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame([
            [" Zoe ", "yes", "", ""], ["alice", "yes", "yes", ""],
            ["blocked", "yes", "yes", "x"], ["", "yes", "yes", ""],
            ["alice", "yes", "yes", ""], ["bob", "", "yes", ""],
        ], columns=["Nickname", "Verified", "Tier", "Blocked"])

    def test_combined_role_conditions(self):
        rule = OutputRule("members", ["Verified"], ["Tier", "Other"], ["Blocked"])
        self.assertEqual(build_lists(self.df, [rule], "Nickname"), {"members.txt": ["alice"]})

    def test_empty_conditions_include_every_nonblank_name(self):
        result = build_lists(self.df, [OutputRule("all")], "Nickname")
        self.assertEqual(result["all.txt"], ["alice", "blocked", "bob", "Zoe"])

    def test_sort_and_dedupe_can_be_disabled(self):
        result = build_lists(self.df, [OutputRule("all")], "Nickname", False, False)
        self.assertEqual(result["all.txt"], ["Zoe", "alice", "blocked", "alice", "bob"])

    def test_missing_roles_count_as_absent(self):
        rules = [OutputRule("required", ["missing"]), OutputRule("any", any_of_roles=["missing"]),
                 OutputRule("excluded", must_not_have_roles=["missing"])]
        result = build_lists(self.df, rules, "Nickname")
        self.assertEqual(result["required.txt"], [])
        self.assertEqual(result["any.txt"], [])
        self.assertEqual(len(result["excluded.txt"]), 4)

    def test_nonblank_values_are_roles(self):
        df = pd.DataFrame({"Nickname": ["a", "b", "c"], "Role": ["0", "False", "  "]})
        self.assertEqual(build_lists(df, [OutputRule("out", ["Role"])], "Nickname")["out.txt"], ["a", "b"])

    def test_name_case_is_preserved(self):
        df = pd.DataFrame({"Nickname": ["Alice", "alice"]})
        self.assertEqual(build_lists(df, [OutputRule("out")], "Nickname")["out.txt"], ["Alice", "alice"])

    def test_duplicate_normalized_file_names_rejected(self):
        with self.assertRaisesRegex(ValueError, "same file name"):
            build_lists(self.df, [OutputRule("List.csv"), OutputRule("list.txt")], "Nickname")

    def test_required_inputs(self):
        for df, rules, name in [(None, [OutputRule("a")], "Nickname"), (self.df, [], "Nickname"),
                                (self.df, [OutputRule("a")], "missing")]:
            with self.assertRaises(ValueError):
                build_lists(df, rules, name)

    def test_filename_cleanup(self):
        self.assertEqual(normalize_output_filename(" a/b.csv "), "a b.txt")
        self.assertEqual(normalize_output_filename("..."), "Whitelist.txt")
