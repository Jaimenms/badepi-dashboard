"""badepi — pipeline medalhão para os microdados BADEPI (INPI).

Camadas:
  bronze  → zips e CSVs originais, intocados, com manifesto
  silver  → parquet tipado, limpo e com chaves de relacionamento
  gold    → agregações em JSON consumidas pelo dashboard (docs/)
"""

__version__ = "0.1.0"
