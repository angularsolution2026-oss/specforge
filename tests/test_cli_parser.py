from specforge.cli import build_parser


def test_cli_parser_builds():
    parser = build_parser()
    args = parser.parse_args(["--repo-root", ".", "lint", "--strict"])
    assert args.command == "lint"
    assert args.strict is True
