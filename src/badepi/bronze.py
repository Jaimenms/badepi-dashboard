"""Camada bronze: download dos zips do INPI e extração dos CSVs originais.

Regras:
  * nada é alterado nos arquivos originais — a bronze é a "foto" do que o INPI publicou;
  * cada zip é validado (teste de integridade) antes de ser aceito; o servidor do
    INPI não informa Content-Length, então o tamanho não serve como checagem;
  * um manifesto JSON registra url, sha256, tamanho, data e versão de cada arquivo.
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

from .config import BADEPI_VERSION, DOWNLOADS_DIR, SOURCES, Source

log = logging.getLogger(__name__)
CHUNK = 1 << 20  # 1 MiB


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def zip_is_valid(path: Path) -> bool:
    if not path.exists() or not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def _manifest_path(directory: Path) -> Path:
    return directory / "_manifest.json"


def _load_manifest(directory: Path) -> dict:
    p = _manifest_path(directory)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"badepi_version": BADEPI_VERSION, "files": {}}


def _save_manifest(directory: Path, manifest: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with open(_manifest_path(directory), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def download(source: Source, force: bool = False, timeout: int = 60) -> Path:
    """Baixa o zip de um ativo para bronze/_downloads, com retomada segura via .part."""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = source.zip_path
    if dest.exists() and not force and zip_is_valid(dest):
        log.info("[%s] zip já presente e íntegro: %s", source.slug, dest.name)
        _register_download(source, dest)
        return dest

    part = dest.with_suffix(dest.suffix + ".part")
    log.info("[%s] baixando %s", source.slug, source.url)
    with requests.get(source.url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0) or None
        with open(part, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=source.filename, leave=False
        ) as bar:
            for block in r.iter_content(CHUNK):
                f.write(block)
                bar.update(len(block))
    if not zip_is_valid(part):
        part.unlink(missing_ok=True)
        raise RuntimeError(f"[{source.slug}] arquivo baixado não é um zip válido: {source.url}")
    part.replace(dest)
    _register_download(source, dest)
    log.info("[%s] ok: %s (%.1f MB)", source.slug, dest.name, dest.stat().st_size / 1e6)
    return dest


def _register_download(source: Source, dest: Path) -> None:
    manifest = _load_manifest(DOWNLOADS_DIR)
    entry = manifest["files"].get(dest.name)
    size = dest.stat().st_size
    if entry and entry.get("size") == size and entry.get("sha256"):
        return  # já registrado
    manifest["files"][dest.name] = {
        "source": source.slug,
        "label": source.label,
        "url": source.url,
        "size": size,
        "sha256": sha256_of(dest),
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "badepi_version": BADEPI_VERSION,
    }
    _save_manifest(DOWNLOADS_DIR, manifest)


def extract(source: Source, force: bool = False) -> Path:
    """Extrai o zip de um ativo para bronze/<slug>/ e grava o manifesto dos arquivos."""
    dest_dir = source.bronze_dir
    zip_path = source.zip_path
    if not zip_is_valid(zip_path):
        raise FileNotFoundError(f"[{source.slug}] zip ausente ou inválido: {zip_path}. Rode 'badepi download' antes.")
    manifest = _load_manifest(dest_dir)
    zip_sha = sha256_of(zip_path)
    if not force and manifest.get("zip_sha256") == zip_sha and all(
        (dest_dir / name).exists() for name in manifest.get("files", {})
    ):
        log.info("[%s] bronze já extraída (%d arquivos)", source.slug, len(manifest["files"]))
        return dest_dir

    dest_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name  # zips do INPI são planos; evita path traversal
            target = dest_dir / name
            with zf.open(info) as src, open(target, "wb") as out:
                for block in iter(lambda: src.read(CHUNK), b""):
                    out.write(block)
            files[name] = {
                "size": info.file_size,
                "zip_mtime": datetime(*info.date_time).isoformat(timespec="minutes"),
                "sha256": sha256_of(target),
            }
            log.info("[%s] extraído %s (%.1f MB)", source.slug, name, info.file_size / 1e6)
    manifest = {
        "badepi_version": BADEPI_VERSION,
        "source": source.slug,
        "label": source.label,
        "zip": zip_path.name,
        "zip_sha256": zip_sha,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": files,
    }
    _save_manifest(dest_dir, manifest)
    return dest_dir


def run(slugs: list[str] | None = None, force: bool = False, do_download: bool = True, do_extract: bool = True) -> None:
    for slug in slugs or list(SOURCES):
        source = SOURCES[slug]
        if do_download:
            download(source, force=force)
        if do_extract:
            extract(source, force=force)
