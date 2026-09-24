"""Servidor SMTP de mentira, para testar envio de e-mail sem mandar nada.

Sobe em 127.0.0.1 numa porta livre, fala o mínimo de SMTP para o `smtplib` do
Python se entender, e guarda na memória tudo que recebe. Nenhuma mensagem sai
para a internet.

Uso:

    from smtp_de_mentira import CaixaDeEntrada, subir_smtp

    caixa = CaixaDeEntrada()
    porta = subir_smtp(caixa)
    ...
    caixa.ultima["mensagem"]["Subject"]
"""
import email
import socket
import threading
from email import policy


class CaixaDeEntrada:
    """Guarda as mensagens que o servidor falso recebeu."""

    def __init__(self):
        self.mensagens = []
        self.usuario = None
        self.senha_certa = "segredo-de-teste"

    def limpar(self):
        self.mensagens.clear()

    @property
    def ultima(self):
        return self.mensagens[-1] if self.mensagens else None



def _atender(conexao, caixa: CaixaDeEntrada):
    """Fala o mínimo de SMTP para o smtplib do Python se entender."""
    arquivo = conexao.makefile("rwb")

    def responder(linha):
        arquivo.write(linha.encode() + b"\r\n")
        arquivo.flush()

    responder("220 smtp-de-mentira pronto")
    envelope = {"de": None, "para": [], "dados": b""}
    autenticado = False
    while True:
        linha = arquivo.readline()
        if not linha:
            break
        comando = linha.decode("utf-8", "replace").strip()
        maiusculo = comando.upper()
        if maiusculo.startswith(("HELO", "EHLO")):
            responder("250-smtp-de-mentira")
            responder("250-AUTH PLAIN LOGIN")
            responder("250 OK")
        elif maiusculo.startswith("AUTH"):
            # uma linha de credencial pode vir junto ou na linha seguinte
            if len(comando.split()) < 3:
                responder("334 ok")
                arquivo.readline()
            import base64
            try:
                partes = comando.split()
                bruto = base64.b64decode(partes[2]).decode() if len(partes) > 2 else ""
                senha = bruto.split("\x00")[-1]
            except Exception:  # noqa: BLE001
                senha = ""
            if senha == caixa.senha_certa:
                autenticado = True
                responder("235 autenticado")
            else:
                responder("535 5.7.8 Username and Password not accepted")
        elif maiusculo.startswith("MAIL FROM"):
            if not autenticado:
                responder("530 5.7.0 Authentication required")
                continue
            envelope["de"] = comando.split(":", 1)[1].strip().strip("<>")
            responder("250 OK")
        elif maiusculo.startswith("RCPT TO"):
            envelope["para"].append(comando.split(":", 1)[1].strip().strip("<>"))
            responder("250 OK")
        elif maiusculo == "DATA":
            responder("354 manda")
            corpo = b""
            while True:
                pedaco = arquivo.readline()
                if not pedaco or pedaco in (b".\r\n", b".\n"):
                    break
                corpo += pedaco
            envelope["dados"] = corpo
            caixa.mensagens.append({
                "de": envelope["de"],
                "para": list(envelope["para"]),
                "mensagem": email.message_from_bytes(corpo, policy=policy.default),
            })
            envelope = {"de": None, "para": [], "dados": b""}
            responder("250 Mensagem aceita")
        elif maiusculo == "QUIT":
            responder("221 tchau")
            break
        elif maiusculo == "RSET":
            envelope = {"de": None, "para": [], "dados": b""}
            responder("250 OK")
        else:
            responder("250 OK")
    try:
        conexao.close()
    except OSError:
        pass


def subir_smtp(caixa: CaixaDeEntrada) -> int:
    tomada = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tomada.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tomada.bind(("127.0.0.1", 0))
    tomada.listen(8)
    porta = tomada.getsockname()[1]

    def laco():
        while True:
            try:
                conexao, _ = tomada.accept()
            except OSError:
                return
            threading.Thread(target=_atender, args=(conexao, caixa), daemon=True).start()

    threading.Thread(target=laco, daemon=True).start()
    return porta


