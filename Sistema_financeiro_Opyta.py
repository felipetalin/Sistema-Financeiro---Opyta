import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import datetime
from babel.numbers import format_currency
import uuid
from PIL import Image

# Configuração da página
st.set_page_config(layout="wide")

# Configurar credenciais
SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/drive']

# Função de conexão única com gspread (cacheada)
@st.cache_resource
def conectar_sheets():
    return gspread.service_account(filename='G:\\Meu Drive\\Opyta Financeiro\\Fluxo de Caixa\\Sistema Finaceiro - Opyta\\acesso-sheets.json')

# Carregar dados
@st.cache_data
def carregar_dados(spreadsheet_id, _gc):
    sh = _gc.open_by_key(spreadsheet_id)
    projetos = pd.DataFrame(sh.worksheet("Projetos").get_all_records())
    receitas = pd.DataFrame(sh.worksheet("Receitas_Reais").get_all_records())
    despesas = pd.DataFrame(sh.worksheet("Despesas_Reais").get_all_records())
    custos = pd.DataFrame(sh.worksheet("Custos_Fixos_Variaveis").get_all_records())
    parametros_impostos = pd.DataFrame(sh.worksheet("Parametros_Impostos").get_all_records())
    return projetos, receitas, despesas, custos, parametros_impostos

# Função para escrever dados sem duplicar (a otimizar)
def escrever_dados(spreadsheet_id, worksheet_name, data, gc):
    sh = gc.open_by_key(spreadsheet_id)
    worksheet = sh.worksheet(worksheet_name)
    existentes = pd.DataFrame(worksheet.get_all_records())
    
    if existentes.empty:
        # Se a planilha estiver vazia, adicionar os cabeçalhos e os dados
        worksheet.append_row(list(data.columns))
        for row in data.values.tolist():
            worksheet.append_row(row)
    else:
        # Se a planilha não estiver vazia
        for index, row in data.iterrows():
            id_calculo = row["ID"]
            # Verificar se o ID já existe na planilha
            if id_calculo in existentes["ID"].values:
                # Se o ID existir, encontrar a linha correspondente e atualizar os valores
                linha_para_atualizar = existentes[existentes["ID"] == id_calculo].index[0] + 2  # +2 porque a primeira linha é o cabeçalho e o índice começa em 0
                
                # Criar uma lista com os valores da linha a ser atualizada
                valores_para_atualizar = list(row.values)
                
                # Atualizar a linha na planilha
                worksheet.update(f"A{linha_para_atualizar}:{chr(64 + len(valores_para_atualizar))}{linha_para_atualizar}", [valores_para_atualizar])
            else:
                # Se o ID não existir, adicionar uma nova linha
                worksheet.append_row(list(row.values))

# Calcular os impostos
def calcular_impostos(receitas, parametros_impostos):
    impostos_calculados = []
    for index, receita in receitas.iterrows():
        projeto = receita["Projeto"]
        valor_receita = receita["Valor Recebido"]
        # Gerar um ID único para o cálculo de imposto
        id_calculo = str(uuid.uuid4())  # Usando UUID para garantir a unicidade
        impostos_projeto = {}
        impostos_projeto["ID"] = id_calculo
        impostos_projeto["Projeto"] = projeto
        impostos_projeto["Valor da Receita"] = valor_receita
        total_impostos = 0  # Inicializa o total de impostos para este projeto
        for index_imposto, parametro in parametros_impostos.iterrows():
            imposto = parametro["Imposto"]
            aliquota = float(parametro["Alíquota"])
            valor_imposto = valor_receita * aliquota
            impostos_projeto[imposto] = valor_imposto
            total_impostos += valor_imposto  # Adiciona o valor do imposto ao total
        impostos_projeto["Total de Impostos"] = total_impostos  # Adiciona o total de impostos ao dicionário
        impostos_calculados.append(impostos_projeto)
    return pd.DataFrame(impostos_calculados)

# ID da planilha
spreadsheet_id = "1Ut25HiLC17oq7X6ThTKqMPHnPUoBjXsIRaVVFJDa7r4"

# Conectar ao Google Sheets
gc = conectar_sheets()

