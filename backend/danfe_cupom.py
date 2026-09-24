"""DANFE NFC-e — o cupom de papel, no tamanho da bobina de 80 mm.

Não é a DANFE da nota fiscal em miniatura: é outro documento, com layout
próprio. O que a SEFAZ exige que apareça:

* identificação do emitente (razão social, CNPJ, endereço);
* o aviso "DANFE NFC-e - Documento Auxiliar da Nota Fiscal de Consumidor
  Eletrônica";
* os itens com código, descrição, quantidade, unidade, valor unitário e total;
* o total, as formas de pagamento e o troco;
* os dados do consumidor, ou a frase "CONSUMIDOR NAO IDENTIFICADO";
* a chave de acesso em números, para consultar digitando;
* o **QR Code**, que é o jeito rápido de conferir;
* o protocolo de autorização.

A página sai pronta para a impressora térmica: 80 mm de largura, sem margem, com
`@page` ajustado. Imprimir é o botão do próprio navegador — o mesmo caminho da
DANFE e do contrato, sem depender de nada instalado.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime

from .dfe import NS, FORMAS_PAGAMENTO, formatar_chave, formatar_documento

_N = f"{{{NS}}}"


def _t(no, *nomes) -> str:
    """Texto da primeira tag encontrada, em qualquer profundidade."""
    for nome in nomes:
        if no is None:
            return ""
        achado = no.find(f".//{_N}{nome}")
        if achado is not None and (achado.text or "").strip():
            return achado.text.strip()
    return ""


def _moeda(valor) -> str:
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0
    return f"{numero:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _quantidade(valor) -> str:
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0
    texto = f"{numero:.3f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",") or "0"


def _escapar(valor) -> str:
    texto = "" if valor is None else str(valor)
    return (texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _qrcode_svg(texto: str) -> str:
    """O QR Code em SVG, desenhado aqui mesmo. Vazio se a biblioteca faltar."""
    if not texto:
        return ""
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:                                   # pragma: no cover
        return ""
    import io

    imagem = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage,
                         box_size=9, border=1)
    buffer = io.BytesIO()
    imagem.save(buffer)
    svg = buffer.getvalue().decode("utf-8")
    return re.sub(r"^<\?xml[^>]*\?>\s*", "", svg)


def gerar(xml: str, empresa=None) -> str:
    """A página do cupom, pronta para imprimir. Levanta ValueError se o XML não serve."""
    raiz = ET.fromstring(xml)
    inf = raiz.find(f".//{_N}infNFe")
    if inf is None:
        raise ValueError("Este cupom não tem o XML completo guardado.")
    ide = inf.find(f"{_N}ide")
    if _t(ide, "mod") != "65":
        raise ValueError("Este documento não é um cupom fiscal (modelo 65).")

    emit = inf.find(f"{_N}emit")
    dest = inf.find(f"{_N}dest")
    total = inf.find(f".//{_N}ICMSTot")
    protocolo = raiz.find(f".//{_N}infProt")
    suplemento = raiz.find(f".//{_N}infNFeSupl")
    chave = (inf.get("Id") or "").replace("NFe", "")
    homologacao = _t(ide, "tpAmb") == "2"
    cancelado = _t(raiz, "tpEvento") == "110111"

    endereco_emit = emit.find(f"{_N}enderEmit") if emit is not None else None
    partes_endereco = [
        _t(endereco_emit, "xLgr"), _t(endereco_emit, "nro"),
        _t(endereco_emit, "xBairro"), _t(endereco_emit, "xMun"),
        _t(endereco_emit, "UF"),
    ]
    endereco = ", ".join(p for p in partes_endereco if p)

    linhas = []
    for det in inf.findall(f"{_N}det"):
        produto = det.find(f"{_N}prod")
        quantidade = _quantidade(_t(produto, "qCom"))
        unitario = _moeda(_t(produto, "vUnCom"))
        linhas.append(f"""
          <tr>
            <td class="cod">{_escapar(_t(produto, 'cProd'))}</td>
            <td class="desc">{_escapar(_t(produto, 'xProd'))}</td>
            <td class="qtd">{quantidade}</td>
            <td class="un">{_escapar(_t(produto, 'uCom'))}</td>
            <td class="vun">{unitario}</td>
            <td class="vtot">{_moeda(_t(produto, 'vProd'))}</td>
          </tr>""")

    pagamentos = []
    grupo_pag = inf.find(f"{_N}pag")
    for det_pag in (grupo_pag.findall(f"{_N}detPag") if grupo_pag is not None else []):
        codigo = _t(det_pag, "tPag")
        pagamentos.append(
            f"<div class='linha'><span>{_escapar(FORMAS_PAGAMENTO.get(codigo, 'Outros'))}"
            f"</span><span>{_moeda(_t(det_pag, 'vPag'))}</span></div>")
    troco = _t(grupo_pag, "vTroco") if grupo_pag is not None else ""

    if dest is not None:
        documento = _t(dest, "CPF") or _t(dest, "CNPJ")
        nome_dest = _t(dest, "xNome")
        consumidor = f"CONSUMIDOR: {formatar_documento(documento)}"
        if nome_dest and not homologacao:
            consumidor += f" - {_escapar(nome_dest)}"
    else:
        consumidor = "CONSUMIDOR NAO IDENTIFICADO"

    emitida_em = _t(ide, "dhEmi")[:19].replace("T", " ")
    try:
        emitida_em = datetime.fromisoformat(_t(ide, "dhEmi")).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        pass

    qr = _qrcode_svg(_t(suplemento, "qrCode"))
    quantidade_itens = len(inf.findall(f"{_N}det"))

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Cupom {_escapar(_t(ide, 'nNF'))}</title>
<style>
  @page {{ size: 80mm auto; margin: 2mm; }}
  * {{ box-sizing: border-box; }}
  body {{ width: 76mm; margin: 0 auto; padding: 2mm 0 6mm;
         font: 11px/1.35 'Courier New', monospace; color: #000; background: #fff; }}
  .centro {{ text-align: center; }}
  .forte {{ font-weight: bold; }}
  .traco {{ border-top: 1px dashed #000; margin: 5px 0; }}
  .topo {{ font-size: 11px; }}
  .topo .nome {{ font-size: 13px; font-weight: bold; }}
  .aviso {{ font-size: 11px; font-weight: bold; margin: 6px 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
  th {{ text-align: left; font-weight: bold; border-bottom: 1px solid #000; padding: 2px 0; }}
  td {{ padding: 1px 0; vertical-align: top; }}
  .cod {{ width: 13%; }} .desc {{ width: 37%; }} .qtd {{ width: 12%; text-align: right; }}
  .un {{ width: 10%; text-align: center; }} .vun {{ width: 14%; text-align: right; }}
  .vtot {{ width: 14%; text-align: right; }}
  .linha {{ display: flex; justify-content: space-between; }}
  .total {{ font-size: 14px; font-weight: bold; }}
  .chave {{ word-break: break-all; font-size: 10px; }}
  .qr svg {{ width: 45mm; height: 45mm; }}
  .homologacao {{ border: 2px solid #000; padding: 4px; margin: 6px 0;
                  font-weight: bold; font-size: 11px; }}
  .cancelado {{ color: #000; border: 2px solid #000; padding: 4px; margin: 6px 0;
                font-weight: bold; }}
  .barra {{ position: fixed; top: 0; left: 0; right: 0; background: #0f172a; color: #fff;
            padding: 8px; text-align: center; font-family: system-ui, sans-serif; }}
  .barra button {{ font-size: 14px; padding: 6px 18px; cursor: pointer; }}
  @media print {{ .barra {{ display: none; }} body {{ padding-top: 0; }} }}
  @media screen {{ body {{ margin-top: 54px; border: 1px solid #cbd5e1; padding: 8px; }} }}
</style></head>
<body>
<div class="barra">
  <button onclick="window.print()">Imprimir o cupom</button>
</div>

<div class="centro topo">
  <div class="nome">{_escapar(_t(emit, 'xFant') or _t(emit, 'xNome'))}</div>
  <div>{_escapar(_t(emit, 'xNome'))}</div>
  <div>CNPJ {formatar_documento(_t(emit, 'CNPJ'))}
       {('IE ' + _escapar(_t(emit, 'IE'))) if _t(emit, 'IE') else ''}</div>
  <div>{_escapar(endereco)}</div>
</div>

<div class="traco"></div>
<div class="centro aviso">
  DANFE NFC-e<br>Documento Auxiliar da<br>Nota Fiscal de Consumidor Eletronica
</div>
{'<div class="centro homologacao">EMITIDA EM AMBIENTE DE HOMOLOGACAO<br>SEM VALOR FISCAL</div>' if homologacao else ''}
{'<div class="centro cancelado">CUPOM CANCELADO</div>' if cancelado else ''}
<div class="traco"></div>

<table>
  <tr><th class="cod">COD</th><th class="desc">DESCRICAO</th><th class="qtd">QTD</th>
      <th class="un">UN</th><th class="vun">VL UN</th><th class="vtot">VL TOT</th></tr>
  {''.join(linhas)}
</table>

<div class="traco"></div>
<div class="linha"><span>Qtd. total de itens</span><span>{quantidade_itens}</span></div>
<div class="linha"><span>Valor dos produtos</span><span>{_moeda(_t(total, 'vProd'))}</span></div>
{f'<div class="linha"><span>Desconto</span><span>{_moeda(_t(total, "vDesc"))}</span></div>'
  if float(_t(total, 'vDesc') or 0) else ''}
<div class="linha total"><span>VALOR TOTAL R$</span><span>{_moeda(_t(total, 'vNF'))}</span></div>

<div class="traco"></div>
<div class="forte">FORMA DE PAGAMENTO</div>
{''.join(pagamentos)}
{f'<div class="linha"><span>Troco</span><span>{_moeda(troco)}</span></div>' if troco and float(troco or 0) else ''}

<div class="traco"></div>
<div class="centro">Consulte pela chave de acesso em<br>
  {_escapar(_t(suplemento, 'urlChave'))}</div>
<div class="centro chave">{formatar_chave(chave)}</div>

<div class="traco"></div>
<div class="centro">{_escapar(consumidor)}</div>

<div class="traco"></div>
<div class="centro qr">{qr}</div>

<div class="centro" style="margin-top:6px">
  <div>NFC-e n. {_escapar(_t(ide, 'nNF'))} Serie {_escapar(_t(ide, 'serie'))}</div>
  <div>{_escapar(emitida_em)}</div>
  {f"<div>Protocolo de autorizacao<br>{_escapar(_t(protocolo, 'nProt'))}</div>"
    if protocolo is not None else '<div>Sem protocolo de autorizacao</div>'}
</div>

<div class="traco"></div>
<div class="centro" style="font-size:9px">
  Emitido pelo AgroDock{(' - ' + _escapar(getattr(empresa, 'razao_social', '')))
    if empresa is not None and getattr(empresa, 'razao_social', '') else ''}
</div>
</body></html>"""
