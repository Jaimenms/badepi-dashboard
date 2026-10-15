"""Gold — comparativo entre ativos para a página inicial (docs/data/comparativo.json)."""

from __future__ import annotations

import logging
from pathlib import Path

from ..config import DOCS_DATA_DIR, GOLD_DIR, SOURCES
from ..ioutil import read_json, write_json
from .common import ANOS, now_iso, pct

log = logging.getLogger(__name__)
ATIVOS = [("patentes", "Patentes", "patentes.html", "concessão"), ("marcas", "Marcas", "marcas.html", "registro"),
          ("desenho_industrial", "Desenhos industriais", "desenhos.html", "registro"), ("indicacao_geografica", "Indicações geográficas", "indicacoes.html", "registro")]


def build(force: bool = False):
    itens = []
    for slug, label, pagina, termo in ATIVOS:
        d = DOCS_DATA_DIR / slug
        if not (d / "resumo.json").exists():
            log.warning("[comparativo] %s sem gold; pulando", slug)
            continue
        r = read_json(d / "resumo.json"); s = read_json(d / "serie_depositos.json"); sc = read_json(d / "situacao_coorte.json")
        tempo = read_json(d / ("tempo_concessao.json" if slug == "patentes" else "tempo_registro.json"))
        fun = read_json(d / "funil.json"); k = r["kpis"]
        tot = sc["total"]; n = sum(tot.values())
        base = s["total"][0] or 1
        itens.append({
            "slug": slug, "label": label, "pagina": pagina, "termo_concessao": termo, "kpis": k,
            "serie_total": s["total"], "serie_indice": [round(v / base * 100, 1) for v in s["total"]],
            "share_residentes_serie": [pct(a, b) for a, b in zip(s["residente"], s["total"])],
            "situacao_total": tot, "situacao_pct": {kk: pct(v, n) for kk, v in tot.items()},
            "tempo_mediana_por_ano": {str(x["ano"]): x["mediana"] for x in tempo["por_ano"]},
            "tempo_mediana_recente": next((x["mediana"] for x in reversed(tempo["por_ano"]) if x["n"] >= 30), (tempo["por_ano"][-1]["mediana"] if tempo["por_ano"] else None)),
            "funil_total": {kk: sum(fun[kk]) for kk in ["depositados", "publicados", "decididos", "concedidos", "vigentes"] if kk in fun},
            "data_referencia": r.get("data_referencia"),
        })
    out = {"gerado_em": now_iso(), "anos": ANOS, "ativos": itens}
    for p in [GOLD_DIR / "comparativo.json", DOCS_DATA_DIR / "comparativo.json"]:
        write_json(out, Path(p))
    log.info("[comparativo] comparativo.json ok (%d ativos)", len(itens))
    return out
