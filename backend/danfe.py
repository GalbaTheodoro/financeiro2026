"""DANFE — a folha de papel que representa a nota fiscal eletrônica.

Gera a página pronta para imprimir (A4 em pé) a partir do XML completo da nota.
Abre numa aba do navegador; o botão "Imprimir" chama a impressão do próprio
navegador, e de lá dá para salvar em PDF — o mesmo caminho da impressão do
contrato, sem precisar de nenhum programa a mais.

Só funciona com o XML completo (nfeProc). Quando a SEFAZ entregou apenas o
resumo da nota, é preciso dar ciência da operação e buscar de novo.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

from .dfe import NS, FORMAS_PAGAMENTO, formatar_chave, formatar_documento

_N = f"{{{NS}}}"

# --------------------------------------------------------------------------- #
# Código de barras da chave de acesso (Code 128-C), desenhado em SVG
# --------------------------------------------------------------------------- #
_PADROES = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 "
    "221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 "
    "221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 "
    "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 "
    "231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 "
    "231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 "
    "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 "
    "112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
    "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 "
    "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 "
    "114131 311141 411131 211412 211214 211232 2331112"
).split()


def codigo_barras_svg(chave: str, altura: int = 44) -> str:
    """Code 128-C da chave de acesso (44 números) como SVG."""
    numeros = "".join(c for c in (chave or "") if c.isdigit())
    if len(numeros) % 2 or not numeros:
        return ""
    valores = [105] + [int(numeros[i:i + 2]) for i in range(0, len(numeros), 2)]
    soma = valores[0] + sum(i * v for i, v in enumerate(valores[1:], start=1))
    valores.append(soma % 103)
    valores.append(106)

    largura_modulo = 1.0
    barras, x = [], 0.0
    for valor in valores:
        barra = True
        for largura in _PADROES[valor]:
            passo = int(largura) * largura_modulo
            if barra:
                barras.append(f'<rect x="{x:.0f}" y="0" width="{passo:.0f}" height="{altura}"/>')
            x += passo
            barra = not barra
    total = x + 10  # margem de silêncio no fim
    return (
        f'<svg class="barras" viewBox="0 0 {total:.0f} {altura}" preserveAspectRatio="none" '
        f'role="img" aria-label="Chave de acesso">{"".join(barras)}</svg>'
    )


# --------------------------------------------------------------------------- #
# Leitura do XML
# --------------------------------------------------------------------------- #
def _t(no, *nomes) -> str:
    if no is None:
        return ""
    for nome in nomes:
        achado = no.find(f".//{_N}{nome}")
        if achado is not None and achado.text:
            return achado.text.strip()
    return ""


def _n(texto: str) -> float:
    try:
        return float(texto)
    except (TypeError, ValueError):
        return 0.0


def _moeda(valor, casas: int = 2) -> str:
    if valor in ("", None):
        return ""
    texto = f"{float(valor):,.{casas}f}"
    return texto.replace(",", "@").replace(".", ",").replace("@", ".")


def _data(texto: str, com_hora: bool = False) -> str:
    if not texto:
        return ""
    try:
        quando = datetime.fromisoformat(texto)
    except ValueError:
        return texto[:10]
    return quando.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


def _escapar(valor) -> str:
    return (str(valor or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _endereco(no) -> str:
    if no is None:
        return ""
    partes = [_t(no, "xLgr"), _t(no, "nro")]
    rua = ", ".join(p for p in partes if p)
    extras = [_t(no, "xCpl"), _t(no, "xBairro")]
    return " - ".join(p for p in [rua] + [e for e in extras if e] if p)


# --------------------------------------------------------------------------- #
# Montagem da folha
# --------------------------------------------------------------------------- #
def _quadro(rotulo: str, valor, classe: str = "") -> str:
    return (f'<div class="quadro {classe}"><span class="rotulo">{_escapar(rotulo)}</span>'
            f'<span class="valor">{_escapar(valor)}</span></div>')


def gerar(xml: str, empresa_nome: str = "") -> str:
    """Devolve a página HTML da DANFE. Levanta ValueError se o XML for resumo."""
    raiz = ET.fromstring(xml)
    inf = raiz.find(f".//{_N}infNFe")
    if inf is None:
        raise ValueError(
            "Esta nota está no sistema apenas como resumo. Dê ciência da operação e "
            "busque os documentos de novo para receber o XML completo e imprimir a DANFE."
        )
    ide = inf.find(f"{_N}ide")
    emit = inf.find(f"{_N}emit")
    dest = inf.find(f"{_N}dest")
    transp = inf.find(f"{_N}transp")
    total = inf.find(f".//{_N}ICMSTot")
    protocolo = raiz.find(f".//{_N}infProt")
    chave = (inf.get("Id") or "").replace("NFe", "")
    entrada = _t(ide, "tpNF") == "0"

    itens = []
    for det in inf.findall(f"{_N}det"):
        prod = det.find(f"{_N}prod")
        imposto = det.find(f"{_N}imposto")
        icms = imposto.find(f".//{_N}ICMS") if imposto is not None else None
        itens.append(f"""<tr>
          <td>{_escapar(_t(prod, 'cProd'))}</td>
          <td class="larga">{_escapar(_t(prod, 'xProd'))}</td>
          <td class="centro">{_escapar(_t(prod, 'NCM'))}</td>
          <td class="centro">{_escapar(_t(icms, 'CST', 'CSOSN'))}</td>
          <td class="centro">{_escapar(_t(prod, 'CFOP'))}</td>
          <td class="centro">{_escapar(_t(prod, 'uCom'))}</td>
          <td class="num">{_moeda(_n(_t(prod, 'qCom')), 3)}</td>
          <td class="num">{_moeda(_n(_t(prod, 'vUnCom')), 4)}</td>
          <td class="num">{_moeda(_n(_t(prod, 'vProd')))}</td>
          <td class="num">{_moeda(_n(_t(icms, 'vBC')))}</td>
          <td class="num">{_moeda(_n(_t(icms, 'vICMS')))}</td>
          <td class="num">{_moeda(_n(_t(imposto.find(f'{_N}IPI') if imposto is not None else None, 'vIPI')))}</td>
          <td class="num">{_moeda(_n(_t(icms, 'pICMS')))}</td>
        </tr>""")

    duplicatas = []
    for dup in inf.findall(f".//{_N}dup"):
        duplicatas.append(
            f'<span class="dup"><b>{_escapar(_t(dup, "nDup") or "-")}</b> '
            f'{_data(_t(dup, "dVenc"))} · R$ {_moeda(_n(_t(dup, "vDup")))}</span>'
        )
    pagamentos = []
    for pag in inf.findall(f".//{_N}detPag"):
        codigo = _t(pag, "tPag")
        pagamentos.append(
            f'<span class="dup">{_escapar(FORMAS_PAGAMENTO.get(codigo, "Outros"))} · '
            f'R$ {_moeda(_n(_t(pag, "vPag")))}</span>'
        )

    complementares = " ".join(x for x in [_t(inf, "infCpl"), _t(inf, "infAdFisco")] if x)
    situacao = ""
    if _t(protocolo, "cStat") in ("101", "135", "155"):
        situacao = '<div class="tarja">NOTA CANCELADA</div>'
    elif _t(protocolo, "cStat") in ("110", "301", "302", "303"):
        situacao = '<div class="tarja">USO DENEGADO</div>'

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DANFE {_escapar(_t(ide, 'nNF'))} — {_escapar(_t(emit, 'xNome'))}</title>
<style>
  :root {{ --linha:#333; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:#eceff1; font-family:Arial,Helvetica,sans-serif; color:#111; }}
  .barra {{ position:sticky; top:0; display:flex; gap:10px; align-items:center;
            padding:10px 16px; background:#14532d; color:#fff; }}
  .barra b {{ flex:1; font-size:14px; font-weight:600; }}
  .barra button, .barra a {{ background:#fff; color:#14532d; border:0; border-radius:6px;
            padding:7px 14px; font-size:13px; font-weight:600; cursor:pointer;
            text-decoration:none; }}
  .folha {{ width:210mm; min-height:297mm; margin:14px auto; padding:6mm; background:#fff;
            box-shadow:0 2px 12px rgba(0,0,0,.2); font-size:8pt; position:relative; }}
  .tarja {{ position:absolute; inset:40% 0 auto 0; text-align:center; font-size:38pt;
            font-weight:700; color:rgba(200,0,0,.25); transform:rotate(-18deg); letter-spacing:4px; }}
  .caixa {{ border:1px solid var(--linha); margin-bottom:2mm; }}
  .faixa {{ display:flex; }}
  .faixa > * {{ border-right:1px solid var(--linha); flex:1; }}
  .faixa > *:last-child {{ border-right:0; }}
  .quadro {{ padding:1mm 1.5mm; min-height:8mm; }}
  .quadro .rotulo {{ display:block; font-size:5.6pt; text-transform:uppercase;
            letter-spacing:.2px; color:#444; }}
  .quadro .valor {{ display:block; font-size:8pt; font-weight:600; word-break:break-word; }}
  .titulo-secao {{ background:#f0f0f0; border-bottom:1px solid var(--linha); padding:.6mm 1.5mm;
            font-size:6.4pt; font-weight:700; text-transform:uppercase; letter-spacing:.4px; }}
  .cabecalho {{ display:flex; }}
  .cabecalho .emitente {{ flex:1.5; padding:2mm; border-right:1px solid var(--linha); }}
  .cabecalho .emitente h1 {{ margin:0 0 1mm; font-size:12pt; }}
  .cabecalho .emitente p {{ margin:0; font-size:7.4pt; line-height:1.35; }}
  .cabecalho .selo {{ width:32mm; text-align:center; padding:2mm 1mm;
            border-right:1px solid var(--linha); }}
  .cabecalho .selo .danfe {{ font-size:15pt; font-weight:700; letter-spacing:1px; }}
  .cabecalho .selo .obs {{ font-size:5.8pt; line-height:1.3; margin:1mm 0; }}
  .cabecalho .selo .sentido {{ font-size:7pt; text-align:left; }}
  .cabecalho .selo .sentido b {{ display:inline-block; border:1px solid var(--linha);
            width:4mm; text-align:center; }}
  .cabecalho .chave {{ flex:1.1; padding:2mm 1mm; text-align:center; }}
  .barras {{ width:100%; height:14mm; display:block; }}
  .barras rect {{ fill:#000; }}
  .chave-numero {{ font-family:"Courier New",monospace; font-size:7.6pt; letter-spacing:.3px;
            margin-top:1mm; word-break:break-all; }}
  table {{ width:100%; border-collapse:collapse; }}
  th, td {{ border:1px solid var(--linha); padding:.7mm 1mm; font-size:6.6pt; }}
  th {{ background:#f0f0f0; font-size:5.8pt; text-transform:uppercase; }}
  td.num {{ text-align:right; white-space:nowrap; }}
  td.centro {{ text-align:center; }}
  td.larga {{ width:34%; }}
  .itens {{ border:1px solid var(--linha); border-top:0; }}
  .itens table {{ border:0; }}
  .itens th, .itens td {{ border-left:0; border-right:1px solid var(--linha); }}
  .dup {{ display:inline-block; margin-right:4mm; font-size:7pt; }}
  .complementares {{ padding:1.5mm; min-height:18mm; font-size:7pt; line-height:1.4; }}
  .canhoto {{ border:1px dashed var(--linha); padding:1.5mm; margin-bottom:2mm;
            display:flex; gap:2mm; font-size:6.6pt; }}
  .canhoto .assina {{ flex:1; border-top:1px solid var(--linha); margin-top:6mm;
            padding-top:.5mm; text-align:center; }}
  @media print {{
    body {{ background:#fff; }}
    .barra {{ display:none; }}
    .folha {{ margin:0; box-shadow:none; width:auto; padding:0; }}
    @page {{ size:A4 portrait; margin:8mm; }}
  }}
  @media (max-width:820px) {{ .folha {{ width:auto; }} }}
</style></head>
<body>
<div class="barra">
  <b>DANFE — nota {_escapar(_t(ide, 'nNF'))}, série {_escapar(_t(ide, 'serie'))}</b>
  <a href="#" onclick="window.close();return false">Fechar</a>
  <button onclick="window.print()">Imprimir / salvar em PDF</button>
</div>

<div class="folha">
{situacao}
  <div class="canhoto">
    <div style="flex:2">RECEBEMOS DE <b>{_escapar(_t(emit, 'xNome'))}</b> OS PRODUTOS CONSTANTES DA
      NOTA FISCAL INDICADA AO LADO
      <div style="display:flex;gap:3mm;margin-top:1mm">
        <span>DATA DE RECEBIMENTO ____/____/______</span>
        <span class="assina">IDENTIFICAÇÃO E ASSINATURA DO RECEBEDOR</span>
      </div>
    </div>
    <div style="width:38mm;text-align:center;border-left:1px dashed var(--linha);padding-left:2mm">
      <b>NF-e</b><br>Nº {_escapar(_t(ide, 'nNF'))}<br>SÉRIE {_escapar(_t(ide, 'serie'))}
    </div>
  </div>

  <div class="caixa cabecalho">
    <div class="emitente">
      <h1>{_escapar(_t(emit, 'xNome'))}</h1>
      <p>{_escapar(_endereco(emit.find(f'{_N}enderEmit') if emit is not None else None))}<br>
         {_escapar(_t(emit, 'xMun'))}/{_escapar(_t(emit, 'UF'))} — CEP {_escapar(_t(emit, 'CEP'))}<br>
         Fone {_escapar(_t(emit, 'fone') or '-')} · {_escapar(_t(emit, 'xFant') or '')}</p>
    </div>
    <div class="selo">
      <div class="danfe">DANFE</div>
      <div class="obs">Documento Auxiliar da Nota Fiscal Eletrônica</div>
      <div class="sentido">
        <b>{'X' if entrada else '&nbsp;'}</b> 0 - ENTRADA<br>
        <b>{'&nbsp;' if entrada else 'X'}</b> 1 - SAÍDA
      </div>
      <div style="margin-top:1.5mm;font-size:8.6pt;font-weight:700">
        Nº {_escapar(_t(ide, 'nNF'))}<br>SÉRIE {_escapar(_t(ide, 'serie'))}
      </div>
    </div>
    <div class="chave">
      {codigo_barras_svg(chave)}
      <div style="font-size:5.8pt;text-transform:uppercase;margin-top:1mm">Chave de acesso</div>
      <div class="chave-numero">{_escapar(formatar_chave(chave))}</div>
      <div style="font-size:6pt;margin-top:1mm">Consulta em www.nfe.fazenda.gov.br/portal</div>
    </div>
  </div>

  <div class="caixa faixa">
    {_quadro('Natureza da operação', _t(ide, 'natOp'))}
    {_quadro('Protocolo de autorização', f"{_t(protocolo, 'nProt')}  {_data(_t(protocolo, 'dhRecbto'), True)}")}
  </div>
  <div class="caixa faixa">
    {_quadro('Inscrição estadual', _t(emit, 'IE'))}
    {_quadro('Inscr. estadual do subst. trib.', _t(emit, 'IEST'))}
    {_quadro('CNPJ do emitente', formatar_documento(_t(emit, 'CNPJ', 'CPF')))}
    {_quadro('Emissão', _data(_t(ide, 'dhEmi') or _t(ide, 'dEmi'), True))}
  </div>

  <div class="caixa">
    <div class="titulo-secao">Destinatário / Remetente</div>
    <div class="faixa" style="border-bottom:1px solid var(--linha)">
      {_quadro('Nome / razão social', _t(dest, 'xNome'))}
      {_quadro('CNPJ / CPF', formatar_documento(_t(dest, 'CNPJ', 'CPF')))}
      {_quadro('Inscrição estadual', _t(dest, 'IE') or 'ISENTO')}
    </div>
    <div class="faixa">
      {_quadro('Endereço', _endereco(dest.find(f'{_N}enderDest') if dest is not None else None))}
      {_quadro('Município', f"{_t(dest, 'xMun')}/{_t(dest, 'UF')}")}
      {_quadro('CEP', _t(dest, 'CEP'))}
      {_quadro('Fone', _t(dest, 'fone'))}
    </div>
  </div>

  <div class="caixa">
    <div class="titulo-secao">Cálculo do imposto</div>
    <div class="faixa" style="border-bottom:1px solid var(--linha)">
      {_quadro('Base de cálculo do ICMS', _moeda(_n(_t(total, 'vBC'))))}
      {_quadro('Valor do ICMS', _moeda(_n(_t(total, 'vICMS'))))}
      {_quadro('Base de cálculo do ICMS ST', _moeda(_n(_t(total, 'vBCST'))))}
      {_quadro('Valor do ICMS ST', _moeda(_n(_t(total, 'vST'))))}
      {_quadro('Valor total dos produtos', _moeda(_n(_t(total, 'vProd'))))}
    </div>
    <div class="faixa">
      {_quadro('Valor do frete', _moeda(_n(_t(total, 'vFrete'))))}
      {_quadro('Valor do seguro', _moeda(_n(_t(total, 'vSeg'))))}
      {_quadro('Desconto', _moeda(_n(_t(total, 'vDesc'))))}
      {_quadro('Outras despesas', _moeda(_n(_t(total, 'vOutro'))))}
      {_quadro('Valor do IPI', _moeda(_n(_t(total, 'vIPI'))))}
      {_quadro('Valor total da nota', _moeda(_n(_t(total, 'vNF'))))}
    </div>
  </div>

  <div class="caixa">
    <div class="titulo-secao">Transportador / volumes transportados</div>
    <div class="faixa">
      {_quadro('Nome', _t(transp, 'xNome') or '-')}
      {_quadro('Frete por conta', {'0': '0 - Emitente', '1': '1 - Destinatário', '2': '2 - Terceiros', '9': '9 - Sem frete'}.get(_t(transp, 'modFrete'), _t(transp, 'modFrete')))}
      {_quadro('Placa', _t(transp, 'placa'))}
      {_quadro('CNPJ / CPF', formatar_documento(_t(transp, 'CNPJ', 'CPF')))}
      {_quadro('Quantidade', _t(transp, 'qVol'))}
      {_quadro('Peso bruto', _moeda(_n(_t(transp, 'pesoB')), 3))}
    </div>
  </div>

  <div class="caixa" style="margin-bottom:0;border-bottom:0">
    <div class="titulo-secao">Dados dos produtos / serviços</div>
  </div>
  <div class="itens">
    <table>
      <thead><tr>
        <th>Código</th><th>Descrição</th><th>NCM</th><th>CST</th><th>CFOP</th><th>Un.</th>
        <th>Qtde</th><th>Vl. unit.</th><th>Vl. total</th><th>BC ICMS</th><th>Vl. ICMS</th>
        <th>Vl. IPI</th><th>% ICMS</th>
      </tr></thead>
      <tbody>{''.join(itens) or '<tr><td colspan="13" class="centro">sem itens</td></tr>'}</tbody>
    </table>
  </div>

  <div class="caixa" style="margin-top:2mm">
    <div class="titulo-secao">Fatura / duplicatas e formas de pagamento</div>
    <div class="complementares" style="min-height:10mm">
      {''.join(duplicatas) or ''}{''.join(pagamentos) or ''}
      {'<span class="dup">sem parcelas informadas</span>' if not duplicatas and not pagamentos else ''}
    </div>
  </div>

  <div class="caixa">
    <div class="titulo-secao">Dados adicionais</div>
    <div class="complementares">{_escapar(complementares) or '&nbsp;'}</div>
  </div>

  <div style="text-align:center;font-size:6pt;color:#555">
    Documento gerado pelo AgroDock a partir do XML autorizado pela SEFAZ{
      ' · ' + _escapar(empresa_nome) if empresa_nome else ''}
  </div>
</div>
</body></html>"""


