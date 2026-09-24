"""Envio de e-mail pelo sistema, usando a conta da própria empresa.

Por que é assim
---------------
O AgroDock não tem servidor de e-mail. Quem envia é a **conta de e-mail da
empresa** — a mesma do Gmail, do Outlook ou do provedor do domínio —, e o
sistema só conversa com o servidor SMTP dela. Duas consequências práticas:

* quem recebe vê o e-mail vindo da empresa, não de um endereço estranho, e
  responde direto para ela;
* é preciso guardar a senha daquela conta. Ela fica **cifrada** no banco
  (AES-GCM, chave derivada de FIN_SECRET_KEY, igual ao certificado digital) e
  nenhuma rota a devolve.

Sobre senha de app
------------------
Gmail e Microsoft não aceitam mais a senha normal da conta em programas como
este: é preciso gerar uma **senha de aplicativo** na conta. Quando o servidor
recusa a senha, a mensagem de erro daqui já explica isso.

O que é enviado
---------------
A nota autorizada vai com dois anexos: o **XML** (é o documento fiscal de
verdade, o que o contador escritura) e a **DANFE em PDF** (é a folha que se
imprime e se confere). O texto do e-mail é editável na configuração.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from .config import SECRET_KEY

# Portas e servidores sugeridos na tela, para não precisar procurar.
SUGESTOES = (
    {"nome": "Gmail / Google Workspace", "servidor": "smtp.gmail.com",
     "porta": 587, "seguranca": "TLS",
     "aviso": "O Gmail exige uma senha de app: conta Google > Segurança > "
              "Verificação em duas etapas > Senhas de app. A senha normal não funciona."},
    {"nome": "Outlook / Microsoft 365", "servidor": "smtp.office365.com",
     "porta": 587, "seguranca": "TLS",
     "aviso": "Com verificação em duas etapas ligada, a Microsoft também exige "
              "senha de app em vez da senha da conta."},
    {"nome": "Servidor do meu domínio", "servidor": "mail.seudominio.com.br",
     "porta": 587, "seguranca": "TLS",
     "aviso": "Peça ao provedor da hospedagem o servidor de saída (SMTP), a porta "
              "e se usa TLS (587) ou SSL (465)."},
)

ASSUNTO_PADRAO = "NF-e {numero} - {empresa}"
TEXTO_PADRAO = (
    "Prezado cliente,\n\n"
    "Segue em anexo a nota fiscal eletrônica {numero}, emitida por {empresa}.\n\n"
    "Vão dois arquivos: o XML, que é o documento fiscal e deve ser entregue ao seu "
    "contador, e a DANFE em PDF, que é a folha para conferência e impressão.\n\n"
    "Chave de acesso: {chave}\n\n"
    "Qualquer dúvida, é só responder este e-mail.\n\n"
    "{empresa}"
)


class ErroEmail(Exception):
    """Falha no envio, já com a frase que a tela mostra para o usuário."""


# --------------------------------------------------------------------------- #
# Guarda da senha
# --------------------------------------------------------------------------- #
def _chave_cofre() -> bytes:
    return hashlib.sha256(f"agrodock-email::{SECRET_KEY}".encode()).digest()


def cifrar(texto: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    selado = AESGCM(_chave_cofre()).encrypt(nonce, (texto or "").encode(), None)
    return base64.b64encode(nonce + selado).decode()


def decifrar(guardado: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not guardado:
        return ""
    bruto = base64.b64decode(guardado)
    try:
        return AESGCM(_chave_cofre()).decrypt(bruto[:12], bruto[12:], None).decode()
    except Exception:  # noqa: BLE001
        raise ErroEmail(
            "Não foi possível abrir a senha de e-mail guardada. Isso acontece quando a "
            "chave de segurança do sistema (FIN_SECRET_KEY) muda. Digite a senha de novo "
            "na configuração de e-mail da empresa."
        ) from None


# --------------------------------------------------------------------------- #
# Endereços
# --------------------------------------------------------------------------- #
_ENDERECO = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


def endereco_valido(texto: str | None) -> bool:
    return bool(_ENDERECO.match((texto or "").strip()))


def separar(texto: str | None) -> list[str]:
    """Aceita vários endereços separados por vírgula, ponto e vírgula ou espaço."""
    partes = re.split(r"[;,\s]+", (texto or "").strip())
    return [p for p in partes if endereco_valido(p)]


# --------------------------------------------------------------------------- #
# Envio
# --------------------------------------------------------------------------- #
def _erro_amigavel(erro: Exception, servidor: str, porta: int) -> ErroEmail:
    """Traduz a falha do servidor para uma frase que diz o que fazer."""
    if isinstance(erro, smtplib.SMTPAuthenticationError):
        return ErroEmail(
            "O servidor recusou o usuário e a senha. Se a conta é Gmail ou Microsoft, "
            "use uma senha de app (a senha normal não funciona em programas). "
            "Confira também se o usuário é o e-mail inteiro."
        )
    if isinstance(erro, smtplib.SMTPRecipientsRefused):
        return ErroEmail("O servidor recusou o endereço de destino. Confira o e-mail "
                         "cadastrado no cliente.")
    if isinstance(erro, smtplib.SMTPSenderRefused):
        return ErroEmail(
            "O servidor recusou o remetente. O e-mail do remetente precisa ser o mesmo "
            "da conta que está enviando."
        )
    if isinstance(erro, socket.gaierror):
        return ErroEmail(f"O servidor '{servidor}' não foi encontrado. Confira o nome do "
                         "servidor de saída (SMTP) na configuração.")
    if isinstance(erro, (socket.timeout, TimeoutError)):
        return ErroEmail(
            f"O servidor '{servidor}' não respondeu na porta {porta}. Confira a porta "
            "(587 para TLS, 465 para SSL) — algumas redes bloqueiam essas portas."
        )
    if isinstance(erro, ssl.SSLError):
        return ErroEmail(
            f"Falha de segurança ao falar com '{servidor}' na porta {porta}. Quase sempre "
            "é TLS e SSL trocados: 587 usa TLS, 465 usa SSL."
        )
    if isinstance(erro, (ConnectionRefusedError, OSError)):
        return ErroEmail(f"Não foi possível conectar em '{servidor}' na porta {porta}. "
                         "Confira o servidor, a porta e a segurança (TLS/SSL).")
    return ErroEmail(f"O envio falhou: {erro}")


def _conectar(servidor: str, porta: int, seguranca: str, tempo: int):
    seguranca = (seguranca or "TLS").upper()
    if seguranca == "SSL":
        return smtplib.SMTP_SSL(servidor, porta, timeout=tempo,
                                context=ssl.create_default_context())
    conexao = smtplib.SMTP(servidor, porta, timeout=tempo)
    if seguranca == "TLS":
        conexao.starttls(context=ssl.create_default_context())
    return conexao


def enviar(config, para: list[str], assunto: str, texto: str,
           anexos: list[tuple[str, bytes, str]] | None = None,
           copias: list[str] | None = None, tempo: int = 30) -> dict:
    """Manda um e-mail pela conta da empresa.

    `anexos` é uma lista de (nome do arquivo, conteúdo, tipo). Devolve para quem
    foi. Levanta `ErroEmail` com uma frase pronta para a tela.
    """
    servidor = (getattr(config, "servidor", "") or "").strip()
    porta = int(getattr(config, "porta", 0) or 587)
    if not servidor:
        raise ErroEmail("A empresa ainda não tem o envio de e-mail configurado. "
                        "Vá em Cadastros > Empresas > Configurar e-mail.")
    remetente = (getattr(config, "remetente_email", "") or
                 getattr(config, "usuario", "") or "").strip()
    if not endereco_valido(remetente):
        raise ErroEmail("Falta o e-mail do remetente na configuração de e-mail da empresa.")

    destinos = [e for e in (para or []) if endereco_valido(e)]
    copias = [e for e in (copias or []) if endereco_valido(e) and e not in destinos]
    if not destinos and not copias:
        raise ErroEmail("Não há para quem enviar: o cliente desta nota está sem e-mail "
                        "no cadastro.")
    if not destinos:                       # só cópias: promove a primeira
        destinos, copias = copias[:1], copias[1:]

    mensagem = EmailMessage()
    mensagem["From"] = formataddr(
        ((getattr(config, "remetente_nome", "") or "").strip(), remetente))
    mensagem["To"] = ", ".join(destinos)
    if copias:
        mensagem["Cc"] = ", ".join(copias)
    responder = (getattr(config, "responder_para", "") or "").strip()
    if endereco_valido(responder):
        mensagem["Reply-To"] = responder
    mensagem["Subject"] = assunto or "Nota fiscal eletrônica"
    mensagem.set_content(texto or "")
    for nome, conteudo, tipo in (anexos or []):
        principal, _, secundario = (tipo or "application/octet-stream").partition("/")
        mensagem.add_attachment(conteudo, maintype=principal,
                                subtype=secundario or "octet-stream", filename=nome)

    usuario = (getattr(config, "usuario", "") or remetente).strip()
    senha = decifrar(getattr(config, "senha", "") or "")
    try:
        with _conectar(servidor, porta, getattr(config, "seguranca", "TLS"), tempo) as smtp:
            if senha:
                smtp.login(usuario, senha)
            smtp.send_message(mensagem, from_addr=parseaddr(remetente)[1] or remetente,
                              to_addrs=destinos + copias)
    except ErroEmail:
        raise
    except Exception as erro:              # noqa: BLE001
        raise _erro_amigavel(erro, servidor, porta) from None
    return {"para": destinos, "copia": copias, "de": remetente}


# --------------------------------------------------------------------------- #
# A mensagem da nota fiscal
# --------------------------------------------------------------------------- #
def _preencher(modelo: str, **dados) -> str:
    """Troca {numero}, {empresa} e {chave} no texto — sem quebrar se sobrar chave."""
    texto = modelo or ""
    for campo, valor in dados.items():
        texto = texto.replace("{" + campo + "}", str(valor or ""))
    return texto


def mensagem_da_nota(config, nota, empresa) -> tuple[str, str]:
    """Assunto e texto do e-mail da nota, já com os dados dela no lugar."""
    dados = {
        "numero": nota.numero or "",
        "empresa": (getattr(empresa, "razao_social", "") or "").strip(),
        "chave": getattr(nota, "chave", "") or "",
    }
    assunto = _preencher(getattr(config, "assunto", "") or ASSUNTO_PADRAO, **dados)
    texto = _preencher(getattr(config, "texto", "") or TEXTO_PADRAO, **dados)
    return assunto.strip(), texto


def anexos_da_nota(nota) -> tuple[list[tuple[str, bytes, str]], str]:
    """Os dois arquivos que vão na nota: o XML e a DANFE em PDF.

    Devolve `(anexos, aviso)`. Se a DANFE não puder ser desenhada, o XML vai
    assim mesmo — é ele o documento fiscal, e ficar sem enviar nada seria pior —,
    mas o `aviso` explica por quê. **O aviso não pode ser engolido**: já
    aconteceu de o PDF faltar por falta da biblioteca e ninguém ficar sabendo,
    porque o e-mail saía dizendo que tinha dado tudo certo.
    """
    from . import danfe

    nome = (getattr(nota, "chave", "") or f"nota-{nota.id}").replace("NFe", "")
    xml = getattr(nota, "xml", "") or ""
    if not xml.strip():
        raise ErroEmail("Esta nota não tem XML guardado — só a autorizada pode ser enviada.")
    anexos = [(f"{nome}.xml", xml.encode("utf-8"), "application/xml")]
    try:
        anexos.append((f"{nome}.pdf", danfe.gerar_pdf(xml), "application/pdf"))
    except ValueError as erro:
        return anexos, str(erro)
    return anexos, ""