# Carregar dados
projetos, receitas, despesas, custos, parametros_impostos = carregar_dados(spreadsheet_id, gc)

# Carregar a logo
logo = Image.open("G:\Meu Drive\Opyta Financeiro\Fluxo de Caixa\Sistema Finaceiro - Opyta\Logo Opyta Horizontal.png")

# Configurar o layout da página para "wide"
st.set_page_config(layout="wide")

# Título do aplicativo e logo
col_title, col_logo = st.columns([3, 1])
with col_title:
    st.title("Sistema Financeiro Simplificado - Opyta")
with col_logo:
    st.image(logo, width=150)

# Sidebar para filtros
with st.sidebar:
    st.header("Filtros")

    # Filtro por Cliente (Independente)
    cliente_selecionado = st.selectbox("Selecione o Cliente", ["Todos"] + projetos["Cliente"].unique().tolist())

    # Filtro por Projeto (Dependente do Cliente)
    projetos_cliente = projetos[projetos["Cliente"] == cliente_selecionado] if cliente_selecionado != "Todos" else projetos
    projeto_selecionado = st.selectbox("Selecione o Projeto", ["Todos"] + projetos_cliente["Código"].tolist())

    # Filtro por Período
    periodo_selecionado = st.selectbox("Selecione o Período",
        ["Este Mês", "Último Mês", "Este Ano", "Último Ano", "Personalizado"])
    data_inicio, data_fim = None, None
    if periodo_selecionado == "Personalizado":
        data_inicio = st.sidebar.date_input("Data de Início", datetime.date(2023, 1, 1))
        data_fim = st.sidebar.date_input("Data de Fim", datetime.date.today())

# --------------------
# APLICAR FILTROS
# --------------------
def filtrar_por_projeto(df, projeto):
    return df if projeto == "Todos" else df[df["Projeto"] == projeto]

def filtrar_por_cliente(df, cliente):
    if cliente == "Todos": return df
    projetos_cliente = projetos[projetos["Cliente"] == cliente]["Código"].tolist()
    return df[df["Projeto"].isin(projetos_cliente)]

def filtrar_por_periodo(df, periodo, data_inicio=None, data_fim=None, data_column="Data"):
    hoje = datetime.date.today()
    if periodo == "Este Mês":
        inicio = datetime.date(hoje.year, hoje.month, 1); fim = hoje
    elif periodo == "Último Mês":
        primeiro_dia_mes_atual = datetime.date(hoje.year, hoje.month, 1)
        fim = primeiro_dia_mes_atual - datetime.timedelta(days=1)
        inicio = datetime.date(fim.year, fim.month, 1)
    elif periodo == "Este Ano":
        inicio = datetime.date(hoje.year, 1, 1); fim = hoje
    elif periodo == "Último Ano":
        inicio = datetime.date(hoje.year - 1, 1, 1); fim = datetime.date(hoje.year - 1, 12, 31)
    elif periodo == "Personalizado":
        inicio, fim = data_inicio, data_fim
    else:
        return df
    return df[((df[data_column] >= str(inicio)) & (df[data_column] <= str(fim)))]

# Aplicar filtros
receitas_f = filtrar_por_projeto(receitas, projeto_selecionado)
receitas_f = filtrar_por_cliente(receitas_f, cliente_selecionado)
receitas_f = filtrar_por_periodo(receitas_f, periodo_selecionado, data_inicio, data_fim, "Data Recebimento")

despesas_f = filtrar_por_projeto(despesas, projeto_selecionado)
despesas_f = filtrar_por_cliente(despesas_f, cliente_selecionado)
despesas_f = filtrar_por_periodo(despesas_f, periodo_selecionado, data_inicio, data_fim, "Data Pagamento")

# Calcular os impostos
impostos_calculados = calcular_impostos(receitas_f, parametros_impostos)

# Escrever os impostos calculados na planilha
escrever_dados(spreadsheet_id, "Calculo_Impostos", impostos_calculados, gc)

# --------------------
# CÁLCULOS PRINCIPAIS
# --------------------
def calcular_totais(receitas, despesas, custos):
    total_receitas = receitas["Valor Recebido"].sum()
    total_despesas = despesas["Valor Pago"].sum()
    total_custos = custos["Valor"].sum()
    lucro_total = total_receitas - total_despesas - total_custos
    fluxo_caixa = total_receitas - total_despesas
    return total_receitas, total_despesas, total_custos, lucro_total, fluxo_caixa

