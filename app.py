import os
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from dotenv import load_dotenv
import xml.etree.ElementTree as ET

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configurações
TOKEN_SECRETO = os.getenv('TOKEN_SECRETO', 'seu_token_secreto')
DEFAULT_VALOR_KM = float(os.getenv('DEFAULT_VALOR_KM', 7.0))
TRAY_API_URL = os.getenv('TRAY_API_URL', '')
TRAY_API_TOKEN = os.getenv('TRAY_API_TOKEN', '')

# ============================================================================
# CENTROS DE DISTRIBUIÇÃO - 5 CDs COBRINDO TODO BRASIL
# ============================================================================
CENTROS_DISTRIBUICAO = {
    "RS": {
        "nome": "CD Sul - Rio Grande do Sul",
        "cidade": "Frederico Westphalen",
        "uf": "RS",
        "cep": "98400000",
        "codigo_ibge": 4307708,
        "lat": -27.3636,
        "lon": -53.3978,
        "codigo_cd_tray": "CD_RS"
    },
    "SC": {
        "nome": "CD Sudeste - Santa Catarina",
        "cidade": "Joinville",
        "uf": "SC",
        "cep": "89239250",
        "codigo_ibge": 4209102,
        "lat": -26.3045,
        "lon": -48.8487,
        "codigo_cd_tray": "CD_SC"
    },
    "MG": {
        "nome": "CD Sudeste - Minas Gerais",
        "cidade": "Montes Claros",
        "uf": "MG",
        "cep": "39404627",
        "codigo_ibge": 3143302,
        "lat": -16.7350,
        "lon": -43.8619,
        "codigo_cd_tray": "CD_MG"
    },
    "MS": {
        "nome": "CD Centro-Oeste - Mato Grosso do Sul",
        "cidade": "Campo Grande",
        "uf": "MS",
        "cep": "79108630",
        "codigo_ibge": 5002704,
        "lat": -20.4697,
        "lon": -54.6201,
        "codigo_cd_tray": "CD_MS"
    },
    "CE": {
        "nome": "CD Nordeste - Ceará",
        "cidade": "Tauá",
        "uf": "CE",
        "cep": "63660000",
        "codigo_ibge": 2313302,
        "lat": -6.0014,
        "lon": -40.2925,
        "codigo_cd_tray": "CD_CE"
    }
}

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def haversine(lat1, lon1, lat2, lon2):
    """
    Calcula a distância em km entre dois pontos usando Haversine
    Multiplica por 1.15 pois rodovias são ~15% maiores que linha reta
    """
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    km = 6371 * c
    
    # Fator de ajuste para rodovias (15% maior que linha reta)
    return km * 1.15


