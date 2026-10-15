"""Configuração central: fontes do BADEPI, versão e diretórios das camadas."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Versão publicada em 13/10/2026 (dados até dezembro/2025)
BADEPI_VERSION = "v12"
BADEPI_PAGE_URL = "https://www.gov.br/inpi/pt-br/inpi-data/dados-e-series-temporais/badepi"
INPIDRIVE_URL = "https://inpidrive.inpi.gov.br/index.php/s/{token}/download"

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("BADEPI_DATA_DIR", REPO_ROOT / "data"))
BRONZE_DIR = DATA_DIR / "bronze"
DOWNLOADS_DIR = BRONZE_DIR / "_downloads"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
DOCS_DIR = REPO_ROOT / "docs"
DOCS_DATA_DIR = DOCS_DIR / "data"
REFERENCE_DIR = Path(__file__).resolve().parent / "reference"


@dataclass(frozen=True)
class Source:
    """Um ativo de PI publicado no BADEPI (um zip por ativo)."""

    slug: str  # nome da pasta em bronze/ e silver/
    prefix: str  # prefixo dos arquivos csv dentro do zip
    label: str
    token: str  # token do compartilhamento Nextcloud (inpidrive)
    silver_ready: bool = False  # True quando já existe transformação silver

    @property
    def filename(self) -> str:
        return f"badepi{BADEPI_VERSION}_{self.prefix}.zip"

    @property
    def url(self) -> str:
        return INPIDRIVE_URL.format(token=self.token)

    @property
    def bronze_dir(self) -> Path:
        return BRONZE_DIR / self.slug

    @property
    def silver_dir(self) -> Path:
        return SILVER_DIR / self.slug

    @property
    def zip_path(self) -> Path:
        return DOWNLOADS_DIR / self.filename


SOURCES: dict[str, Source] = {
    s.slug: s
    for s in [
        Source("patentes", "ptn", "Patentes", "G33ljb4puihwzDR", silver_ready=True),
        Source("marcas", "mrc", "Marcas", "muKXZIss7b6t1Mc"),
        Source("desenho_industrial", "di", "Desenho Industrial", "lhf76AMnV9ZQRQU"),
        Source("indicacao_geografica", "ig", "Indicação Geográfica", "1AG5jwKf9JZkNYl"),
        Source("contratos", "ctt", "Contratos de Tecnologia", "st9Qc409XUtnuWV"),
        Source("programa_computador", "prg", "Programa de Computador", "l3NBlP1i9WWnZKE"),
        Source("topografia_ci", "tci", "Topografia de Circuito Integrado", "6MeSqSiYXoxPVAX"),
        Source("pi_genero", "pigen", "PI e Gênero", "gRN41UuBt8NdlEB"),
    ]
}


def get_source(slug: str) -> Source:
    try:
        return SOURCES[slug]
    except KeyError:
        raise SystemExit(f"Fonte desconhecida: {slug!r}. Opções: {', '.join(SOURCES)}") from None
