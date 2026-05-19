from specforge.cli import build_parser


def test_cli_parser_builds():
    parser = build_parser()
    args = parser.parse_args(["--repo-root", ".", "lint", "--strict"])
    assert args.command == "lint"
    assert args.strict is True


def test_cli_parser_profiles_and_run_flags():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--repo-root",
            ".",
            "run",
            "--task-id",
            "P0-000",
            "--mode",
            "dry-run",
            "--profile",
            "governed",
            "--preflight-strict",
            "--allow-executor-on-block",
        ]
    )
    assert args.profile == "governed"
    assert args.preflight_strict is True
    assert args.allow_executor_on_block is True
