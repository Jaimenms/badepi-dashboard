"""Camada gold: agregações prontas para o dashboard, um módulo por ativo."""

from __future__ import annotations

import importlib
import logging

from ..config import SOURCES

log = logging.getLogger(__name__)


def run(slugs: list[str], force: bool = False) -> None:
    for slug in slugs:
        source = SOURCES[slug]
        if not source.silver_ready:
            log.warning("[%s] ainda sem camada gold; pulando", slug)
            continue
        module = importlib.import_module(f"badepi.gold.{slug}")
        module.build(force=force)
