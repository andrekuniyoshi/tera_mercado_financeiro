# -*- coding: utf-8 -*-
"""Untitled21.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1rRdcV7pQeq4hU6ajCYLaKyIbT3TgKoiv
"""

import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st
import datetime as dt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from xgboost import XGBClassifier
import sklearn
import altair
import pickle

# -------------------------------------- Cabeçalho -------------------------------------------------------#

st.set_page_config(
    page_title="TERA - Projeto Mercado Financeiro",
    page_icon="📈",
)

st.title("🤑 TERA - Projeto Mercado Financeiro")
st.header("")

with st.expander("ℹ️ - About this app", expanded=True):
	st.write(
        """     
	-   Esse app é fruto do projeto final do curso de Data Science & Machile Learning da TERA
	-   Nosso app utiliza técnicas de Machine Learning para tentar prever se o valor das ações vai subir ou descer 
	-   Esse trabalho ainda está em desenvolvimento, então ressalta-se que não deve ser utilizado para subsidiar suas decisões de investimentos! Pelo menos, não por enquanto😁
	-   O código do app pode ser conferido em: 'https://github.com/andrekuniyoshi/tera_mercado_financeiro/tree/main/streamlit'
	-   Autores: Andre Kuniyoshi, Gustavo Henrique Farias, Guilherme Gomes e Lucas Oliveira
	    """
	)
	st.markdown("")

# -------------------------------------------------------------------------------------------------------------------------------#
model = pickle.load(open('/tera_mercado_financeiro/tree/main/streamlit/stock_pred.pkl','rb'))
# ---------------------------------------------Escolhendo o tempo futuro da previsão-----------------------------------------------------#
st.subheader('Previsão de Subida ou Descida')

col1, col2, col3, col4 = st.columns([2,2,1,1])
with col1:
	symbols = ['AAPL', 'AMZN']

	ticker = st.selectbox('Escolha uma ação',
				      symbols)

# -------------------------------------------------------------------------------------------------------------------------------#

stock = yf.Ticker(ticker)

df = yf.download(tickers = ticker,
                 start = '2021-01-01',
                 end = dt.datetime.today(),
                 interval = '1h',
                 ajusted = True)

#-----------------------------------FEATURE ENGINEERING--------------------------------------------
# CRIANDO FEATURE RSI
def criar_rsi(df):
    n = 20
    def rma(x, n, y0):
        a = (n-1) / n
        ak = a**np.arange(len(x)-1, -1, -1)
        return np.r_[np.full(n, np.nan), y0, np.cumsum(ak * x) / ak / n + y0 * a**np.arange(1, len(x)+1)]

    df['change'] = df['Adj Close'].diff()
    df['gain'] = df.change.mask(df.change < 0, 0.0)
    df['loss'] = -df.change.mask(df.change > 0, -0.0)
    df['avg_gain'] = rma(df.gain[n+1:].to_numpy(), n, np.nansum(df.gain.to_numpy()[:n+1])/n)
    df['avg_loss'] = rma(df.loss[n+1:].to_numpy(), n, np.nansum(df.loss.to_numpy()[:n+1])/n)
    df['rs'] = df.avg_gain / df.avg_loss
    df['rsi'] = 100 - (100 / (1 + df.rs))
    return df

# CRIANDO FEATURE BOLLINGER BAND
def criar_bollinger(df):
  # calculando a média móvel e limites superior e inferiror
  # limites com base em 2 desvios padrão
  mid = df['Adj Close'].rolling(20).mean()
  std = df['Adj Close'].rolling(20).std()
  up = mid + std
  low = mid - std

  # criando features para a média e os limites
  df['upper'] = up
  df['mid'] = mid
  df['low'] = low
  df['bbp'] = (df['Adj Close'] - df['low'])/(df['upper'] - df['low'])
  df.dropna(inplace=True)
  return df

# RESISTÊNCIA
def is_resistance(df,i):
  resistance = (df['High'][i] > df['High'][i-1]
                and df['High'][i] > df['High'][i+1]
                and df['High'][i+1] > df['High'][i+2]
                and df['High'][i-1] > df['High'][i-2])
  return resistance

# SUPORTE
def is_support(df,i):
  support = (df['Low'][i] < df['Low'][i-1]
             and df['Low'][i] < df['Low'][i+1]
             and df['Low'][i+1] < df['Low'][i+2]
             and df['Low'][i-1] < df['Low'][i-2])
  return support

def suporte_resistencia(df):
  # resistência verdadeiro -> 1 (vender)
  # suporte verdadeiro -> 0 (comprar)
  # outros (2)

  # criando feature com valores 2
  df['suport_resistencia'] = 2

  # definindo os valores 1 e 0
  for i in range(2, df.shape[0] - 2):
    if is_resistance(df,i):
      df['suport_resistencia'][i] = 1 # definindo 1 para resistência
    elif is_support(df,i):
      df['suport_resistencia'][i] = 0 # definindo 0 para suporte
  return df

# LTA E LTB
def lta_ltb(df):
  df2 = df.reset_index()
  df['corr'] = (df2['Adj Close'].rolling(20).corr(pd.Series(df2.index))).tolist()
  df.dropna(inplace=True)

  def condition(x):
      if x<=-0.5:
          return -1
      elif x>-0.5 and x<0.5:
          return 0
      else:
          return 1
  df['corr_class'] = df['corr'].apply(condition)

  return df

# MÉDIA MÓVEL
def media_movel(df, coluna, defasagem):
  df['media_movel'] = df[coluna].rolling(20).mean()
  return df