def buscar_coordenadas_ibge(cep):
    """
    Busca coordenadas reais via API IBGE
    1. Busca município pelo CEP (ViaCEP)
    2. Busca código IBGE do município
    3. Obtém coordenadas oficiais
    """
    try:
        # Remove formatação do CEP
        cep = cep.replace('-', '').replace('.', '').strip()
        
        print(f"[IBGE] Buscando município para CEP {cep}...")
        
        # 1. Busca município via ViaCEP
        response = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=5)
        
        if response.status_code != 200:
            print(f"[IBGE] ⚠️  Erro no ViaCEP: {response.status_code}")
            return None
        
        data = response.json()
        
        if 'erro' in data:
            print(f"[IBGE] ⚠️  CEP não encontrado")
            return None
        
        municipio = data.get('localidade', '')
        uf = data.get('uf', '')
        
        if not municipio or not uf:
            print(f"[IBGE] ⚠️  Município ou UF não encontrado")
            return None
        
        print(f"[IBGE] Município encontrado: {municipio}/{uf}")
        
        # 2. Busca código IBGE do município
        url_ibge = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
        response = requests.get(url_ibge, timeout=5)
        
        if response.status_code != 200:
            print(f"[IBGE] ⚠️  Erro ao buscar municípios: {response.status_code}")
            return None
        
        municipios = response.json()
        
        # Encontra o município exato
        municipio_encontrado = None
        for mun in municipios:
            if mun['nome'].upper() == municipio.upper():
                municipio_encontrado = mun
                break
        
        if not municipio_encontrado:
            print(f"[IBGE] ⚠️  Município {municipio} não encontrado na lista IBGE")
            # Fallback: usa capital do estado
            return buscar_coordenadas_capital(uf)
        
        codigo_ibge = municipio_encontrado['id']
        
        # 3. Busca coordenadas via API IBGE
        url_coord = f"https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo_ibge}"
        response = requests.get(url_coord, timeout=5)
        
        if response.status_code != 200:
            print(f"[IBGE] ⚠️  Erro ao buscar coordenadas: {response.status_code}")
            return None
        
        data = response.json()
        
        # Coordenadas vêm em formato diferente dependendo da API
        try:
            # Tenta formato completo primeiro
            if 'geometria' in data and 'coordenadas' in data['geometria']:
                lon = data['geometria']['coordenadas'][0]
                lat = data['geometria']['coordenadas'][1]
            # Senão tenta formato simplificado
            elif 'longitude' in data and 'latitude' in data:
                lon = float(data['longitude'])
                lat = float(data['latitude'])
            else:
                print(f"[IBGE] ⚠️  Formato de coordenadas não reconhecido")
                return None
            
            print(f"[IBGE] ✓ Coordenadas: {lat}, {lon}")
            
            return {
                'municipio': municipio,
                'uf': uf,
                'codigo_ibge': codigo_ibge,
                'lat': lat,
                'lon': lon
            }
            
        except (KeyError, ValueError, IndexError) as e:
            print(f"[IBGE] ⚠️  Erro ao extrair coordenadas: {e}")
            return None
            
    except requests.Timeout:
        print(f"[IBGE] ⚠️  Timeout ao buscar coordenadas")
        return None
    except Exception as e:
        print(f"[IBGE] ⚠️  Erro inesperado: {e}")
        return None


def buscar_coordenadas_capital(uf):
    """
    Fallback: retorna coordenadas da capital do estado
    """
    capitais = {
        'AC': {'nome': 'Rio Branco', 'lat': -9.9754, 'lon': -67.8249},
        'AL': {'nome': 'Maceió', 'lat': -9.6658, 'lon': -35.7353},
        'AP': {'nome': 'Macapá', 'lat': 0.0389, 'lon': -51.0664},
        'AM': {'nome': 'Manaus', 'lat': -3.1190, 'lon': -60.0217},
        'BA': {'nome': 'Salvador', 'lat': -12.9714, 'lon': -38.5014},
        'CE': {'nome': 'Fortaleza', 'lat': -3.7172, 'lon': -38.5433},
        'DF': {'nome': 'Brasília', 'lat': -15.7939, 'lon': -47.8828},
        'ES': {'nome': 'Vitória', 'lat': -20.3155, 'lon': -40.3128},
        'GO': {'nome': 'Goiânia', 'lat': -16.6869, 'lon': -49.2648},
        'MA': {'nome': 'São Luís', 'lat': -2.5387, 'lon': -44.2825},
        'MT': {'nome': 'Cuiabá', 'lat': -15.6014, 'lon': -56.0979},
        'MS': {'nome': 'Campo Grande', 'lat': -20.4697, 'lon': -54.6201},
        'MG': {'nome': 'Belo Horizonte', 'lat': -19.9167, 'lon': -43.9345},
        'PA': {'nome': 'Belém', 'lat': -1.4558, 'lon': -48.5039},
        'PB': {'nome': 'João Pessoa', 'lat': -7.1195, 'lon': -34.8450},
        'PR': {'nome': 'Curitiba', 'lat': -25.4284, 'lon': -49.2733},
        'PE': {'nome': 'Recife', 'lat': -8.0476, 'lon': -34.8770},
        'PI': {'nome': 'Teresina', 'lat': -5.0892, 'lon': -42.8016},
        'RJ': {'nome': 'Rio de Janeiro', 'lat': -22.9068, 'lon': -43.1729},
        'RN': {'nome': 'Natal', 'lat': -5.7945, 'lon': -35.2110},
        'RS': {'nome': 'Porto Alegre', 'lat': -30.0346, 'lon': -51.2177},
        'RO': {'nome': 'Porto Velho', 'lat': -8.7612, 'lon': -63.9004},
        'RR': {'nome': 'Boa Vista', 'lat': 2.8235, 'lon': -60.6758},
        'SC': {'nome': 'Florianópolis', 'lat': -27.5954, 'lon': -48.5480},
        'SP': {'nome': 'São Paulo', 'lat': -23.5505, 'lon': -46.6333},
        'SE': {'nome': 'Aracaju', 'lat': -10.9472, 'lon': -37.0731},
        'TO': {'nome': 'Palmas', 'lat': -10.2491, 'lon': -48.3243}
    }
    
    if uf in capitais:
        capital = capitais[uf]
        print(f"[IBGE] Usando capital como fallback: {capital['nome']}/{uf}")
        return {
            'municipio': capital['nome'],
            'uf': uf,
            'lat': capital['lat'],
            'lon': capital['lon']
        }
    
    return None


