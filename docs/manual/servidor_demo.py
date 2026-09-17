"""Sobe o AgroDock para as capturas do manual, sem internet: cotações e notícias vêm
das respostas gravadas em testes/dados_mercado e testes/dados_cotacoes."""
import os, sys, random, tempfile
from datetime import date, timedelta
from pathlib import Path
APP = Path('/home/claude/app'); sys.path.insert(0, str(APP))
os.environ['FIN_DATABASE_URL'] = f"sqlite:///{tempfile.mkdtemp()}/manual.db"
os.environ['FIN_MASTER_EMAIL'] = 'dono@agrodock.com.br'
from backend import cotacoes, mercado
D1 = APP/'testes/dados_mercado'; D2 = APP/'testes/dados_cotacoes'
def baixar(url):
    if 'finance.yahoo.com' in url:
        s = url.split('/chart/')[1].split('?')[0].replace('%3D', '=')
        f = D2/f'yahoo_{s}.json'
        if f.exists(): return f.read_text()
        raise OSError('sem gravação')
    if 'awesomeapi' in url: return (D2/f"awesome_{url.split('/')[-1]}.json").read_text()
    if 'olinda' in url: return (D1/'bcb_ptax_periodo.json').read_text()
    if '/cotacoes/cafe/' in url: return (D1/f"na_{url.rstrip('/').split('/')[-1]}.html").read_text()
    m = {'agnocafe': 'agnocafe.html', '/noticias/cafe/': 'na_noticias_cafe.html', 'agricultura/cafe/feed': 'canal_cafe.xml',
         'canalrural.com.br/feed': 'canal_geral.xml', 'agronegocios': 'g1_agro.xml', 'sul-de-minas': 'g1_sul.xml', 'triangulo': 'g1_triangulo.xml'}
    for k, v in m.items():
        if k in url: return (D1/v).read_text()
    raise OSError(url)
cotacoes.baixar = baixar
from backend.main import app
from backend.database import SessionLocal
from backend.migracao import preparar_banco
preparar_banco()
db = SessionLocal()
mercado.atualizar_mercado(db)
random.seed(3); linhas = []
for grupo, item, base, cid, tipo in [('ny', 'Dezembro/26', 281.55, None, 'pontos'),
                                     ('fisico_6_duro', 'Patrocínio/MG (Expocaccer)', 1635, 'Patrocínio', '%'),
                                     ('fisico_6_7', 'Patrocínio/MG (Expocaccer)', 1600, 'Patrocínio', '%')]:
    v = base
    for k in range(3, 80):
        d = date(2026, 9, 16) - timedelta(days=k)
        if d.weekday() >= 5: continue
        v = v * (1 + random.uniform(-0.018, 0.017))
        linhas.append(mercado._linha(grupo, item, d, round(v, 2), round(random.uniform(-2, 2), 2), tipo, cid))
mercado.gravar_historico(db, linhas)
mercado.atualizar_noticias(db)
db.close()
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=8000, log_level='warning')
