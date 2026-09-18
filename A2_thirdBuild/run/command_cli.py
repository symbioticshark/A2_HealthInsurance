"""Command adapter used by the thin program entry point."""

from run import interactive_cli


def run(argv):
    parser = interactive_cli.build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        return interactive_cli.run()
    interactive_cli.prepare_runtime()
    return args.func(args)