total_receitas, total_despesas, total_custos, lucro_total, fluxo_caixa = calcular_totais(receitas_f, despesas_f, custos)

# --------------------
# LAYOUT PRINCIPAL
# --------------------


# Resumo Executivo
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Receita Total", format_currency(total_receitas, "BRL", locale="pt_BR"))
col2.metric("Despesa Total", format_currency(total_despesas, "BRL", locale="pt_BR"))
col3.metric("Custos Fixos/Var.", format_currency(total_custos, "BRL", locale="pt_BR"))
col4.metric("Lucro Total", format_currency(lucro_total, "BRL", locale="pt_BR"))
col5.metric("Fluxo de Caixa", format_currency(fluxo_caixa, "BRL", locale="pt_BR"))

# Gráfico de Receitas vs Despesas no tempo
st.header("📈 Evolução de Receitas e Despesas")
if not receitas_f.empty and not despesas_f.empty:
    df_tempo = pd.concat([
        receitas_f.rename(columns={"Data Recebimento": "Data", "Valor Recebido": "Valor"}).assign(Tipo="Receita")[[ "Data", "Valor", "Tipo"]],
        despesas_f.rename(columns={"Data Pagamento": "Data", "Valor Pago": "Valor"}).assign(Tipo="Despesa")[["Data", "Valor", "Tipo"]]
    ])
    df_tempo["Data"] = pd.to_datetime(df_tempo["Data"])
    fig = px.area(df_tempo, x="Data", y="Valor", color="Tipo", 
                  title="Evolução de Receitas e Despesas ao Longo do Tempo",
                  labels={"Valor": "Valor (R$)"},  # Customizar os rótulos
                  color_discrete_map={"Receita": "#87A96B", "Despesa": "#FF4B4B"}) # Define as cores
    
    # Mostrar o gráfico
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sem dados suficientes para o gráfico de evolução.")

# Definir uma função para aplicar a formatação condicional
def highlight_max(s):
    '''
    Highlight the maximum in a Series yellow.
    '''
    is_max = s == s.max()
    return ['background-color: yellow' if v else '' for v in is_max]

# Tabelas detalhadas com formatação condicional
st.header("📊 Receitas Detalhadas")
styled_receitas = receitas_f.style.format({"Valor Recebido": lambda x: format_currency(x, "BRL", locale="pt_BR")})
styled_receitas = styled_receitas.apply(highlight_max, subset=['Valor Recebido'])
st.dataframe(styled_receitas)

st.header("📊 Despesas Detalhadas")

def color_negative_red(value):
    """
    Colors elements in a column red if negative.
    """
    if isinstance(value, (int, float)):
        if value < 0:
            return 'color: red'
    return ''

styled_despesas = despesas_f.style.format({"Valor Pago": lambda x: format_currency(x, "BRL", locale="pt_BR")}).applymap(color_negative_red, subset=['Valor Pago'])
st.dataframe(styled_despesas)