# --------------------------------------------------------------------------- #
# DANFE em PDF — é o arquivo que vai anexado no e-mail do cliente
# --------------------------------------------------------------------------- #
def pdf_disponivel() -> tuple[bool, str]:
    """A biblioteca que desenha a DANFE em PDF está instalada?

    Serve para a tela avisar **antes** de a primeira nota sair sem o PDF — foi
    assim que se descobriu, tarde demais, que o `pip install` não tinha rodado.
    """
    try:
        from brazilfiscalreport.danfe import Danfe          # noqa: F401
    except ImportError as erro:
        return False, (
            "Falta a biblioteca que desenha a DANFE em PDF "
            f"({erro}). No seu computador, rode o iniciar.bat — ele instala sozinho; "
            "ou, na pasta do projeto: .venv\\Scripts\\activate e depois "
            "pip install -r requirements.txt. No servidor, publique de novo."
        )
    return True, ""


def gerar_pdf(xml: str) -> bytes:
    """Devolve a DANFE em PDF, gerada a partir do XML autorizado.

    A página HTML acima é para ver e imprimir na tela; para **anexar no e-mail**
    é preciso um arquivo, e arquivo de nota fiscal é PDF. Quem desenha é a
    biblioteca `brazilfiscalreport`, que monta o DANFE no layout oficial lendo o
    próprio `nfeProc` — é Python puro (fpdf2), então roda igual no PC e no
    servidor, sem depender de navegador nem de programa instalado.

    Levanta `ValueError` com uma frase clara quando o XML não serve.
    """
    if not (xml or "").strip():
        raise ValueError("Esta nota não tem XML guardado — só a autorizada tem DANFE.")
    if "infNFe" not in xml:
        raise ValueError(
            "Esta nota está no sistema apenas como resumo. Dê ciência da operação e "
            "busque os documentos de novo para receber o XML completo."
        )
    tem, motivo = pdf_disponivel()
    if not tem:
        raise ValueError(motivo)
    from brazilfiscalreport.danfe import Danfe
    try:
        return bytes(Danfe(xml=xml).output())
    except Exception as erro:                             # noqa: BLE001
        raise ValueError(
            f"Não foi possível montar a DANFE em PDF desta nota ({erro})."
        ) from None
