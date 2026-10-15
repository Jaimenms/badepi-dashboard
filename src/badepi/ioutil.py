"""Leitura dos CSVs do BADEPI e escrita de parquet/JSON.

Os CSVs do INPI usam ';' como separador, CRLF, aspas inconsistentes e
encoding misto: a maior parte das tabelas está em cp1252/latin-1, a tabela de
despachos está em UTF-8 e algumas linhas isoladas fogem ao padrão do arquivo.
Por isso a leitura é feita linha a linha: tenta UTF-8 e, se falhar, cp1252.
"""

from __future__ import annotations

import io
import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CSV_SEP = ";"


class TranscodingReader(io.TextIOBase):
    """Arquivo texto virtual que decodifica cada linha como UTF-8 com fallback cp1252."""

    def __init__(self, path: Path | str, fallback: str = "cp1252") -> None:
        self._f = open(path, "rb")
        self._fallback = fallback
        self._pending: list[str] = []
        self._pending_len = 0
        self.n_fallback = 0

    def readable(self) -> bool:  # pragma: no cover - protocolo
        return True

    def _decode(self, line: bytes) -> str:
        try:
            return line.decode("utf-8")
        except UnicodeDecodeError:
            self.n_fallback += 1
            return line.decode(self._fallback, errors="replace")

    def read(self, size: int | None = -1) -> str:
        if size is None or size < 0:
            chunks = self._pending + [self._decode(l) for l in self._f]
            self._pending, self._pending_len = [], 0
            return "".join(chunks)
        while self._pending_len < size:
            line = self._f.readline()
            if not line:
                break
            text = self._decode(line)
            self._pending.append(text)
            self._pending_len += len(text)
        joined = "".join(self._pending)
        out, rest = joined[:size], joined[size:]
        self._pending, self._pending_len = ([rest] if rest else []), len(rest)
        return out

    def close(self) -> None:
        self._f.close()
        super().close()


def _clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Remove espaços nas bordas e converte vazios em <NA>."""
    for col in df.columns:
        s = df[col].str.strip()
        df[col] = s.mask(s == "", pd.NA).astype("string")
    return df


def read_badepi_csv(path: Path | str, usecols: list[str] | None = None) -> pd.DataFrame:
    """Lê um CSV do BADEPI inteiro como texto limpo (dtype string, vazios = <NA>)."""
    reader = TranscodingReader(path)
    try:
        df = pd.read_csv(reader, sep=CSV_SEP, dtype=str, keep_default_na=False, usecols=usecols)
    finally:
        reader.close()
    return _clean_frame(df)


def iter_badepi_csv(
    path: Path | str, chunksize: int = 500_000, usecols: list[str] | None = None
) -> Iterator[pd.DataFrame]:
    """Lê um CSV grande em blocos (para tabelas de milhões de linhas)."""
    reader = TranscodingReader(path)
    try:
        for chunk in pd.read_csv(
            reader, sep=CSV_SEP, dtype=str, keep_default_na=False, usecols=usecols, chunksize=chunksize
        ):
            yield _clean_frame(chunk)
    finally:
        reader.close()


class ParquetSink:
    """Escreve DataFrames em um arquivo parquet único ou em dataset particionado (hive).

    Permite gravar em blocos: o schema é fixado pelo primeiro bloco e os demais
    são convertidos para ele.
    """

    def __init__(self, path: Path, partition_cols: list[str] | None = None, compression: str = "zstd") -> None:
        self.path = Path(path)
        self.partition_cols = partition_cols
        self.compression = compression
        self._writer: pq.ParquetWriter | None = None
        self._schema: pa.Schema | None = None
        self._chunk = 0
        self.rows = 0
        if self.path.exists():
            shutil.rmtree(self.path) if self.path.is_dir() else self.path.unlink()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, df: pd.DataFrame) -> None:
        table = pa.Table.from_pandas(df, preserve_index=False)
        if self._schema is None:
            self._schema = table.schema
        else:
            table = table.cast(self._schema)
        if self.partition_cols:
            pq.write_to_dataset(
                table,
                root_path=str(self.path),
                partition_cols=self.partition_cols,
                compression=self.compression,
                existing_data_behavior="overwrite_or_ignore",
                basename_template=f"part-{self._chunk:03d}-{{i}}.parquet",
            )
        else:
            if self._writer is None:
                self._writer = pq.ParquetWriter(str(self.path), self._schema, compression=self.compression)
            self._writer.write_table(table)
        self._chunk += 1
        self.rows += len(df)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    def __enter__(self) -> "ParquetSink":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def write_parquet(df: pd.DataFrame, path: Path, partition_cols: list[str] | None = None) -> int:
    with ParquetSink(path, partition_cols) as sink:
        sink.write(df)
        return sink.rows


def read_parquet(path: Path | str, columns: list[str] | None = None, filters=None) -> pd.DataFrame:
    """Lê parquet (arquivo ou dataset particionado hive) para pandas, preservando os dtypes nullable.

    Em datasets particionados o pyarrow devolve a coluna de partição como dicionário; ela é
    decodificada antes da conversão para que os metadados pandas (ex.: Int16) sejam respeitados.
    `filters` aceita a sintaxe do pyarrow, ex.: [("ano_publicacao", ">=", 2020)].
    """
    table = pq.read_table(str(path), columns=columns, filters=filters)
    cols, changed = [], False
    for name in table.column_names:
        col = table[name]
        if pa.types.is_dictionary(col.type):
            col, changed = col.cast(col.type.value_type), True
        cols.append(col)
    if changed:
        table = pa.table(cols, names=table.column_names).replace_schema_metadata(table.schema.metadata)
    return table.to_pandas()


class _JsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, (pd.Timestamp,)):
            return o.isoformat()
        if hasattr(o, "item"):  # numpy scalars
            return o.item()
        if o is pd.NA or (isinstance(o, float) and o != o):
            return None
        return super().default(o)


def write_json(obj, path: Path, indent: int | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, cls=_JsonEncoder, ensure_ascii=False, indent=indent, allow_nan=False)


def read_json(path: Path | str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