# FEATURES DE TEMPO
def feat_temporais(df):
  df['dia_semana'] = df.index.dayofweek
  df['horario'] = df.index.hour
  df['mes'] = df.index.month
  return df

# CRIANDO A TARGET
def target(df):

  # criando feature com 1h de defasagem (com hora anterior)
  df['def_1'] = df['Adj Close'].shift(1)
  # criando feature comparando valor atual com o defasado
  df['subt'] = df['Adj Close'] - df['def_1']


#  criando a target de subida ou descida do valor da ação
#  0 -> caiu (com relação ao anterior)
#  1 -> subiu (com relação ao anterior)
#  2 -> igual ao anterior
  

  df['target'] = df['subt'].apply(lambda x: int(0) if x<0 else int(1) if x>0 else int(2))

  return df

# FEATURES DEFASADAS 
def constroi_features_defasadas(df,lista_features,defasagem_maxima):
    # Constrói features defasadas com base na base original
    # Copia a base
    df_cop = df.copy()
    for feat in lista_features:       
        for i in range(1,defasagem_maxima+1):
            df_cop[str(feat)+'_def_'+str(i)] = df_cop[feat].shift(i)
    
    df_cop.dropna(inplace=True)
    return df_cop

# FEATURES FUTURAS
def constroi_features_futuras(df,feature,defasagem):
    # Constrói features defasadas com base na base original
    # Copia a base
    df_cop = df.copy()

    df_cop[str(feature)+'_fut'] = df_cop[feature].shift(-defasagem)
    return df_cop

###-----------------------------------FUNÇÃO DO MODELO-------------------------------------------- '''

def modelo(df, target_):
    X_test = df.drop(target_, axis=1)[-1:]

    X_train = df[:-1].dropna().drop(target_, axis=1)
    y_train = df[:-1].dropna()[target_]

    xgb = XGBClassifier(random_state=42,
			gamma = 0.1,
			max_depth = 8,
			n_estimators = 100,
			n_jobs=-1)
    xgb.fit(X_train, y_train)
    y_pred = xgb.predict(X_test)
    y_proba = xgb.predict_proba(X_test)
    y_proba = y_proba[:, 1]
    return y_pred, y_proba

df = criar_rsi(df)
df = criar_bollinger(df)
df = suporte_resistencia(df)
df = lta_ltb(df)
df = media_movel(df, 'Adj Close', 20)
df = feat_temporais(df)

##-----------------------------------slider de horas-------------------------------------------- '''

with col2:
	hora_previsao = st.slider("Tempo Futuro da Previsão (horas)",
				  value=1,
				  min_value=1,
				  max_value=8,
				  step=1)
with col3:
        st.write("Previsão")
with col4:
        st.write("Probabilidade")
##-----------------------------------slider de horas-------------------------------------------- '''
if st.button('Aperte para Previsão'):
##-----------------------------------VISUALIZAÇÃO DOS DADOS-------------------------------------------- '''
        df_viz = df[-600:]
        st.markdown("")

        # Bollinger Band
        st.subheader('Visualização das features exógenas')
        figBoll = go.Figure()
        figBoll.add_trace(
	        go.Scatter(
	            x = df_viz.index,
		    y = df_viz['upper'],
		    name = "Upper Band")
	        )
        figBoll.add_trace(
	        go.Scatter(
		    x = df_viz.index,
		    y = df_viz['mid'],
		    name = "Média Móvel")
	        )
        figBoll.add_trace(
	        go.Scatter(
	            x = df_viz.index,
		    y = df_viz['low'],
		    name = "Lower Band")
	        )
        figBoll.update_layout(legend=dict(
   	        orientation="h",
	        yanchor="bottom",
	        y=1,
	        xanchor="left",
	        x=0
	        ))
        figBoll.update_layout(title_text="Bollinger Band")
        figBoll.update_yaxes(tickprefix="$")
        st.plotly_chart(figBoll, use_container_width=False)

# Gráfico RSI
        fig = px.line(df_viz, x=df_viz.index, y="rsi")
        fig.update_layout(title_text="Variação de RSI")
        st.plotly_chart(fig, use_container_width=False)

##-----------------------------------CRIANDO DATASET-------------------------------------------- '''

        df = target(df)
        df.dropna(inplace=True)
        df = df[['target', 'Adj Close', 'Volume', 'rsi', 'bbp', 'suport_resistencia', 'corr_class', 'media_movel', 'dia_semana', 'horario', 'mes']]
        df = constroi_features_defasadas(df,['Adj Close'],20)
        df = constroi_features_futuras(df,'target',hora_previsao)
        df_model = df.drop('target', axis=1)

#st.dataframe(df)

###-----------------------------------MODELO--------------------------------------------
        df = df_model[-600:]
        X_test = df.drop('target_fut', axis=1)[-1:]
        #X_train = df[:-1].dropna().drop('target_fut', axis=1)
        #y_train = df[:-1].dropna()['target_fut']
	
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)
        y_proba = y_proba[:, 1]
        #y_pred, y_proba = modelo(df, 'target_fut')

###-------------------------------------------------------------------------------------
        with col3:
            #st.write("Previsão")
            if y_proba >= 0.7:
                st.info('Subir ⬆️')
            elif y_proba <= 0.3:
                st.error('Descer ⬇️')
            else:
                st.warning('Na mesma 😐')

        with col4:
            #st.write("Probabilidade")
			#st.subheader(y_proba[0])
            if y_proba >= 0.7:
                st.info(round(y_proba[0],4))
            elif y_proba <= 0.3:
                st.error(round(y_proba[0],4))
            else:
                st.warning(round(y_proba[0],4))