# Alertas Visuais
st.header("🚨 Alertas")
col_alert1, col_alert2 = st.columns(2)
for index, projeto in projetos.iterrows():
    codigo_projeto = projeto["Código"]
    
    # Verificar se a coluna 'Meta de Receita' e 'Orçamento' existem antes de acessá-las
    if 'Meta de Receita' in projeto and 'Orçamento' in projeto:
        meta_receita = projeto["Meta de Receita"]
        orcamento = projeto["Orçamento"]
    else:
        st.warning(f"As colunas 'Meta de Receita' ou 'Orçamento' não foram encontradas para o projeto {codigo_projeto}.")
        continue  # Ir para o próximo projeto

    # Filtrar receitas e despesas para o projeto atual
    receitas_projeto = receitas_f[receitas_f["Projeto"] == codigo_projeto]
    despesas_projeto = despesas_f[despesas_f["Projeto"] == codigo_projeto]
    total_receita_projeto = receitas_projeto["Valor Recebido"].sum()
    total_despesa_projeto = despesas_projeto["Valor Pago"].sum()
    
    # Calcular o percentual gasto
    try:
        percentual_gasto = (total_despesa_projeto / float(orcamento)) * 100
    except (ZeroDivisionError, ValueError):
        percentual_gasto = 0  # Tratar divisão por zero ou valor inválido no orçamento
    
    # Definir a cor do alerta
    if percentual_gasto > 100:
        cor_alerta = "#FF4B4B"  # Vermelho (ex: gasto acima do orçamento)
    elif percentual_gasto > 80:
        cor_alerta = "#FFDA61"  # Amarelo (ex: perto de estourar o orçamento)
    else:
        cor_alerta = "#87A96B"  # Verde (ex: dentro do orçamento)
        
    # Criar o mini box com o percentual gasto e a cor de alerta
    with col_alert1:
        st.markdown(f"""
            <div style="background-color:{cor_alerta}; padding:10px; border-radius:5px; text-align:center; color: black">
                <b>{codigo_projeto}</b><br>
                Gasto: {percentual_gasto:.2f}%
            </div>
            """, unsafe_allow_html=True)

    # Verificar se a receita está abaixo da meta
    try:
        if total_receita_projeto < float(meta_receita):
            st.warning(f"O projeto {codigo_projeto} está com receita abaixo da meta (R$ {total_receita_projeto:,.2f} / R$ {float(meta_receita):,.2f})")
    except ValueError:
        st.warning(f"Valor inválido na coluna 'Meta de Receita' para o projeto {codigo_projeto}. Verifique se o valor é numérico.")

st.markdown("---")

# Gráfico de Receitas vs Despesas no tempo
st.header("📈 Evolução de Receitas e Despesas")
if not receitas_f.empty and not despesas_f.empty:
    df_tempo = pd.concat([
        receitas_f.rename(columns={"Data Recebimento": "Data", "Valor Recebido": "Valor"}).assign(Tipo="Receita")[[ "Data", "Valor", "Tipo"]],
        despesas_f.rename(columns={"Data Pagamento": "Data", "Valor Pago": "Valor"}).assign(Tipo="Despesa")[["Data", "Valor", "Tipo"]]
    ])
    df_tempo["Data"] = pd.to_datetime(df_tempo["Data"])
    fig = px.area(df_tempo, x="Data", y="Valor", color="Tipo", 
                  title="Evolução de Receitas e Despesas ao Longo do Tempo",
                  labels={"Valor": "Valor (R$)"},  # Customizar os rótulos
                  color_discrete_map={"Receita": "#87A96B", "Despesa": "#FF4B4B"}) # Define as cores
    
    # Mostrar o gráfico
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sem dados suficientes para o gráfico de evolução.")

st.markdown("---")

# Definir uma função para aplicar a formatação condicional
def highlight_max(s):
    '''
    Highlight the maximum in a Series yellow.
    '''
    is_max = s == s.max()
    return ['background-color: yellow' if v else '' for v in is_max]

# Tabelas detalhadas com formatação condicional
st.header("📊 Receitas Detalhadas")
styled_receitas = receitas_f.style.format({"Valor Recebido": lambda x: format_currency(x, "BRL", locale="pt_BR")})
styled_receitas = styled_receitas.apply(highlight_max, subset=['Valor Recebido'])
st.dataframe(styled_receitas)

st.header("📊 Despesas Detalhadas")

def color_negative_red(value):
    """
    Colors elements in a column red if negative.
    """
    if isinstance(value, (int, float)):
        if value < 0:
            return 'color: red'
    return ''

styled_despesas = despesas_f.style.format({"Valor Pago": lambda x: format_currency(x, "BRL", locale="pt_BR")}).applymap(color_negative_red, subset=['Valor Pago'])
st.dataframe(styled_despesas)

st.markdown("---")

# Custos fixos/variáveis
st.header("💡 Custos por Categoria")
custos_cat = custos.groupby("Categoria")["Valor"].sum().reset_index()
st.plotly_chart(px.pie(custos_cat, values="Valor", names="Categoria", title="Distribuição dos Custos"), use_container_width=True)

# Exibir os impostos calculados
st.header("Impostos Calculados")
st.dataframe(impostos_calculados)