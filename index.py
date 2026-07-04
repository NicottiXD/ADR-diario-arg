# Reporte ADRs Argentina - versión Vercel (serverless)

import logging
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
from flask import Flask, Response

# ================= CONFIG ================= #
WATCHLIST = ['GGAL', 'BMA', 'YPF', 'MELI', 'SUPV',
             'CEPU', 'PAM', 'TGS', 'CRESY', 'BIOX', 'EDN',
             'IRS', 'LOMA', 'TEO']

# Variación % a partir de la cual el color llega a su máxima intensidad.
MAX_PCT_COLOR = 5

# En Vercel la página se recarga sola cada REFRESH_SECONDS (client-side,
# no requiere loop en el server ni filesystem persistente).
REFRESH_SECONDS = 300
# ========================================== #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

app = Flask(__name__)


def fetch_watchlist(watchlist):
    """Descarga OHLC, cierre anterior y variación % de la watchlist."""
    tickers = yf.Tickers(" ".join(watchlist))
    rows = []

    for symbol in watchlist:
        try:
            tk = tickers.tickers.get(symbol)
            if tk:
                info = tk.info
                rows.append({
                    'Ticker': symbol,
                    'Apertura': info.get('regularMarketOpen', info.get('open', np.nan)),
                    'Máximo': info.get('regularMarketDayHigh', info.get('dayHigh', np.nan)),
                    'Mínimo': info.get('regularMarketDayLow', info.get('dayLow', np.nan)),
                    'Precio': info.get('regularMarketPrice', np.nan),
                    'Cierre anterior': info.get('regularMarketPreviousClose', info.get('previousClose', np.nan)),
                    'Variación %': info.get('regularMarketChangePercent', np.nan)
                })
            else:
                logging.warning(f"No se encontró info para {symbol}")
        except Exception as e:
            logging.error(f"Error al procesar {symbol}: {e}")
            rows.append({
                'Ticker': symbol, 'Apertura': np.nan, 'Máximo': np.nan,
                'Mínimo': np.nan, 'Precio': np.nan, 'Cierre anterior': np.nan, 'Variación %': np.nan
            })

    df = pd.DataFrame(rows)
    df['Variación %'] = df['Variación %'].round(2)
    df['Última actualización'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return df


def get_candle_color(pct, max_pct=MAX_PCT_COLOR):
    """
    Devuelve un color rojo o verde cuya intensidad es proporcional
    a la magnitud de la variación % diaria.
    """
    if pd.isna(pct):
        return 'rgb(180,180,180)'

    intensity = min(abs(pct) / max_pct, 1.0)

    if pct > 0:
        r = int(198 - 160 * intensity)
        g = int(219 - 60 * intensity)
        b = int(198 - 160 * intensity)
    elif pct < 0:
        r = int(219 - 60 * intensity)
        g = int(198 - 160 * intensity)
        b = int(198 - 160 * intensity)
    else:
        r, g, b = 180, 180, 180

    return f'rgb({r},{g},{b})'


def build_figure(df):
    """Arma la figura de Plotly (velas diarias en % vs cierre anterior)."""
    fig = go.Figure()
    fecha = datetime.now().strftime("%Y-%m-%d")

    for _, row in df.iterrows():
        ticker = row['Ticker']
        o, h, l, c = row['Apertura'], row['Máximo'], row['Mínimo'], row['Precio']
        prev, pct = row['Cierre anterior'], row['Variación %']

        if any(pd.isna(v) for v in [o, h, l, c, prev]) or prev == 0:
            logging.warning(f"Datos incompletos para {ticker}, se omite del gráfico")
            continue

        o_pct = (o - prev) / prev * 100
        h_pct = (h - prev) / prev * 100
        l_pct = (l - prev) / prev * 100
        c_pct = pct

        color = get_candle_color(pct)

        fig.add_trace(go.Candlestick(
            x=[ticker],
            open=[o_pct], high=[h_pct], low=[l_pct], close=[c_pct],
            increasing_line_color=color, increasing_fillcolor=color,
            decreasing_line_color=color, decreasing_fillcolor=color,
            line=dict(width=1.3),
            showlegend=False,
            name=ticker,
            text=(
                f"<b>{ticker}</b><br>"
                f"Apertura: {o_pct:+.2f}%<br>"
                f"Máximo: {h_pct:+.2f}%<br>"
                f"Mínimo: {l_pct:+.2f}%<br>"
                f"Cierre: {c_pct:+.2f}%"
            ),
            hoverinfo="text"
        ))

    fig.update_layout(
        title=dict(
            text=f"ADRs Argentina - {fecha}<br><sup>Variación diaria vs cierre anterior (%)</sup>",
            x=0.5, xanchor="center"
        ),
        yaxis_title="Cambio % diario",
        xaxis_title="Ticker",
        plot_bgcolor="white",
        xaxis_rangeslider_visible=True,
        showlegend=False
    )
    fig.update_yaxes(zeroline=True, zerolinecolor="black", zerolinewidth=1, gridcolor="#eee")

    fig.add_annotation(
        text="@MJPmarkets",
        xref="paper", yref="paper",
        x=0.95, y=0.05,
        showarrow=False,
        font=dict(size=18, color="rgba(1,1,1,1)"),
        align="right"
    )

    return fig


def render_page(fig):
    """
    Envuelve el gráfico en una página HTML con:
    - auto-refresh cada REFRESH_SECONDS
    - un botón para descargar una copia (PNG) del gráfico, resuelto
      100% en el navegador con Plotly.downloadImage (no requiere
      kaleido ni nada en el server -> ideal para Vercel).
    """
    div_id = "adrsChart"
    plot_html = fig.to_html(
        include_plotlyjs='cdn',
        full_html=False,
        div_id=div_id,
        config={"displaylogo": False}
    )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    page = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="{REFRESH_SECONDS}">
    <title>ADRs Argentina</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .toolbar {{
            text-align: center;
            margin-bottom: 12px;
        }}
        button {{
            background: #305496;
            color: white;
            border: none;
            padding: 10px 18px;
            border-radius: 6px;
            font-size: 14px;
            cursor: pointer;
        }}
        button:hover {{
            background: #24406e;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <button onclick="descargarGrafico()">📥 Guardar copia del gráfico (PNG)</button>
    </div>

    {plot_html}

    <script>
        function descargarGrafico() {{
            var chartDiv = document.getElementById('{div_id}');
            Plotly.downloadImage(chartDiv, {{
                format: 'png',
                filename: 'adrs_argentina_{timestamp}',
                width: 1400,
                height: 800
            }});
        }}
    </script>
</body>
</html>
"""
    return page


@app.route('/')
def home():
    try:
        df = fetch_watchlist(WATCHLIST)
        fig = build_figure(df)
        html = render_page(fig)
        return Response(html, mimetype='text/html')
    except Exception as e:
        logging.error(f"Error generando la página: {e}")
        return Response(f"<h1>Error al generar el reporte</h1><p>{e}</p>", mimetype='text/html', status=500)


# Vercel busca una variable llamada "app" en este archivo
if __name__ == '__main__':
    app.run(debug=True)
