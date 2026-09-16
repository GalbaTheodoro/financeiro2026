"""Tela de diagnóstico quando o sistema não consegue ligar.

Sem isto, um endereço de banco errado no Vercel vira só "500 FUNCTION_INVOCATION_FAILED"
e a causa fica escondida no log. Aqui a própria página diz o que aconteceu e o que
fazer — sem nunca mostrar senhas.
"""
import html
import re

_DICAS = [
    (("FIN_DATABASE_URL", "banco na nuvem"),
     "Cadastre FIN_DATABASE_URL no Vercel (Settings → Environment Variables) com o "
     "endereço do Neon e faça Redeploy."),
    (("FIN_SECRET_KEY",),
     "Cadastre FIN_SECRET_KEY no Vercel (Settings → Environment Variables) e faça Redeploy."),
    (("password authentication failed", "authentication failed"),
     "A senha do banco no endereço está errada. No Neon: Connect → Show password → copie o "
     "endereço inteiro de novo, cole em FIN_DATABASE_URL e faça Redeploy."),
    (("could not translate host name", "Name or service not known", "nodename nor servname",
      "getaddrinfo failed", "failed to resolve host"),
     "O nome do servidor no endereço do banco está errado ou incompleto. Copie de novo o "
     "endereço no Neon (botão Connect)."),
    (("timeout", "timed out"),
     "O banco não respondeu a tempo. Confira se o endereço é o do Neon com '-pooler' e se o "
     "projeto no Neon não está suspenso (cota do mês)."),
    (("does not exist",),
     "O nome do banco no fim do endereço não existe. No Neon o padrão é /neondb."),
    (("quota", "exceeded the compute time"),
     "O Neon suspendeu o banco por passar da cota grátis do mês. Volta sozinho no próximo mês."),
    (("invalid dsn", "invalid connection option", "missing \"=\"", "invalid URI"),
     "O endereço do banco está com formato errado. Ele deve começar com postgresql:// e não "
     "pode ter aspas, espaços ou a palavra psql na frente."),
]


def ocultar_senhas(texto: str) -> str:
    texto = str(texto or "")
    texto = re.sub(r"(://[^:/@\s]+:)[^@\s]+@", r"\1****@", texto)
    texto = re.sub(r"(password=)\S+", r"\1****", texto, flags=re.I)
    return texto


def dica_para(texto: str) -> str:
    baixo = (texto or "").lower()
    for chaves, dica in _DICAS:
        if any(c.lower() in baixo for c in chaves):
            return dica
    return ("Copie a mensagem acima e envie para o suporte. No Vercel, a aba Logs mostra os "
            "detalhes completos.")


def resumo_erro(erro: BaseException) -> str:
    texto = f"{type(erro).__name__}: {erro}"
    return ocultar_senhas(texto)[:1500]


def pagina_html(erro_texto: str) -> str:
    dica = dica_para(erro_texto)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgroDock — não foi possível ligar</title>
<style>
body{{margin:0;font-family:system-ui,Segoe UI,sans-serif;background:#f4f6f1;color:#18231d;padding:32px 16px}}
main{{max-width:720px;margin:0 auto;background:#fff;border:1px solid #dce3da;border-radius:12px;padding:24px}}
h1{{font-size:22px;margin:0 0 8px}} p{{line-height:1.55}}
pre{{background:#eef2ec;border-radius:8px;padding:12px;white-space:pre-wrap;word-break:break-word;font-size:13px}}
.dica{{background:#fbf0da;border-radius:8px;padding:12px 14px}}
</style></head><body><main>
<h1>O AgroDock não conseguiu ligar</h1>
<p>O site está no ar, mas algo na configuração impediu o sistema de abrir.</p>
<p><b>O que aconteceu:</b></p>
<pre>{html.escape(erro_texto)}</pre>
<p class="dica"><b>O que fazer:</b> {html.escape(dica)}</p>
<p style="color:#5a675f;font-size:14px">Depois de corrigir, recarregue esta página.</p>
</main></body></html>"""