def verificar_estoque_tray(codigo_produto, cd_codigo):
    """
    Verifica estoque do produto no CD específico via API Tray
    """
    if not TRAY_API_URL or not TRAY_API_TOKEN:
        print(f"[TRAY] API não configurada, assumindo estoque disponível")
        return True
    
    try:
        headers = {
            'Authorization': f'Bearer {TRAY_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        # Busca produto
        url = f"{TRAY_API_URL}/products"
        params = {'reference': codigo_produto}
        
        response = requests.get(url, headers=headers, params=params, timeout=5)
        
        if response.status_code != 200:
            print(f"[TRAY] ⚠️  Erro ao buscar produto: {response.status_code}")
            return True  # Assume disponível em caso de erro
        
        data = response.json()
        
        if not data or 'products' not in data or not data['products']:
            print(f"[TRAY] ⚠️  Produto {codigo_produto} não encontrado")
            return True
        
        produto = data['products'][0]
        
        # Verifica campo de estoque do CD específico
        campo_estoque = f"stock_{cd_codigo}"
        
        if campo_estoque in produto:
            estoque = int(produto[campo_estoque])
            print(f"[TRAY] Estoque de {codigo_produto} no {cd_codigo}: {estoque}")
            return estoque > 0
        
        # Fallback: usa campo stock padrão
        if 'stock' in produto:
            estoque = int(produto['stock'])
            print(f"[TRAY] Estoque padrão de {codigo_produto}: {estoque}")
            return estoque > 0
        
        print(f"[TRAY] ⚠️  Campo de estoque não encontrado")
        return True
        
    except Exception as e:
        print(f"[TRAY] ⚠️  Erro ao verificar estoque: {e}")
        return True  # Assume disponível em caso de erro


def calcular_distancias_cds(lat_destino, lon_destino):
    """
    Calcula distância de todos CDs para o destino
    Retorna lista ordenada por distância
    """
    distancias = []
    
    for cd_id, cd_info in CENTROS_DISTRIBUICAO.items():
        distancia = haversine(
            cd_info['lat'], cd_info['lon'],
            lat_destino, lon_destino
        )
        
        distancias.append({
            'cd_id': cd_id,
            'cd_info': cd_info,
            'distancia': distancia
        })
    
    # Ordena por distância (mais próximo primeiro)
    distancias.sort(key=lambda x: x['distancia'])
    
    return distancias


def selecionar_melhor_cd(lat_destino, lon_destino, produtos):
    """
    Seleciona o melhor CD baseado em:
    1. Distância (mais próximo)
    2. Disponibilidade de estoque
    """
    distancias = calcular_distancias_cds(lat_destino, lon_destino)
    
    print(f"\n[CALC] Distâncias calculadas:")
    for d in distancias:
        print(f"  - {d['cd_info']['nome']}: {d['distancia']:.1f} km")
    
    # Verifica estoque em cada CD (do mais próximo ao mais distante)
    for d in distancias:
        cd_id = d['cd_id']
        cd_info = d['cd_info']
        distancia = d['distancia']
        
        # Verifica se todos produtos têm estoque neste CD
        todos_disponiveis = True
        for produto in produtos:
            codigo = produto.get('codigo', '')
            if codigo and not verificar_estoque_tray(codigo, cd_info['codigo_cd_tray']):
                todos_disponiveis = False
                print(f"[CD] {cd_info['nome']}: Produto {codigo} sem estoque")
                break
        
        if todos_disponiveis:
            print(f"[CD] ✓ Escolhido: {cd_info['nome']} ({distancia:.1f} km)")
            return {
                'cd_id': cd_id,
                'cd_info': cd_info,
                'distancia': distancia,
                'tem_estoque': True
            }
    
    # Se nenhum CD tem estoque completo, retorna o mais próximo
    print(f"[CD] ⚠️  Nenhum CD com estoque completo, usando mais próximo")
    return {
        'cd_id': distancias[0]['cd_id'],
        'cd_info': distancias[0]['cd_info'],
        'distancia': distancias[0]['distancia'],
        'tem_estoque': False
    }


def calcular_prazo_entrega(distancia_km):
    """
    Calcula prazo de entrega baseado na distância
    """
    if distancia_km <= 100:
        return 3
    elif distancia_km <= 300:
        return 5
    elif distancia_km <= 600:
        return 7
    elif distancia_km <= 1000:
        return 10
    else:
        return 15


def calcular_valor_frete(distancia_km, peso_total, volume_total, valor_km=None):
    """
    Calcula valor do frete baseado em distância, peso e volume
    """
    if valor_km is None:
        valor_km = DEFAULT_VALOR_KM
    
    # Valor base por distância
    valor_base = distancia_km * valor_km
    
    # Fator de peso (cada 10kg adiciona 5%)
    fator_peso = 1 + (peso_total / 10) * 0.05
    
    # Fator de volume (cada m³ adiciona 10%)
    fator_volume = 1 + (volume_total * 0.1)
    
    # Cálculo final
    valor_final = valor_base * fator_peso * fator_volume
    
    # Valor mínimo de R$ 50,00
    valor_final = max(valor_final, 50.00)
    
    return round(valor_final, 2)


def parse_produtos_tray(produtos_str):
    """
    Parse do formato de produtos da Tray:
    comp;larg;alt;cubagem;quantidade;peso;codigo;valor
    """
    produtos = []
    
    try:
        # Produtos separados por /
        itens = produtos_str.split('/')
        
        for item in itens:
            # Campos separados por ;
            campos = item.split(';')
            
            if len(campos) >= 8:
                produtos.append({
                    'comprimento': float(campos[0]),
                    'largura': float(campos[1]),
                    'altura': float(campos[2]),
                    'cubagem': float(campos[3]),
                    'quantidade': int(campos[4]),
                    'peso': float(campos[5]),
                    'codigo': campos[6],
                    'valor': float(campos[7])
                })
        
        return produtos
        
    except Exception as e:
        print(f"[PARSE] Erro ao processar produtos: {e}")
        return []


# ============================================================================
# ENDPOINTS DA API
# ============================================================================

@app.route('/frete', methods=['GET', 'POST'])
def calcular_frete():
    """
    Endpoint principal - calcula frete compatível com Tray
    """
    try:
        print("\n" + "="*70)
        print(f"📦 NOVA REQUISIÇÃO DE FRETE - {request.method}")
        print("="*70)
        
        # Pega parâmetros (GET ou POST)
        if request.method == 'POST':
            params = request.form.to_dict()
        else:
            params = request.args.to_dict()
        
        print(f"Parâmetros: {params}")
        
        # CEP pode vir como cep_destino ou cep
        cep = params.get('cep_destino') or params.get('cep', '')
        produtos_str = params.get('prods', '')
        
        if not cep:
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<error>CEP não informado</error>',
                mimetype='text/xml'
            ), 400
        
        if not produtos_str:
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<error>Produtos não informados</error>',
                mimetype='text/xml'
            ), 400
        
        # Parse produtos
        produtos = parse_produtos_tray(produtos_str)
        
        if not produtos:
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<error>Formato de produtos inválido</error>',
                mimetype='text/xml'
            ), 400
        
        print(f"Produtos: {[p['codigo'] for p in produtos]}")
        
        # Calcula totais
        peso_total = sum(p['peso'] * p['quantidade'] for p in produtos)
        volume_total = sum(p['cubagem'] * p['quantidade'] for p in produtos)
        qtd_total = sum(p['quantidade'] for p in produtos)
        
        print(f"Quantidade total: {qtd_total}, Peso total: {peso_total:.2f} kg")
        
        # Busca coordenadas do destino via IBGE
        coord_destino = buscar_coordenadas_ibge(cep)
        
        if not coord_destino:
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<error>CEP inválido ou não encontrado</error>',
                mimetype='text/xml'
            ), 400
        
        print(f"[CALC] Calculando distâncias para {coord_destino['municipio']}/{coord_destino['uf']}")
        
        # Seleciona melhor CD
        resultado_cd = selecionar_melhor_cd(
            coord_destino['lat'],
            coord_destino['lon'],
            produtos
        )
        
        cd_info = resultado_cd['cd_info']
        distancia = resultado_cd['distancia']
        
        # Calcula frete e prazo
        valor_frete = calcular_valor_frete(distancia, peso_total, volume_total)
        prazo = calcular_prazo_entrega(distancia)
        
        print(f"\n{'='*70}")
        print(f"🏢 CD Selecionado: {cd_info['nome']}")
        print(f"📍 Origem: {cd_info['cidade']}/{cd_info['uf']}")
        print(f"📏 Distância: {distancia:.1f} km")
        print(f"📦 Estoque: {'Disponível' if resultado_cd['tem_estoque'] else 'Verificar'}")
        print(f"💰 Valor: R$ {valor_frete:.2f}")
        print(f"⏱️  Prazo: {prazo} dias")
        print("="*70 + "\n")
        
        # Retorna XML compatível com Tray
        xml_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<shipping>
    <cep>{cep}</cep>
    <price>{valor_frete:.2f}</price>
    <delivery_time>{prazo}</delivery_time>
    <message>Frete calculado via {cd_info['nome']}</message>
    <carrier>{cd_info['nome']}</carrier>
    <distance>{distancia:.1f}</distance>
    <origin>{cd_info['cidade']}/{cd_info['uf']}</origin>
