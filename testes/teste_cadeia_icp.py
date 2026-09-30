"""A conexão com a SEFAZ reconhece a ICP-Brasil sem desligar a conferência do certificado.

O SVRS (que autoriza o cupom de GO e TO) usa a cadeia Raiz Brasileira v5 →
SERPRO v4 → SERPRO Final SSL. Sem essas autoridades no contexto TLS a conexão
falha com CERTIFICATE_VERIFY_FAILED.

Rodar:  python -m testes.teste_cadeia_icp
"""
import datetime
import os
import ssl
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from backend import dfe


def _certificado_de_teste():
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TESTE:12345678000199")])
    agora = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
            .public_key(chave.public_key()).serial_number(1)
            .not_valid_before(agora).not_valid_after(agora + datetime.timedelta(days=1))
            .sign(chave, hashes.SHA256()))
    return chave, cert


def main():
    assert os.path.exists(dfe.CADEIA_ICP_BRASIL), "falta backend/certs/icp_brasil.pem"
    chave, cert = _certificado_de_teste()
    ctx = dfe._contexto_ssl(chave, cert, [])

    # a conferência continua ligada
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True

    nomes = set()
    for ca in ctx.get_ca_certs():
        campos = dict(par[0] for par in ca["subject"])
        nomes.add(campos.get("commonName", ""))
    for precisa in ("Autoridade Certificadora Raiz Brasileira v5",
                    "Autoridade Certificadora Raiz Brasileira v10",
                    "Autoridade Certificadora SERPRO v4",
                    "Autoridade Certificadora do SERPRO Final SSL"):
        assert precisa in nomes, f"falta {precisa}"
    print("ok — cadeia ICP-Brasil carregada, conferência do certificado ligada")


if __name__ == "__main__":
    main()
