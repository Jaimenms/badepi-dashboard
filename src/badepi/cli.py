"""Linha de comando: badepi download | extract | silver | gold | all."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import SOURCES


def _sources_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-s", "--source", action="append", dest="sources", choices=list(SOURCES),
        help="ativo de PI (repetível). Padrão: todos os aplicáveis.",
    )
    parser.add_argument("--force", action="store_true", help="refaz mesmo que a saída exista")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="badepi", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("download", help="bronze: baixa os zips do INPI para data/bronze/_downloads")
    _sources_arg(p)
    p = sub.add_parser("extract", help="bronze: extrai os zips para data/bronze/<ativo>/")
    _sources_arg(p)
    p = sub.add_parser("bronze", help="bronze: download + extract")
    _sources_arg(p)
    p = sub.add_parser("silver", help="silver: CSVs → parquet tipado e relacionado em data/silver/<ativo>/")
    _sources_arg(p)
    p = sub.add_parser("gold", help="gold: agregações JSON em data/gold e docs/data (dashboard)")
    _sources_arg(p)
    p = sub.add_parser("all", help="bronze + silver + gold")
    _sources_arg(p)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    from . import bronze

    silver_slugs = [s for s in (args.sources or SOURCES) if SOURCES[s].silver_ready]
    if args.cmd in ("download", "bronze", "all"):
        bronze.run(args.sources, force=args.force, do_extract=False)
    if args.cmd in ("extract", "bronze", "all"):
        bronze.run(args.sources, force=args.force, do_download=False)
    if args.cmd in ("silver", "all"):
        from .silver import run as silver_run

        silver_run(silver_slugs, force=args.force)
    if args.cmd in ("gold", "all"):
        from .gold import run as gold_run

        gold_run(silver_slugs, force=args.force)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