</shipping>'''
        
        return Response(xml_response, mimetype='text/xml')
        
    except Exception as e:
        print(f"[ERRO] {e}")
        import traceback
        traceback.print_exc()
        
        return Response(
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<error>Erro ao calcular frete: {str(e)}</error>',
            mimetype='text/xml'
        ), 500


@app.route('/teste', methods=['GET'])
def teste_frete():
    """
    Endpoint de teste - retorna HTML com resultado
    """
    try:
        cep = request.args.get('cep', '')
        produto = request.args.get('produto', 'PROD001')
        
        if not cep:
            return jsonify({"erro": "Parâmetro 'cep' obrigatório"}), 400
        
        # Busca coordenadas
        coord = buscar_coordenadas_ibge(cep)
        
        if not coord:
            return jsonify({"erro": "CEP inválido"}), 400
        
        # Calcula distâncias
        distancias = calcular_distancias_cds(coord['lat'], coord['lon'])
        
        # Monta resposta HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Teste de Frete - Multi-CD</title>
            <style>
                body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
                h1 {{ color: #333; }}
                .info {{ background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .cd {{ background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #2196F3; }}
                .cd.melhor {{ border-left-color: #4CAF50; background: #e8f5e9; }}
                .stats {{ display: flex; justify-content: space-between; margin: 20px 0; }}
                .stat {{ text-align: center; }}
                .stat-value {{ font-size: 24px; font-weight: bold; color: #2196F3; }}
                .stat-label {{ color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚚 Teste de Frete Multi-CD</h1>
                
                <div class="info">
                    <h3>📍 Destino</h3>
                    <p><strong>CEP:</strong> {cep}</p>
                    <p><strong>Município:</strong> {coord['municipio']}/{coord['uf']}</p>
                    <p><strong>Coordenadas:</strong> {coord['lat']:.4f}, {coord['lon']:.4f}</p>
                    <p><strong>Produto:</strong> {produto}</p>
                </div>
                
                <h3>📊 Distâncias dos CDs</h3>
        """
        
        melhor_cd = distancias[0]
        
        for i, d in enumerate(distancias):
            cd = d['cd_info']
            dist = d['distancia']
            prazo = calcular_prazo_entrega(dist)
            valor = calcular_valor_frete(dist, 10.0, 0.5)  # Exemplo: 10kg, 0.5m³
            
            classe = "cd melhor" if i == 0 else "cd"
            
            html += f"""
                <div class="{classe}">
                    <h4>{'🏆 ' if i == 0 else ''}{cd['nome']}</h4>
                    <p><strong>Origem:</strong> {cd['cidade']}/{cd['uf']}</p>
                    <div class="stats">
                        <div class="stat">
                            <div class="stat-value">{dist:.0f} km</div>
                            <div class="stat-label">Distância</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">R$ {valor:.2f}</div>
                            <div class="stat-label">Valor</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">{prazo} dias</div>
                            <div class="stat-label">Prazo</div>
                        </div>
                    </div>
                </div>
            """
        
        html += """
            </div>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route('/cds', methods=['GET'])
def listar_cds():
    """
    Lista todos CDs disponíveis
    """
    cds = []
    for cd_id, cd_info in CENTROS_DISTRIBUICAO.items():
        cds.append({
            'id': cd_id,
            'nome': cd_info['nome'],
            'cidade': cd_info['cidade'],
            'uf': cd_info['uf'],
            'cep': f"{cd_info['cep'][:5]}-{cd_info['cep'][5:]}",
            'lat': cd_info['lat'],
            'lon': cd_info['lon']
        })
    
    return jsonify({
        'total': len(cds),
        'centros': cds
    })


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check da API
    """
    # Testa conexão com APIs externas
    ibge_ok = True
    try:
        r = requests.get('https://servicodados.ibge.gov.br/api/v1/localidades/estados', timeout=3)
        ibge_ok = r.status_code == 200
    except:
        ibge_ok = False
    
    tray_ok = bool(TRAY_API_URL and TRAY_API_TOKEN)
    
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'cds': len(CENTROS_DISTRIBUICAO),
        'ibge_api': 'disponível' if ibge_ok else 'indisponível',
        'tray_api': 'configurado' if tray_ok else 'não configurado',
        'versao': '2.0.0'
    })


@app.route('/', methods=['GET'])
def index():
    """
    Página inicial da API
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>API Multi-CD - Sistema de Frete Inteligente</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #333;
            }}
            .container {{
                max-width: 900px;
                margin: 50px auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 2.5em;
            }}
            .header p {{
                margin: 10px 0 0 0;
                opacity: 0.9;
            }}
            .content {{
                padding: 40px;
            }}
            .section {{
                margin: 30px 0;
            }}
            .section h2 {{
                color: #667eea;
                border-bottom: 3px solid #667eea;
                padding-bottom: 10px;
            }}
            .cds-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }}
            .cd-card {{
                background: #f8f9fa;
                padding: 20px;
                border-radius: 10px;
                border-left: 4px solid #667eea;
            }}
            .cd-card h3 {{
                margin-top: 0;
                color: #333;
            }}
            .cd-card p {{
                margin: 5px 0;
                color: #666;
            }}
            .endpoint {{
                background: #f1f3f4;
                padding: 15px;
                border-radius: 8px;
                margin: 15px 0;
                font-family: 'Courier New', monospace;
            }}
            .endpoint code {{
                color: #d63384;
            }}
            .stats {{
                display: flex;
                justify-content: space-around;
                margin: 30px 0;
            }}
            .stat {{
                text-align: center;
            }}
            .stat-value {{
                font-size: 3em;
                font-weight: bold;
                color: #667eea;
            }}
            .stat-label {{
                color: #666;
                margin-top: 10px;
            }}
            .btn {{
                display: inline-block;
                padding: 12px 30px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 25px;
                margin: 10px;
                transition: all 0.3s;
            }}
            .btn:hover {{
                background: #764ba2;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            }}
            .footer {{
                background: #f8f9fa;
                padding: 20px;
                text-align: center;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚚 API Multi-CD</h1>
                <p>Sistema Inteligente de Cálculo de Frete com 5 Centros de Distribuição</p>
            </div>
            
            <div class="content">
                <div class="stats">
                    <div class="stat">
                        <div class="stat-value">{len(CENTROS_DISTRIBUICAO)}</div>
                        <div class="stat-label">Centros de Distribuição</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">100%</div>
                        <div class="stat-label">Cobertura Brasil</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">API</div>
                        <div class="stat-label">IBGE Oficial</div>
                    </div>
                </div>
                
                <div class="section">
                    <h2>📍 Nossos Centros de Distribuição</h2>
                    <div class="cds-grid">
                        {''.join([f'''
                        <div class="cd-card">
                            <h3>{cd['nome']}</h3>
                            <p>📍 {cd['cidade']}/{cd['uf']}</p>
                            <p>📮 CEP: {cd['cep'][:5]}-{cd['cep'][5:]}</p>
                        </div>
                        ''' for cd in CENTROS_DISTRIBUICAO.values()])}
                    </div>
                </div>
                
                <div class="section">
                    <h2>🔌 Endpoints Disponíveis</h2>
                    
                    <div class="endpoint">
                        <strong>POST/GET /frete</strong><br>
                        Calcula frete (compatível com Tray)<br>
                        <code>?cep_destino=90000000&prods=...</code>
                    </div>
                    
                    <div class="endpoint">
                        <strong>GET /teste</strong><br>
                        Testa cálculo com interface visual<br>
                        <code>?cep=90000000&produto=PROD001</code>
                    </div>
                    
                    <div class="endpoint">
                        <strong>GET /cds</strong><br>
                        Lista todos CDs disponíveis<br>
                        <code>Retorna JSON com informações dos CDs</code>
                    </div>
                    
                    <div class="endpoint">
                        <strong>GET /health</strong><br>
                        Status da API e serviços<br>
                        <code>Health check e monitoramento</code>
                    </div>
                </div>
                
                <div class="section" style="text-align: center;">
                    <h2>🧪 Testar Agora</h2>
                    <a href="/teste?cep=90000000&produto=TESTE001" class="btn">Testar Porto Alegre/RS</a>
                    <a href="/teste?cep=88000000&produto=TESTE001" class="btn">Testar Florianópolis/SC</a>
                    <a href="/teste?cep=30000000&produto=TESTE001" class="btn">Testar Belo Horizonte/MG</a>
                    <a href="/cds" class="btn">Ver Todos CDs</a>
                    <a href="/health" class="btn">Status da API</a>
                </div>
                
                <div class="section">
                    <h2>✨ Funcionalidades</h2>
                    <ul>
                        <li>✅ Coordenadas reais via API IBGE oficial</li>
                        <li>✅ Cálculo de distância por fórmula Haversine + fator rodoviário</li>
                        <li>✅ Seleção automática do CD mais próximo</li>
                        <li>✅ Verificação de estoque via API Tray</li>
                        <li>✅ Cálculo inteligente de prazo e valor</li>
                        <li>✅ Compatível 100% com Tray Commerce</li>
                        <li>✅ Resposta em XML padrão Tray</li>
                    </ul>
                </div>
            </div>
            
            <div class="footer">
                <p>API Multi-CD v2.0.0 | Sistema de Frete Inteligente</p>
                <p>Desenvolvido para integração com Tray Commerce</p>
            </div>
        </div>
    </body>
    </html>
    """


# ============================================================================
# INICIALIZAÇÃO DO SERVIDOR
# ============================================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    
    print("\n" + "="*70)
    print("🚀 INICIANDO API MULTI-CD")
    print("="*70)
    print(f"🌐 Porta: {port}")
    print(f"📦 CDs configurados: {len(CENTROS_DISTRIBUICAO)}")
    print(f"🔑 Token configurado: {'Sim' if TOKEN_SECRETO != 'seu_token_secreto' else 'Não (usando padrão)'}")
    print(f"💰 Valor/km: R$ {DEFAULT_VALOR_KM:.2f}")
    print(f"🏪 Tray API: {'Configurada' if TRAY_API_URL else 'Não configurada'}")
    print("\n📍 Centros de Distribuição:")
    for cd_id, cd in CENTROS_DISTRIBUICAO.items():
        print(f"   {cd_id}: {cd['nome']} ({cd['cidade']}/{cd['uf']})")
    print("\n🔗 Endpoints disponíveis:")
    print(f"   http://localhost:{port}/")
    print(f"   http://localhost:{port}/frete")
    print(f"   http://localhost:{port}/teste")
    print(f"   http://localhost:{port}/cds")
    print(f"   http://localhost:{port}/health")
    print("="*70 + "\n")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.getenv('DEBUG', 'False').lower() == 'true'
    )
